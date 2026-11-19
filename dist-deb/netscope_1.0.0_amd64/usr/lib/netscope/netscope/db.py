"""SQLite persistence, integrity checks, backups, and timezone-aware queries for NETSCOPE."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = os.environ.get(
    "NETSCOPE_DB_PATH",
    os.path.join(os.getcwd(), "data", "netscope.db"),
)

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interface_state (
    iface TEXT PRIMARY KEY,
    iface_type TEXT NOT NULL,
    last_rx_bytes INTEGER NOT NULL,
    last_tx_bytes INTEGER NOT NULL,
    last_rx_packets INTEGER NOT NULL DEFAULT 0,
    last_tx_packets INTEGER NOT NULL DEFAULT 0,
    boot_rx_bytes INTEGER NOT NULL DEFAULT 0,
    boot_tx_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    ip_addresses TEXT NOT NULL DEFAULT '[]',
    mac_address TEXT NOT NULL DEFAULT '',
    mtu INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interface_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    local_date TEXT NOT NULL,
    iface TEXT NOT NULL,
    iface_type TEXT NOT NULL,
    rx_delta INTEGER NOT NULL,
    tx_delta INTEGER NOT NULL,
    rx_rate_bps REAL NOT NULL,
    tx_rate_bps REAL NOT NULL,
    is_loopback INTEGER NOT NULL DEFAULT 0,
    is_vpn INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_iface_samples_ts ON interface_samples(ts_utc);
CREATE INDEX IF NOT EXISTS idx_iface_samples_date_iface ON interface_samples(local_date, iface);

CREATE TABLE IF NOT EXISTS daily_interface_usage (
    local_date TEXT NOT NULL,
    iface TEXT NOT NULL,
    iface_type TEXT NOT NULL,
    rx_bytes INTEGER NOT NULL DEFAULT 0,
    tx_bytes INTEGER NOT NULL DEFAULT 0,
    is_loopback INTEGER NOT NULL DEFAULT 0,
    is_vpn INTEGER NOT NULL DEFAULT 0,
    measurement_source TEXT NOT NULL DEFAULT 'kernel_proc_net_dev',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (local_date, iface)
);

CREATE INDEX IF NOT EXISTS idx_daily_iface_date ON daily_interface_usage(local_date);

CREATE TABLE IF NOT EXISTS app_usage_daily (
    local_date TEXT NOT NULL,
    app_id TEXT NOT NULL,
    app_name TEXT NOT NULL,
    exe_path TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    rx_bytes INTEGER,
    tx_bytes INTEGER,
    bytes_available INTEGER NOT NULL DEFAULT 0,
    measurement_source TEXT NOT NULL,
    last_active_ts TEXT NOT NULL,
    active_sockets INTEGER NOT NULL DEFAULT 0,
    interfaces_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (local_date, app_id)
);

CREATE INDEX IF NOT EXISTS idx_app_usage_date ON app_usage_daily(local_date);

CREATE TABLE IF NOT EXISTS app_socket_snapshots (
    app_id TEXT PRIMARY KEY,
    app_name TEXT NOT NULL,
    exe_path TEXT NOT NULL,
    owner TEXT NOT NULL,
    pids_json TEXT NOT NULL,
    status TEXT NOT NULL,
    active_sockets INTEGER NOT NULL,
    tcp_established INTEGER NOT NULL,
    udp_active INTEGER NOT NULL,
    lan_sockets INTEGER NOT NULL,
    internet_sockets INTEGER NOT NULL,
    rx_rate_bps REAL,
    tx_rate_bps REAL,
    total_rx_bytes INTEGER,
    total_tx_bytes INTEGER,
    bytes_available INTEGER NOT NULL DEFAULT 0,
    measurement_source TEXT NOT NULL,
    connections_json TEXT NOT NULL,
    interfaces_json TEXT NOT NULL,
    last_active_ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS browser_tabs (
    tab_key TEXT PRIMARY KEY,
    browser_name TEXT NOT NULL,
    tab_id TEXT NOT NULL,
    tab_title TEXT NOT NULL,
    domain TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    rx_bytes INTEGER NOT NULL DEFAULT 0,
    tx_bytes INTEGER NOT NULL DEFAULT 0,
    rx_rate_bps REAL NOT NULL DEFAULT 0,
    tx_rate_bps REAL NOT NULL DEFAULT 0,
    accuracy_label TEXT NOT NULL DEFAULT 'browser_reported_estimate',
    measurement_source TEXT NOT NULL DEFAULT 'browser_extension_webrequest',
    last_active_ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    period_label TEXT NOT NULL,
    start_ts TEXT,
    end_ts TEXT,
    iface TEXT NOT NULL DEFAULT '',
    rx_bytes INTEGER,
    tx_bytes INTEGER,
    measurement_accuracy TEXT NOT NULL,
    measurement_type TEXT NOT NULL,
    import_status TEXT NOT NULL,
    notes TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    period_type TEXT NOT NULL, -- daily, weekly, monthly, custom
    limit_bytes INTEGER NOT NULL,
    custom_days INTEGER NOT NULL DEFAULT 30,
    include_vpn INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    notify_desktop INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    limit_id INTEGER,
    threshold_pct INTEGER NOT NULL,
    period_key TEXT NOT NULL,
    consumed_bytes INTEGER NOT NULL,
    limit_bytes INTEGER NOT NULL,
    message TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(limit_id, threshold_pct, period_key)
);

CREATE TABLE IF NOT EXISTS network_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    event_type TEXT NOT NULL,
    iface TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_network_events_ts ON network_events(ts_utc);
"""

