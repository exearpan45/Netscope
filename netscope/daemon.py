"""Lightweight NETSCOPE background monitoring daemon & CLI entrypoint."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from netscope.analytics import query_period_analytics, resolve_custom_limit_range
from netscope.capabilities import detect_capabilities
from netscope.db import NetscopeDB, local_date_str, now_local, now_utc_iso
from netscope.history_importer import run_historical_import
from netscope.proc_monitor import collect_process_applications, read_proc_net_dev

LIVE_STATE_PATH = os.environ.get(
    "NETSCOPE_LIVE_STATE",
    os.path.join(os.getcwd(), "data", "live_state.json"),
)

_RUNNING = True


def _handle_signal(_signum: int, _frame: Any) -> None:
    global _RUNNING
    _RUNNING = False


def _desktop_gui_running() -> bool:
    """Avoid duplicate popups when the Qt tray application owns notifications."""
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit() or entry == str(os.getpid()):
                continue
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as fh:
                    cmdline = fh.read()
                if b"netscope_gui.py" in cmdline:
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _send_desktop_notification(title: str, body: str) -> bool:
    """Send a session notification and report failures instead of hiding them."""
    notify_bin = shutil.which("notify-send")
    if not notify_bin:
        sys.stderr.write("[netscope.daemon] notify-send is unavailable; desktop alert was not delivered.\n")
        return False
    try:
        result = subprocess.run(
            [notify_bin, "-a", "NETSCOPE", title, body],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or "").strip() or f"exit status {result.returncode}"
            sys.stderr.write(f"[netscope.daemon] desktop notification failed: {detail}\n")
            return False
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"[netscope.daemon] desktop notification error: {exc}\n")
        return False


def _write_live_state(payload: dict[str, Any]) -> None:
    Path(LIVE_STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
    tmp = f"{LIVE_STATE_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, LIVE_STATE_PATH)


class MonitorEngine:
    def __init__(self, db: NetscopeDB) -> None:
        self.db = db
        self.caps = detect_capabilities()
        self.prev_iface_bytes: dict[str, tuple[int, int]] = {}
        self.prev_iface_status: dict[str, str] = {}
        self.prev_socket_bytes: dict[tuple[str, int, str, int], tuple[int, int]] = {}
        self.last_tick_mono: float = time.monotonic()
        self.last_backup_date: str = ""

        # Always establish a fresh in-memory baseline. Reusing persisted kernel
        # counters after a reboot or daemon restart can turn the entire gap since
        # the last sample into a false one-second traffic spike.
        self.prev_iface_bytes = {}
        self.prev_iface_status = {}

    def _evaluate_limits(self, local_date: str, settings: dict[str, str]) -> None:
        exclude_lo = settings.get("exclude_loopback", "true") == "true"
        desktop_ok = settings.get("desktop_notifications", "true") == "true"
        with self.db.connect() as conn:
            limits = conn.execute(
                "SELECT * FROM data_limits WHERE enabled = 1"
            ).fetchall()
        if not limits:
            return

        now_d = now_local().date()
        for lim in limits:
            p = lim["period_type"]
            if p == "daily":
                res = query_period_analytics(self.db, "today", exclude_loopback=exclude_lo)
                period_key = local_date
            elif p == "weekly":
                res = query_period_analytics(self.db, "this_week", exclude_loopback=exclude_lo)
                iso_cal = now_d.isocalendar()
                period_key = f"{iso_cal.year}-W{iso_cal.week:02d}"
            elif p == "monthly":
                res = query_period_analytics(self.db, "this_month", exclude_loopback=exclude_lo)
                period_key = now_d.strftime("%Y-%m")
            else:
                start_c, end_c, period_key = resolve_custom_limit_range(lim, now_d)
                res = query_period_analytics(self.db, "custom", start_c, end_c, exclude_loopback=exclude_lo)

            consumed = int(res["summary"]["total_bytes"])
            limit_bytes = int(lim["limit_bytes"])
            if limit_bytes <= 0:
                continue
            pct = (consumed / limit_bytes) * 100.0

            for threshold in (50, 75, 90, 100):
                if pct >= threshold:
                    msg = f"NETSCOPE: You have consumed {threshold}% of your {lim['name']} ({p}) data allowance."
                    with self.db.connect() as conn:
                        cur = conn.execute(
                            """
                            INSERT OR IGNORE INTO alert_events (
                                limit_id, threshold_pct, period_key,
                                consumed_bytes, limit_bytes, message, acknowledged, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                            """,
                            (
                                lim["id"],
                                threshold,
                                period_key,
                                consumed,
                                limit_bytes,
                                msg,
                                now_utc_iso(),
                            ),
                        )
                        conn.commit()
                        if cur.rowcount > 0 and desktop_ok and lim["notify_desktop"]:
                            if not _desktop_gui_running():
                                _send_desktop_notification("NETSCOPE Data Allowance Alert", msg)

    def step(self) -> dict[str, Any]:
        settings = self.db.get_settings()
        paused = settings.get("monitoring_paused", "false") == "true"
        privacy = settings.get("privacy_mode", "false") == "true"
        retention_days = int(settings.get("retention_days", "365") or 365)

        now_mono = time.monotonic()
        elapsed = max(0.2, now_mono - self.last_tick_mono)
        self.last_tick_mono = now_mono

        ts_utc = now_utc_iso()
        l_date = local_date_str()

        if paused:
            _write_live_state({"daemon_alive": True, "paused": True, "ts_utc": ts_utc})
            return {"paused": True, "ts_utc": ts_utc}

        ifaces = read_proc_net_dev()
        iface_deltas: list[dict[str, Any]] = []
        iface_states: list[dict[str, Any]] = []
        events: list[dict[str, str]] = []

        for snap in ifaces:
            prev = self.prev_iface_bytes.get(snap.iface)
            if prev is None:
                # First observation for this interface: baseline without phantom spike
                d_rx, d_tx = 0, 0
            else:
                prev_rx, prev_tx = prev
                # Handle kernel counter reset (reboot or interface recreate) cleanly
                d_rx = snap.rx_bytes - prev_rx if snap.rx_bytes >= prev_rx else snap.rx_bytes
                d_tx = snap.tx_bytes - prev_tx if snap.tx_bytes >= prev_tx else snap.tx_bytes

            self.prev_iface_bytes[snap.iface] = (snap.rx_bytes, snap.tx_bytes)

            old_status = self.prev_iface_status.get(snap.iface)
            if old_status is None:
                if snap.is_vpn and snap.status == "up":
                    events.append(
                        {"event_type": "vpn_connected", "iface": snap.iface, "details": f"VPN interface {snap.iface} active"}
                    )
            elif old_status != snap.status:
                ev_type = "interface_up" if snap.status == "up" else "interface_down"
                if snap.is_vpn:
                    ev_type = "vpn_connected" if snap.status == "up" else "vpn_disconnected"
                events.append(
                    {
                        "event_type": ev_type,
                        "iface": snap.iface,
                        "details": f"{snap.iface} ({snap.iface_type}) transitioned {old_status} -> {snap.status}",
                    }
                )
            self.prev_iface_status[snap.iface] = snap.status

            iface_deltas.append(
                {
                    "iface": snap.iface,
                    "iface_type": snap.iface_type,
                    "rx_delta": d_rx,
                    "tx_delta": d_tx,
                    "rx_rate_bps": round(d_rx / elapsed, 2),
                    "tx_rate_bps": round(d_tx / elapsed, 2),
                    "is_loopback": snap.is_loopback,
                    "is_vpn": snap.is_vpn,
                }
            )
            iface_states.append(
                {
                    "iface": snap.iface,
                    "iface_type": snap.iface_type,
                    "rx_bytes": snap.rx_bytes,
                    "tx_bytes": snap.tx_bytes,
                    "rx_packets": snap.rx_packets,
                    "tx_packets": snap.tx_packets,
                    "status": snap.status,
                    "ip_addresses": snap.ip_addresses,
                    "mac_address": snap.mac_address,
                    "mtu": snap.mtu,
                }
            )

        if privacy:
            app_snapshots = []
        else:
            app_snapshots, new_sock_map = collect_process_applications(
                ifaces,
                self.prev_socket_bytes,
                elapsed,
                self.caps.per_process_bytes_available,
                self.caps.per_process_byte_method,
            )
            self.prev_socket_bytes = new_sock_map

        self.db.record_sample_batch(
            ts_utc=ts_utc,
            local_date=l_date,
            iface_deltas=iface_deltas,
            iface_states=iface_states,
            app_snapshots=app_snapshots,
            network_events=events,
            retention_days=retention_days,
        )

        self._evaluate_limits(l_date, settings)

        # Daily automatic SQLite backup
        if self.last_backup_date != l_date:
            try:
                self.db.create_backup(keep_last=5)
                self.last_backup_date = l_date
            except Exception:
                pass

        live_payload = {
            "daemon_alive": True,
            "paused": False,
            "ts_utc": ts_utc,
            "interfaces": iface_deltas,
            "app_count": len(app_snapshots),
        }
        _write_live_state(live_payload)
        return live_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="NETSCOPE Linux Network Monitoring Daemon")
    parser.add_argument("--daemon", action="store_true", help="Run continuous monitoring loop")
    parser.add_argument("--once", action="store_true", help="Collect one sample and exit")
    parser.add_argument("--import-history", action="store_true", help="Run historical import scan")
    parser.add_argument("--db", default=None, help="Path to SQLite database")
    args = parser.parse_args()

    db = NetscopeDB(args.db) if args.db else NetscopeDB()
    # Run initial historical scan once on startup
    run_historical_import(db, force=False)

    if args.import_history:
        res = run_historical_import(db, force=True)
        print(json.dumps(res, indent=2))
        return 0

    engine = MonitorEngine(db)
    if args.once or not args.daemon:
        out = engine.step()
        if args.once:
            print(json.dumps(out, indent=2))
            return 0

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    while _RUNNING:
        loop_start = time.monotonic()
        try:
            engine.step()
        except Exception as exc:
            sys.stderr.write(f"[netscope.daemon] sample error: {exc}\n")
            sys.stderr.flush()
        settings = db.get_settings()
        interval = float(settings.get("refresh_interval_sec", "1") or 1.0)
        interval = max(1.0, min(10.0, interval))
        sleep_for = max(0.2, interval - (time.monotonic() - loop_start))
        time.sleep(sleep_for)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
