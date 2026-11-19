#!/usr/bin/env python3
"""NETSCOPE Native Messaging Host for Chromium/Chrome/Brave/Edge/Firefox."""

from __future__ import annotations

import json
import os
import struct
import sys

# Ensure project root is importable when launched by browser
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from netscope.db import NetscopeDB, now_utc_iso  # noqa: E402


def read_message() -> dict | None:
    raw_len = sys.stdin.buffer.read(4)
    if len(raw_len) < 4:
        return None
    msg_len = struct.unpack("<I", raw_len)[0]
    if msg_len == 0 or msg_len > 4 * 1024 * 1024:
        return None
    payload = sys.stdin.buffer.read(msg_len)
    if len(payload) < msg_len:
        return None
    return json.loads(payload.decode("utf-8"))


def send_message(obj: dict) -> None:
    encoded = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def main() -> int:
    db = NetscopeDB()
    while True:
        msg = read_message()
        if msg is None:
            break
        try:
            tabs = msg.get("tabs", [])
            settings = db.get_settings()
            if settings.get("privacy_mode") == "true" or settings.get("browser_telemetry_enabled") != "true":
                send_message({"ok": False, "reason": "disabled_or_privacy_mode"})
                continue

            now_iso = now_utc_iso()
            with db.connect() as conn:
                for t in tabs:
                    browser_name = str(t.get("browser_name", "Browser"))
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
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'browser_reported_estimate', 'native_messaging_webrequest', ?)
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
                            now_iso,
                        ),
                    )
                conn.commit()
            send_message({"ok": True, "recorded": len(tabs)})
        except Exception as exc:
            send_message({"ok": False, "error": str(exc)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
