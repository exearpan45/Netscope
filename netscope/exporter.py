"""Real CSV, JSON, and valid PDF 1.4 export generator for NETSCOPE."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from typing import Any

from netscope.db import NetscopeDB, now_utc_iso


def _fmt_bytes(num: int | float | None) -> str:
    if num is None:
        return "Not available"
    val = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < 1024.0 or unit == "TB":
            return f"{val:.2f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.2f} TB"


def build_export_payload(db: NetscopeDB, scope: str = "complete") -> dict[str, Any]:
    generated_at = now_utc_iso()
    with db.connect() as conn:
        daily = [
            dict(r)
            for r in conn.execute(
                "SELECT local_date, iface, iface_type, rx_bytes, tx_bytes, is_loopback, is_vpn, measurement_source, updated_at FROM daily_interface_usage ORDER BY local_date DESC, iface ASC"
            ).fetchall()
        ]
        apps = [
            dict(r)
            for r in conn.execute(
                "SELECT local_date, app_id, app_name, exe_path, owner, rx_bytes, tx_bytes, bytes_available, measurement_source, active_sockets, last_active_ts FROM app_usage_daily ORDER BY local_date DESC, app_name ASC"
            ).fetchall()
        ]
        tabs = [
            dict(r)
            for r in conn.execute(
                "SELECT browser_name, tab_id, tab_title, domain, is_active, rx_bytes, tx_bytes, accuracy_label, measurement_source, last_active_ts FROM browser_tabs ORDER BY last_active_ts DESC"
            ).fetchall()
        ]
        imports = [
            dict(r)
            for r in conn.execute(
                "SELECT source, period_label, iface, rx_bytes, tx_bytes, measurement_accuracy, measurement_type, import_status, notes, imported_at FROM historical_imports ORDER BY id DESC"
            ).fetchall()
        ]

    today_str = dt.datetime.now().astimezone().strftime("%Y-%m-%d")
    if scope == "daily":
        daily = [d for d in daily if d["local_date"] == today_str]
        apps = [a for a in apps if a["local_date"] == today_str]
    elif scope == "weekly":
        cutoff = (dt.datetime.now().astimezone() - dt.timedelta(days=7)).strftime("%Y-%m-%d")
        daily = [d for d in daily if d["local_date"] >= cutoff]
        apps = [a for a in apps if a["local_date"] >= cutoff]
    elif scope == "monthly":
        cutoff = (dt.datetime.now().astimezone() - dt.timedelta(days=30)).strftime("%Y-%m-%d")
        daily = [d for d in daily if d["local_date"] >= cutoff]
        apps = [a for a in apps if a["local_date"] >= cutoff]
    elif scope == "applications":
        daily = []
    elif scope == "browser":
        daily = []
        apps = []

    return {
        "application": "NETSCOPE",
        "scope": scope,
        "generated_at_utc": generated_at,
        "daily_interface_usage": daily,
        "application_usage": apps,
        "browser_telemetry": tabs,
        "historical_imports": imports,
    }


def export_csv(db: NetscopeDB, scope: str = "complete") -> str:
    payload = build_export_payload(db, scope)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["# NETSCOPE Network Usage Report", f"Scope={scope}", f"GeneratedUTC={payload['generated_at_utc']}"])
    writer.writerow([])

    if payload["daily_interface_usage"]:
        writer.writerow(["Section", "Date", "Interface", "Type", "Download_Bytes", "Upload_Bytes", "Total_Bytes", "Loopback", "VPN", "Measurement_Source"])
        for row in payload["daily_interface_usage"]:
            writer.writerow([
                "interface_usage",
                row["local_date"],
                row["iface"],
                row["iface_type"],
                row["rx_bytes"],
                row["tx_bytes"],
                row["rx_bytes"] + row["tx_bytes"],
                bool(row["is_loopback"]),
                bool(row["is_vpn"]),
                row["measurement_source"],
            ])
        writer.writerow([])

    if payload["application_usage"]:
        writer.writerow(["Section", "Date", "App", "Executable", "Owner", "Download_Bytes", "Upload_Bytes", "Bytes_Available", "Active_Sockets", "Measurement_Source", "Last_Active_UTC"])
        for row in payload["application_usage"]:
            writer.writerow([
                "application_usage",
                row["local_date"],
                row["app_name"],
                row["exe_path"],
                row["owner"],
                row["rx_bytes"] if row["bytes_available"] else "unavailable",
                row["tx_bytes"] if row["bytes_available"] else "unavailable",
                bool(row["bytes_available"]),
                row["active_sockets"],
                row["measurement_source"],
                row["last_active_ts"],
            ])
        writer.writerow([])

    if payload["browser_telemetry"]:
        writer.writerow(["Section", "Browser", "Tab_ID", "Title", "Domain", "Download_Bytes", "Upload_Bytes", "Accuracy_Label", "Source", "Last_Active_UTC"])
        for row in payload["browser_telemetry"]:
            writer.writerow([
                "browser_tab",
                row["browser_name"],
                row["tab_id"],
                row["tab_title"],
                row["domain"],
                row["rx_bytes"],
                row["tx_bytes"],
                row["accuracy_label"],
                row["measurement_source"],
                row["last_active_ts"],
            ])

    return buf.getvalue()


def export_json(db: NetscopeDB, scope: str = "complete") -> str:
    return json.dumps(build_export_payload(db, scope), indent=2)


def _pdf_escape(text: str) -> str:
    ascii_safe = text.encode("latin-1", errors="replace").decode("latin-1")
    return ascii_safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def export_pdf(db: NetscopeDB, scope: str = "complete") -> bytes:
    """Generate a valid multi-line PDF 1.4 report using standard Type1 Helvetica & Courier."""
    payload = build_export_payload(db, scope)
    lines: list[str] = [
        "NETSCOPE - LINUX NETWORK INTELLIGENCE REPORT",
        f"Scope: {scope.upper()}   Generated (UTC): {payload['generated_at_utc']}",
        "-" * 78,
        "",
    ]

    if payload["daily_interface_usage"]:
        lines.append("SYSTEM INTERFACE USAGE (Exact Kernel /proc/net/dev Counters)")
        lines.append(f"{'Date':<12} {'Iface':<10} {'Type':<10} {'Download':>12} {'Upload':>12} {'Total':>12}")
        for r in payload["daily_interface_usage"][:30]:
            tot = r["rx_bytes"] + r["tx_bytes"]
            lines.append(
                f"{r['local_date']:<12} {r['iface'][:10]:<10} {r['iface_type'][:10]:<10} "
                f"{_fmt_bytes(r['rx_bytes']):>12} {_fmt_bytes(r['tx_bytes']):>12} {_fmt_bytes(tot):>12}"
            )
        lines.append("")

    if payload["application_usage"]:
        lines.append("APPLICATION NETWORK RECORDS")
        lines.append(f"{'Date':<12} {'Application':<22} {'Sockets':>7} {'Download':>13} {'Source'}")
        for r in payload["application_usage"][:30]:
            dl = _fmt_bytes(r["rx_bytes"]) if r["bytes_available"] else "Unavailable"
            lines.append(
                f"{r['local_date']:<12} {r['app_name'][:22]:<22} {r['active_sockets']:>7} {dl:>13} {r['measurement_source'][:18]}"
            )
        lines.append("")

    if payload["browser_telemetry"]:
        lines.append("BROWSER TAB TELEMETRY (Browser-Reported Estimates)")
        for r in payload["browser_telemetry"][:20]:
            lines.append(
                f"[{r['browser_name']}] {r['domain']} - {r['tab_title'][:28]} | DL {_fmt_bytes(r['rx_bytes'])} | {r['accuracy_label']}"
            )
        lines.append("")

    if not payload["daily_interface_usage"] and not payload["application_usage"] and not payload["browser_telemetry"]:
        lines.append("No recorded data matched the selected report scope.")

    # Paginate 48 lines per page
    pages_lines = [lines[i : i + 48] for i in range(0, max(1, len(lines)), 48)]
    objects: list[bytes] = []

    def add_obj(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog_id = add_obj(b"")  # placeholder 1
    pages_id = add_obj(b"")    # placeholder 2
    font_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    page_ids: list[int] = []
    for page_chunk in pages_lines:
        stream_cmds = ["BT", "/F1 9 Tf", "42 756 Td", "14 TL"]
        for line in page_chunk:
            stream_cmds.append(f"({_pdf_escape(line)}) Tj T*")
        stream_cmds.append("ET")
        stream_bytes = "\n".join(stream_cmds).encode("latin-1")
        content_id = add_obj(
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream"
        )
        page_id = add_obj(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode(
                "ascii"
            )
        )
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii")
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for idx, obj_body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj_body)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)
