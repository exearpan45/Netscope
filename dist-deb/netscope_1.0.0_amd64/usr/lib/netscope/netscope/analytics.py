"""Analytics & time-range query engine for NETSCOPE."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from netscope.capabilities import detect_capabilities
from netscope.db import NetscopeDB, local_date_str, now_local


def resolve_date_range(
    period: str, custom_start: str | None = None, custom_end: str | None = None
) -> tuple[str, str, str]:
    """Return (start_local_date, end_local_date, human_label)."""
    today = now_local().date()

    if period == "today":
        s = today.isoformat()
        return s, s, "Today"
    if period == "yesterday":
        y = (today - dt.timedelta(days=1)).isoformat()
        return y, y, "Yesterday"
    if period == "last_7_days":
        return (today - dt.timedelta(days=6)).isoformat(), today.isoformat(), "Last 7 Days"
    if period == "this_week":
        start = today - dt.timedelta(days=today.weekday())
        return start.isoformat(), today.isoformat(), "This Week"
    if period == "previous_week":
        this_mon = today - dt.timedelta(days=today.weekday())
        prev_mon = this_mon - dt.timedelta(days=7)
        prev_sun = this_mon - dt.timedelta(days=1)
        return prev_mon.isoformat(), prev_sun.isoformat(), "Previous Week"
    if period == "last_30_days":
        return (today - dt.timedelta(days=29)).isoformat(), today.isoformat(), "Last 30 Days"
    if period == "this_month":
        return today.replace(day=1).isoformat(), today.isoformat(), "This Month"
    if period == "previous_month":
        first_this = today.replace(day=1)
        last_prev = first_this - dt.timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev.isoformat(), last_prev.isoformat(), "Previous Month"
    if period == "last_3_months":
        return (today - dt.timedelta(days=89)).isoformat(), today.isoformat(), "Last 3 Months"
    if period == "last_6_months":
        return (today - dt.timedelta(days=179)).isoformat(), today.isoformat(), "Last 6 Months"
    if period == "this_year":
        return today.replace(month=1, day=1).isoformat(), today.isoformat(), "This Year"
    if period == "previous_year":
        y = today.year - 1
        return f"{y}-01-01", f"{y}-12-31", "Previous Year"
    if period == "custom" and custom_start and custom_end:
        return custom_start[:10], custom_end[:10], f"{custom_start[:10]} to {custom_end[:10]}"
    # lifetime
    return "1970-01-01", today.isoformat(), "Lifetime (Since Monitoring Started)"


def query_period_analytics(
    db: NetscopeDB,
    period: str = "last_30_days",
    custom_start: str | None = None,
    custom_end: str | None = None,
    exclude_loopback: bool = True,
    iface_filter: str | None = None,
) -> dict[str, Any]:
    start_date, end_date, label = resolve_date_range(period, custom_start, custom_end)
    where_clauses = ["local_date >= ?", "local_date <= ?"]
    params: list[Any] = [start_date, end_date]

    if exclude_loopback:
        where_clauses.append("is_loopback = 0")
    if iface_filter and iface_filter != "all":
        where_clauses.append("iface = ?")
        params.append(iface_filter)

    where_sql = " AND ".join(where_clauses)

    with db.connect() as conn:
        daily_rows = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT local_date,
                       SUM(rx_bytes) AS rx_bytes,
                       SUM(tx_bytes) AS tx_bytes,
                       SUM(rx_bytes + tx_bytes) AS total_bytes,
                       GROUP_CONCAT(DISTINCT measurement_source) AS sources
                FROM daily_interface_usage
                WHERE {where_sql}
                GROUP BY local_date
                ORDER BY local_date ASC
                """,
                params,
            ).fetchall()
        ]

        iface_rows = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT iface,
                       iface_type,
                       SUM(rx_bytes) AS rx_bytes,
                       SUM(tx_bytes) AS tx_bytes,
                       SUM(rx_bytes + tx_bytes) AS total_bytes,
                       MAX(is_vpn) AS is_vpn
                FROM daily_interface_usage
                WHERE {where_sql}
                GROUP BY iface, iface_type
                ORDER BY total_bytes DESC
                """,
                params,
            ).fetchall()
        ]

        app_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT app_id,
                       app_name,
                       MAX(exe_path) AS exe_path,
                       MAX(owner) AS owner,
                       SUM(COALESCE(rx_bytes, 0)) AS rx_bytes,
                       SUM(COALESCE(tx_bytes, 0)) AS tx_bytes,
                       MAX(bytes_available) AS bytes_available,
                       MAX(active_sockets) AS peak_sockets,
                       MAX(last_active_ts) AS last_active_ts,
                       MAX(measurement_source) AS measurement_source
                FROM app_usage_daily
                WHERE local_date >= ? AND local_date <= ?
                GROUP BY app_id, app_name
                ORDER BY bytes_available DESC, (SUM(COALESCE(rx_bytes, 0)) + SUM(COALESCE(tx_bytes, 0))) DESC, peak_sockets DESC
                """,
                (start_date, end_date),
            ).fetchall()
        ]

        # Previous period comparison (only for bounded non-lifetime periods)
        prev_total = None
        if period != "lifetime":
            d0 = dt.date.fromisoformat(start_date)
            d1 = dt.date.fromisoformat(end_date)
            span = (d1 - d0).days + 1
            p_end = d0 - dt.timedelta(days=1)
            p_start = p_end - dt.timedelta(days=span - 1)
            p_params = [p_start.isoformat(), p_end.isoformat()]
            p_where = ["local_date >= ?", "local_date <= ?"]
            if exclude_loopback:
                p_where.append("is_loopback = 0")
            if iface_filter and iface_filter != "all":
                p_where.append("iface = ?")
                p_params.append(iface_filter)
            prev_row = conn.execute(
                f"SELECT SUM(rx_bytes + tx_bytes) AS tot FROM daily_interface_usage WHERE {' AND '.join(p_where)}",
                p_params,
            ).fetchone()
            if prev_row and prev_row["tot"] is not None and prev_row["tot"] > 0:
                prev_total = int(prev_row["tot"])

    total_rx = sum(r["rx_bytes"] for r in daily_rows)
    total_tx = sum(r["tx_bytes"] for r in daily_rows)
    total_combined = total_rx + total_tx
    active_days = len(daily_rows)
    avg_daily = round(total_combined / active_days, 2) if active_days > 0 else 0.0
    highest_day = max(daily_rows, key=lambda r: r["total_bytes"]) if daily_rows else None

    top_app = None
    measured_apps = [a for a in app_rows if a["bytes_available"]]
    if measured_apps:
        top_app = measured_apps[0]
    elif app_rows:
        top_app = {**app_rows[0], "note": "Ranked by socket activity; per-process byte totals unavailable"}

    pct_change = None
    if prev_total and prev_total > 0:
        pct_change = round(((total_combined - prev_total) / prev_total) * 100.0, 2)

    return {
        "period": period,
        "label": label,
        "start_date": start_date,
        "end_date": end_date,
        "summary": {
            "total_rx_bytes": total_rx,
            "total_tx_bytes": total_tx,
            "total_bytes": total_combined,
            "active_days": active_days,
            "daily_average_bytes": avg_daily,
            "highest_day": highest_day,
            "most_consuming_app": top_app,
            "previous_period_bytes": prev_total,
            "percent_change_vs_previous": pct_change,
        },
        "daily_series": daily_rows,
        "by_interface": iface_rows,
        "by_application": app_rows,
    }