DEFAULT_SETTINGS = {
    "refresh_interval_sec": "1",
    "exclude_loopback": "true",
    "privacy_mode": "false",
    "monitoring_paused": "false",
    "retention_days": "365",
    "theme": "system",
    "browser_telemetry_enabled": "true",
    "desktop_notifications": "true",
}


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def local_date_str(ts: dt.datetime | None = None) -> str:
    d = ts or now_local()
    return d.strftime("%Y-%m-%d")


class NetscopeDB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            now_iso = now_utc_iso()
            for key, val in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, val, now_iso),
                )
            conn.commit()

    def integrity_check(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("PRAGMA integrity_check;").fetchone()
            status = row[0] if row else "unknown"
            page_count = conn.execute("PRAGMA page_count;").fetchone()[0]
            page_size = conn.execute("PRAGMA page_size;").fetchone()[0]
        size_bytes = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        return {
            "status": status,
            "ok": status == "ok",
            "db_path": self.db_path,
            "size_bytes": size_bytes,
            "allocated_bytes": page_count * page_size,
        }

    def create_backup(self, keep_last: int = 5) -> str:
        backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
        Path(backup_dir).mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = os.path.join(backup_dir, f"netscope-{stamp}.db")
        with self.connect() as src:
            dst_conn = sqlite3.connect(dest)
            try:
                src.backup(dst_conn)
            finally:
                dst_conn.close()
        backups = sorted(Path(backup_dir).glob("netscope-*.db"))
        for old in backups[:-keep_last]:
            try:
                old.unlink()
            except OSError:
                pass
        return dest

    def get_settings(self) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        out = dict(DEFAULT_SETTINGS)
        for r in rows:
            out[r["key"]] = r["value"]
        return out

    def update_setting(self, key: str, value: str) -> None:
        now_iso = now_utc_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, str(value), now_iso),
            )
            conn.commit()

    def record_sample_batch(
        self,
        ts_utc: str,
        local_date: str,
        iface_deltas: list[dict[str, Any]],
        iface_states: list[dict[str, Any]],
        app_snapshots: list[dict[str, Any]],
        network_events: list[dict[str, str]],
        retention_days: int = 365,
    ) -> None:
        with self.connect() as conn:
            for st in iface_states:
                conn.execute(
                    """
                    INSERT INTO interface_state (
                        iface, iface_type, last_rx_bytes, last_tx_bytes,
                        last_rx_packets, last_tx_packets, boot_rx_bytes, boot_tx_bytes,
                        status, ip_addresses, mac_address, mtu, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(iface) DO UPDATE SET
                        iface_type = excluded.iface_type,
                        last_rx_bytes = excluded.last_rx_bytes,
                        last_tx_bytes = excluded.last_tx_bytes,
                        last_rx_packets = excluded.last_rx_packets,
                        last_tx_packets = excluded.last_tx_packets,
                        boot_rx_bytes = excluded.boot_rx_bytes,
                        boot_tx_bytes = excluded.boot_tx_bytes,
                        status = excluded.status,
                        ip_addresses = excluded.ip_addresses,
                        mac_address = excluded.mac_address,
                        mtu = excluded.mtu,
                        updated_at = excluded.updated_at
                    """,
                    (
                        st["iface"],
                        st["iface_type"],
                        st["rx_bytes"],
                        st["tx_bytes"],
                        st["rx_packets"],
                        st["tx_packets"],
                        st["rx_bytes"],
                        st["tx_bytes"],
                        st["status"],
                        json.dumps(st["ip_addresses"]),
                        st["mac_address"],
                        st["mtu"],
                        ts_utc,
                    ),
                )

            for d in iface_deltas:
                conn.execute(
                    """
                    INSERT INTO interface_samples (
                        ts_utc, local_date, iface, iface_type,
                        rx_delta, tx_delta, rx_rate_bps, tx_rate_bps,
                        is_loopback, is_vpn
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts_utc,
                        local_date,
                        d["iface"],
                        d["iface_type"],
                        d["rx_delta"],
                        d["tx_delta"],
                        d["rx_rate_bps"],
                        d["tx_rate_bps"],
                        1 if d["is_loopback"] else 0,
                        1 if d["is_vpn"] else 0,
                    ),
                )

                conn.execute(
                    """
                    INSERT INTO daily_interface_usage (
                        local_date, iface, iface_type, rx_bytes, tx_bytes,
                        is_loopback, is_vpn, measurement_source, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'kernel_proc_net_dev', ?)
                    ON CONFLICT(local_date, iface) DO UPDATE SET
                        iface_type = excluded.iface_type,
                        rx_bytes = daily_interface_usage.rx_bytes + excluded.rx_bytes,
                        tx_bytes = daily_interface_usage.tx_bytes + excluded.tx_bytes,
                        is_loopback = excluded.is_loopback,
                        is_vpn = excluded.is_vpn,
                        updated_at = excluded.updated_at
                    """,
                    (
                        local_date,
                        d["iface"],
                        d["iface_type"],
                        d["rx_delta"],
                        d["tx_delta"],
                        1 if d["is_loopback"] else 0,
                        1 if d["is_vpn"] else 0,
                        ts_utc,
                    ),
                )

            # Mark previously running apps stopped if absent in this snapshot
            active_app_ids = [a["app_id"] for a in app_snapshots]
            if active_app_ids:
                placeholders = ",".join("?" for _ in active_app_ids)
                conn.execute(
                    f"UPDATE app_socket_snapshots SET status = 'stopped', active_sockets = 0, tcp_established = 0, udp_active = 0, rx_rate_bps = 0, tx_rate_bps = 0, connections_json = '[]' WHERE app_id NOT IN ({placeholders})",
                    active_app_ids,
                )
            else:
                conn.execute(
                    "UPDATE app_socket_snapshots SET status = 'stopped', active_sockets = 0, tcp_established = 0, udp_active = 0, rx_rate_bps = 0, tx_rate_bps = 0, connections_json = '[]'"
                )

            for app in app_snapshots:
                rx_delta = app.get("rx_delta")
                tx_delta = app.get("tx_delta")
                bytes_avail = 1 if app.get("bytes_available") else 0

                conn.execute(
                    """
                    INSERT INTO app_usage_daily (
                        local_date, app_id, app_name, exe_path, owner,
                        rx_bytes, tx_bytes, bytes_available, measurement_source,
                        last_active_ts, active_sockets, interfaces_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(local_date, app_id) DO UPDATE SET
                        app_name = excluded.app_name,
                        exe_path = CASE WHEN excluded.exe_path != '' THEN excluded.exe_path ELSE app_usage_daily.exe_path END,
                        owner = CASE WHEN excluded.owner != '' THEN excluded.owner ELSE app_usage_daily.owner END,
                        rx_bytes = CASE
                            WHEN excluded.bytes_available = 1 THEN COALESCE(app_usage_daily.rx_bytes, 0) + COALESCE(excluded.rx_bytes, 0)
                            ELSE app_usage_daily.rx_bytes
                        END,
                        tx_bytes = CASE
                            WHEN excluded.bytes_available = 1 THEN COALESCE(app_usage_daily.tx_bytes, 0) + COALESCE(excluded.tx_bytes, 0)
                            ELSE app_usage_daily.tx_bytes
                        END,
                        bytes_available = MAX(app_usage_daily.bytes_available, excluded.bytes_available),
                        measurement_source = excluded.measurement_source,
                        last_active_ts = excluded.last_active_ts,
                        active_sockets = excluded.active_sockets,
                        interfaces_json = excluded.interfaces_json
                    """,
                    (
                        local_date,
                        app["app_id"],
                        app["app_name"],
                        app["exe_path"],
                        app["owner"],
                        rx_delta if bytes_avail else None,
                        tx_delta if bytes_avail else None,
                        bytes_avail,
                        app["measurement_source"],
                        ts_utc,
                        app["active_sockets"],
                        json.dumps(app["interfaces"]),
                    ),
                )

                # Get accumulated daily/lifetime for snapshot display
                row = conn.execute(
                    "SELECT SUM(rx_bytes) AS total_rx, SUM(tx_bytes) AS total_tx, MAX(bytes_available) AS has_bytes FROM app_usage_daily WHERE app_id = ?",
                    (app["app_id"],),
                ).fetchone()
                total_rx = row["total_rx"] if row and row["has_bytes"] else None
                total_tx = row["total_tx"] if row and row["has_bytes"] else None

                conn.execute(
                    """
                    INSERT INTO app_socket_snapshots (
                        app_id, app_name, exe_path, owner, pids_json, status,
                        active_sockets, tcp_established, udp_active,
                        lan_sockets, internet_sockets,
                        rx_rate_bps, tx_rate_bps, total_rx_bytes, total_tx_bytes,
                        bytes_available, measurement_source,
                        connections_json, interfaces_json, last_active_ts
                    ) VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(app_id) DO UPDATE SET
                        app_name = excluded.app_name,
                        exe_path = excluded.exe_path,
                        owner = excluded.owner,
                        pids_json = excluded.pids_json,
                        status = 'running',
                        active_sockets = excluded.active_sockets,
                        tcp_established = excluded.tcp_established,
                        udp_active = excluded.udp_active,
                        lan_sockets = excluded.lan_sockets,
                        internet_sockets = excluded.internet_sockets,
                        rx_rate_bps = excluded.rx_rate_bps,
                        tx_rate_bps = excluded.tx_rate_bps,
                        total_rx_bytes = excluded.total_rx_bytes,
                        total_tx_bytes = excluded.total_tx_bytes,
                        bytes_available = excluded.bytes_available,
                        measurement_source = excluded.measurement_source,
                        connections_json = excluded.connections_json,
                        interfaces_json = excluded.interfaces_json,
                        last_active_ts = excluded.last_active_ts
                    """,
                    (
                        app["app_id"],
                        app["app_name"],
                        app["exe_path"],
                        app["owner"],
                        json.dumps(app["pids"]),
                        app["active_sockets"],
                        app["tcp_established"],
                        app["udp_active"],
                        app["lan_sockets"],
                        app["internet_sockets"],
                        app["rx_rate_bps"] if bytes_avail else None,
                        app["tx_rate_bps"] if bytes_avail else None,
                        total_rx,
                        total_tx,
                        bytes_avail,
                        app["measurement_source"],
                        json.dumps(app["connections"][:25]),
                        json.dumps(app["interfaces"]),
                        ts_utc,
                    ),
                )

            for ev in network_events:
                conn.execute(
                    "INSERT INTO network_events (ts_utc, event_type, iface, details) VALUES (?, ?, ?, ?)",
                    (ts_utc, ev["event_type"], ev["iface"], ev["details"]),
                )

            # Prune raw per-second samples older than 48 hours to keep SQLite compact
            # while daily_interface_usage & app_usage_daily keep long-term retention
            cutoff_samples = (
                dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)
            ).isoformat()
            conn.execute("DELETE FROM interface_samples WHERE ts_utc < ?", (cutoff_samples,))

            if retention_days > 0:
                cutoff_date = (now_local() - dt.timedelta(days=retention_days)).strftime("%Y-%m-%d")
                conn.execute("DELETE FROM daily_interface_usage WHERE local_date < ?", (cutoff_date,))
                conn.execute("DELETE FROM app_usage_daily WHERE local_date < ?", (cutoff_date,))

            conn.commit()
