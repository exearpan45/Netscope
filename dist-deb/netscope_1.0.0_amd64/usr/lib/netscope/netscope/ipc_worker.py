"""Persistent stdin/stdout JSON-RPC worker for zero-overhead IPC between Node/Express and NETSCOPE Python engine."""

from __future__ import annotations

import base64
import json
import os
import sys
import traceback
from typing import Any

from netscope.analytics import query_dashboard_state, query_period_analytics
from netscope.capabilities import detect_capabilities
from netscope.db import NetscopeDB, now_utc_iso
from netscope.exporter import export_csv, export_json, export_pdf
from netscope.history_importer import run_historical_import

LIVE_STATE_PATH = os.environ.get(
    "NETSCOPE_LIVE_STATE",
    os.path.join(os.getcwd(), "data", "live_state.json"),
)


def _read_live_state() -> dict[str, Any] | None:
    if not os.path.exists(LIVE_STATE_PATH):
        return None
    try:
        with open(LIVE_STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def handle_request(db: NetscopeDB, req: dict[str, Any]) -> Any:
    action = req.get("action")
    params = req.get("params") or {}

    if action == "dashboard":
        return query_dashboard_state(db, _read_live_state())

    if action == "capabilities":
        return detect_capabilities().to_dict()

    if action == "analytics":
        settings = db.get_settings()
        exclude_lo = settings.get("exclude_loopback", "true") == "true"
        if "exclude_loopback" in params:
            exclude_lo = bool(params["exclude_loopback"])
        return query_period_analytics(
            db,
            period=str(params.get("period", "last_30_days")),
            custom_start=params.get("start"),
            custom_end=params.get("end"),
            exclude_loopback=exclude_lo,
            iface_filter=params.get("iface"),
        )

    if action == "app_detail":
        app_id = str(params.get("app_id", ""))
        with db.connect() as conn:
            snap = conn.execute(
                "SELECT * FROM app_socket_snapshots WHERE app_id = ?", (app_id,)
            ).fetchone()
            history = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM app_usage_daily WHERE app_id = ? ORDER BY local_date DESC LIMIT 90",
                    (app_id,),
                ).fetchall()
            ]
        return {
            "snapshot": dict(snap) if snap else None,
            "history": history,
        }

    if action == "history_import":
        return run_historical_import(db, force=bool(params.get("force", True)))

    if action == "update_settings":
        allowed = {
            "refresh_interval_sec",
            "exclude_loopback",
            "privacy_mode",
            "monitoring_paused",
            "retention_days",
            "theme",
            "browser_telemetry_enabled",
            "desktop_notifications",
        }
        for k, v in params.items():
            if k in allowed:
                db.update_setting(k, str(v).lower() if isinstance(v, bool) else str(v))
        return db.get_settings()

    if action == "create_limit":
        name = str(params.get("name", "Monthly Allowance")).strip() or "Data Allowance"
        period_type = str(params.get("period_type", "monthly"))
        limit_bytes = int(params.get("limit_bytes", 0))
        custom_days = int(params.get("custom_days", 30))
        notify_desktop = 1 if params.get("notify_desktop", True) else 0
        if limit_bytes <= 0:
            raise ValueError("limit_bytes must be positive")
        with db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO data_limits (name, period_type, limit_bytes, custom_days, enabled, notify_desktop, created_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (name, period_type, limit_bytes, custom_days, notify_desktop, now_utc_iso()),
            )
            conn.commit()
            return {"id": cur.lastrowid}

    if action == "delete_limit":
        lim_id = int(params.get("id", 0))
        with db.connect() as conn:
            conn.execute("DELETE FROM alert_events WHERE limit_id = ?", (lim_id,))
            conn.execute("DELETE FROM data_limits WHERE id = ?", (lim_id,))
            conn.commit()
        return {"deleted": lim_id}

    if action == "ack_alerts":
        with db.connect() as conn:
            conn.execute("UPDATE alert_events SET acknowledged = 1")
            conn.commit()
        return {"ok": True}

    if action == "browser_telemetry":
        settings = db.get_settings()
        if settings.get("browser_telemetry_enabled", "true") != "true" or settings.get("privacy_mode", "false") == "true":
            return {"accepted": False, "reason": "Browser telemetry disabled or privacy mode active"}
        tabs = params.get("tabs") or []
        now_iso = now_utc_iso()
        with db.connect() as conn:
            for t in tabs:
                browser_name = str(t.get("browser_name", "Unknown Browser"))
                tab_id = str(t.get("tab_id", ""))
                domain = str(t.get("domain", ""))
                if not tab_id or not domain:
                    continue
                tab_key = f"{browser_name}:{tab_id}"
                conn.execute(
                    """
                    INSERT INTO browser_tabs (
                        tab_key, browser_name, tab_id, tab_title, domain,
                        is_active, rx_bytes, tx_bytes, rx_rate_bps, tx_rate_bps,
                        accuracy_label, measurement_source, last_active_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'browser_reported_estimate', ?, ?)
                    ON CONFLICT(tab_key) DO UPDATE SET
                        tab_title = excluded.tab_title,
                        domain = excluded.domain,
                        is_active = excluded.is_active,
                        rx_bytes = browser_tabs.rx_bytes + MAX(0, excluded.rx_bytes),
                        tx_bytes = browser_tabs.tx_bytes + MAX(0, excluded.tx_bytes),
                        rx_rate_bps = excluded.rx_rate_bps,
                        tx_rate_bps = excluded.tx_rate_bps,
                        last_active_ts = excluded.last_active_ts
                    """,
                    (
                        tab_key,
                        browser_name,
                        tab_id,
                        str(t.get("tab_title", domain))[:240],
                        domain[:180],
                        1 if t.get("is_active") else 0,
                        int(t.get("rx_delta_bytes", 0) or 0),
                        int(t.get("tx_delta_bytes", 0) or 0),
                        float(t.get("rx_rate_bps", 0) or 0),
                        float(t.get("tx_rate_bps", 0) or 0),
                        str(t.get("measurement_source", "browser_extension_webrequest")),
                        now_iso,
                    ),
                )
            conn.commit()
        return {"accepted": True, "count": len(tabs)}

    if action == "backup":
        path = db.create_backup(keep_last=5)
        return {"backup_path": path, "integrity": db.integrity_check()}

    if action == "export":
        fmt = str(params.get("format", "json")).lower()
        scope = str(params.get("scope", "complete")).lower()
        if fmt == "csv":
            return {"content_type": "text/csv", "data": export_csv(db, scope), "encoding": "utf-8"}
        if fmt == "pdf":
            pdf_bytes = export_pdf(db, scope)
            return {
                "content_type": "application/pdf",
                "data": base64.b64encode(pdf_bytes).decode("ascii"),
                "encoding": "base64",
            }
        return {"content_type": "application/json", "data": export_json(db, scope), "encoding": "utf-8"}

    raise ValueError(f"Unknown action: {action}")


def main() -> int:
    db = NetscopeDB()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            result = handle_request(db, req)
            sys.stdout.write(json.dumps({"id": req_id, "ok": True, "result": result}) + "\n")
        except Exception as exc:
            sys.stdout.write(
                json.dumps(
                    {
                        "id": req_id,
                        "ok": False,
                        "error": str(exc),
                        "trace": traceback.format_exc(),
                    }
                )
                + "\n"
            )
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