def query_dashboard_state(db: NetscopeDB, live_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble full structured dashboard data from real SQLite & live daemon state."""
    settings = db.get_settings()
    exclude_loopback = settings.get("exclude_loopback", "true") == "true"
    today_str = local_date_str()
    caps = detect_capabilities().to_dict()

    with db.connect() as conn:
        # Recent 120 samples for live graph
        samples = [
            dict(r)
            for r in conn.execute(
                """
                SELECT ts_utc, iface, iface_type, rx_delta, tx_delta, rx_rate_bps, tx_rate_bps, is_loopback, is_vpn
                FROM interface_samples
                ORDER BY id DESC
                LIMIT 360
                """
            ).fetchall()
        ]

        # Aggregate live series per timestamp excluding loopback if enabled
        ts_buckets: dict[str, dict[str, Any]] = {}
        for s in reversed(samples):
            if exclude_loopback and s["is_loopback"]:
                continue
            ts = s["ts_utc"]
            if ts not in ts_buckets:
                ts_buckets[ts] = {"ts_utc": ts, "rx_rate_bps": 0.0, "tx_rate_bps": 0.0, "rx_delta": 0, "tx_delta": 0}
            ts_buckets[ts]["rx_rate_bps"] += float(s["rx_rate_bps"])
            ts_buckets[ts]["tx_rate_bps"] += float(s["tx_rate_bps"])
            ts_buckets[ts]["rx_delta"] += int(s["rx_delta"])
            ts_buckets[ts]["tx_delta"] += int(s["tx_delta"])
        speed_series = list(ts_buckets.values())[-90:]

        # Interfaces current state + historical totals
        iface_states = [
            dict(r)
            for r in conn.execute("SELECT * FROM interface_state ORDER BY iface ASC").fetchall()
        ]
        iface_hist = {
            r["iface"]: {"rx_bytes": r["rx_bytes"], "tx_bytes": r["tx_bytes"]}
            for r in conn.execute(
                "SELECT iface, SUM(rx_bytes) AS rx_bytes, SUM(tx_bytes) AS tx_bytes FROM daily_interface_usage GROUP BY iface"
            ).fetchall()
        }

        # Latest rates per iface
        latest_rates: dict[str, tuple[float, float]] = {}
        for s in samples:
            if s["iface"] not in latest_rates:
                latest_rates[s["iface"]] = (float(s["rx_rate_bps"]), float(s["tx_rate_bps"]))

        interfaces_out = []
        for st in iface_states:
            rx_bps, tx_bps = latest_rates.get(st["iface"], (0.0, 0.0))
            hist = iface_hist.get(st["iface"], {"rx_bytes": 0, "tx_bytes": 0})
            interfaces_out.append(
                {
                    "iface": st["iface"],
                    "iface_type": st["iface_type"],
                    "status": st["status"],
                    "ip_addresses": json.loads(st["ip_addresses"] or "[]"),
                    "mac_address": st["mac_address"],
                    "mtu": st["mtu"],
                    "boot_rx_bytes": st["boot_rx_bytes"],
                    "boot_tx_bytes": st["boot_tx_bytes"],
                    "recorded_rx_bytes": hist["rx_bytes"],
                    "recorded_tx_bytes": hist["tx_bytes"],
                    "rx_rate_bps": round(rx_bps, 2),
                    "tx_rate_bps": round(tx_bps, 2),
                    "updated_at": st["updated_at"],
                }
            )

        # Applications live snapshot
        app_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT * FROM app_socket_snapshots
                ORDER BY CASE WHEN status = 'running' THEN 0 ELSE 1 END,
                         COALESCE(total_rx_bytes, 0) DESC,
                         active_sockets DESC,
                         app_name ASC
                """
            ).fetchall()
        ]
        applications_out = []
        for a in app_rows:
            applications_out.append(
                {
                    "app_id": a["app_id"],
                    "app_name": a["app_name"],
                    "exe_path": a["exe_path"],
                    "owner": a["owner"],
                    "pids": json.loads(a["pids_json"] or "[]"),
                    "status": a["status"],
                    "active_sockets": a["active_sockets"],
                    "tcp_established": a["tcp_established"],
                    "udp_active": a["udp_active"],
                    "lan_sockets": a["lan_sockets"],
                    "internet_sockets": a["internet_sockets"],
                    "rx_rate_bps": a["rx_rate_bps"],
                    "tx_rate_bps": a["tx_rate_bps"],
                    "total_rx_bytes": a["total_rx_bytes"],
                    "total_tx_bytes": a["total_tx_bytes"],
                    "bytes_available": bool(a["bytes_available"]),
                    "measurement_source": a["measurement_source"],
                    "connections": json.loads(a["connections_json"] or "[]"),
                    "interfaces": json.loads(a["interfaces_json"] or "[]"),
                    "last_active_ts": a["last_active_ts"],
                }
            )

        # Browser tabs
        browser_tabs = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM browser_tabs ORDER BY is_active DESC, rx_bytes DESC, last_active_ts DESC"
            ).fetchall()
        ]

        # Network events
        events = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM network_events ORDER BY id DESC LIMIT 40"
            ).fetchall()
        ]

        # Data limits & alerts
        limits = [
            dict(r) for r in conn.execute("SELECT * FROM data_limits ORDER BY id DESC").fetchall()
        ]
        alerts = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM alert_events ORDER BY id DESC LIMIT 40"
            ).fetchall()
        ]

        # Historical imports
        imports = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM historical_imports ORDER BY id DESC"
            ).fetchall()
        ]

    # Period summaries for Overview
    today_summary = query_period_analytics(db, "today", exclude_loopback=exclude_loopback)
    week_summary = query_period_analytics(db, "last_7_days", exclude_loopback=exclude_loopback)
    month_summary = query_period_analytics(db, "this_month", exclude_loopback=exclude_loopback)
    lifetime_summary = query_period_analytics(db, "lifetime", exclude_loopback=exclude_loopback)

    # Enrich data limits with live consumption percentage
    limits_enriched = []
    for lim in limits:
        p = lim["period_type"]
        if p == "daily":
            consumed = today_summary["summary"]["total_bytes"]
        elif p == "weekly":
            consumed = week_summary["summary"]["total_bytes"]
        elif p == "monthly":
            consumed = month_summary["summary"]["total_bytes"]
        else:
            start_c = (now_local().date() - dt.timedelta(days=max(1, lim["custom_days"]) - 1)).isoformat()
            custom_res = query_period_analytics(db, "custom", start_c, today_str, exclude_loopback=exclude_loopback)
            consumed = custom_res["summary"]["total_bytes"]
        pct = round((consumed / lim["limit_bytes"]) * 100.0, 2) if lim["limit_bytes"] > 0 else 0.0
        limits_enriched.append(
            {
                **lim,
                "consumed_bytes": consumed,
                "percent_used": pct,
            }
        )

    cur_rx_bps = sum(
        i["rx_rate_bps"]
        for i in interfaces_out
        if not (exclude_loopback and i["iface_type"] == "loopback")
    )
    cur_tx_bps = sum(
        i["tx_rate_bps"]
        for i in interfaces_out
        if not (exclude_loopback and i["iface_type"] == "loopback")
    )

    active_non_lo = [
        i for i in interfaces_out if i["iface_type"] != "loopback" and i["status"] == "up"
    ]
    vpn_connected = any(i["iface_type"] == "vpn" and i["status"] == "up" for i in interfaces_out)

    return {
        "status": {
            "monitoring_paused": settings.get("monitoring_paused", "false") == "true",
            "privacy_mode": settings.get("privacy_mode", "false") == "true",
            "connected": len(active_non_lo) > 0,
            "vpn_connected": vpn_connected,
            "active_interfaces": [i["iface"] for i in active_non_lo],
            "current_rx_rate_bps": round(cur_rx_bps, 2),
            "current_tx_rate_bps": round(cur_tx_bps, 2),
            "daemon_alive": live_state.get("daemon_alive", True) if live_state else True,
            "last_sample_ts": live_state.get("ts_utc") if live_state else (speed_series[-1]["ts_utc"] if speed_series else None),
        },
        "capabilities": caps,
        "settings": settings,
        "db_integrity": db.integrity_check(),
        "overview": {
            "today": today_summary["summary"],
            "last_7_days": week_summary["summary"],
            "this_month": month_summary["summary"],
            "lifetime": lifetime_summary["summary"],
            "today_by_interface": today_summary["by_interface"],
        },
        "speed_series": speed_series,
        "interfaces": interfaces_out,
        "applications": applications_out,
        "browser_tabs": browser_tabs,
        "network_events": events,
        "limits": limits_enriched,
        "alerts": alerts,
        "historical_imports": imports,
    }
