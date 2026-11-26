"""End-to-end verification tests for NETSCOPE real monitoring engine."""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from netscope.analytics import (
    query_dashboard_state,
    query_period_analytics,
    resolve_custom_limit_range,
)
from netscope.capabilities import detect_capabilities
from netscope.daemon import MonitorEngine
from netscope.db import NetscopeDB
from netscope.exporter import export_csv, export_json, export_pdf
from netscope.history_importer import run_historical_import
from netscope.ipc_worker import handle_request
from netscope.proc_monitor import (
    _read_ss_tcp_info_bytes,
    classify_interface_type,
    is_lan_or_local_ip,
    read_proc_net_dev,
)


class NetscopeTestSuite(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_netscope.db")
        self.db = NetscopeDB(self.db_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_real_proc_net_dev_and_classification(self) -> None:
        ifaces = read_proc_net_dev()
        self.assertGreater(len(ifaces), 0)
        names = [i.iface for i in ifaces]
        self.assertIn("lo", names)
        self.assertEqual(classify_interface_type("lo"), "loopback")
        self.assertEqual(classify_interface_type("wlan0"), "wifi")
        self.assertEqual(classify_interface_type("wg0"), "vpn")
        self.assertEqual(classify_interface_type("docker0"), "virtual")
        self.assertEqual(classify_interface_type("eth1", "none"), "ethernet")
        self.assertTrue(is_lan_or_local_ip("192.168.1.50"))
        self.assertTrue(is_lan_or_local_ip("127.0.0.1"))
        self.assertFalse(is_lan_or_local_ip("8.8.8.8"))

    def test_ss_tcp_info_parser_uses_local_and_peer_columns(self) -> None:
        sample = (
            "State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
            "ESTAB 0 0 192.168.1.20:43122 93.184.216.34:443\n"
            " cubic wscale:7,7 bytes_acked:9876 bytes_received:5432\n"
        )
        completed = SimpleNamespace(returncode=0, stderr="", stdout=sample)
        with patch("netscope.proc_monitor.shutil.which", return_value="/usr/bin/ss"):
            with patch("netscope.proc_monitor.subprocess.run", return_value=completed):
                counters = _read_ss_tcp_info_bytes()
        self.assertEqual(counters, {
            ("192.168.1.20", 43122, "93.184.216.34", 443): (5432, 9876)
        })

    def test_aggregate_usage_excludes_vpn_virtual_and_loopback(self) -> None:
        from netscope.db import local_date_str

        today = local_date_str()
        with self.db.connect() as conn:
            rows = [
                ("wlan0", "wifi", 100, 50, 0, 0),
                ("tun0", "vpn", 200, 100, 0, 1),
                ("veth123", "virtual", 300, 150, 0, 0),
                ("lo", "loopback", 400, 200, 1, 0),
            ]
            for iface, iface_type, rx, tx, loopback, vpn in rows:
                conn.execute(
                    """
                    INSERT INTO daily_interface_usage (
                        local_date, iface, iface_type, rx_bytes, tx_bytes,
                        is_loopback, is_vpn, measurement_source, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'test', '2026-01-01T00:00:00+00:00')
                    """,
                    (today, iface, iface_type, rx, tx, loopback, vpn),
                )
            conn.commit()

        aggregate = query_period_analytics(self.db, "today")
        self.assertEqual(aggregate["summary"]["total_rx_bytes"], 100)
        self.assertEqual(aggregate["summary"]["total_tx_bytes"], 50)

        tunnel = query_period_analytics(self.db, "today", iface_filter="tun0")
        self.assertEqual(tunnel["summary"]["total_bytes"], 300)

    def test_custom_allowance_period_is_stable_until_cycle_rollover(self) -> None:
        limit = {
            "id": 7,
            "custom_days": 30,
            "created_at": "2026-11-01T12:00:00+00:00",
        }
        start1, end1, key1 = resolve_custom_limit_range(limit, dt.date(2026, 11, 26))
        start2, end2, key2 = resolve_custom_limit_range(limit, dt.date(2026, 11, 30))
        start3, end3, key3 = resolve_custom_limit_range(limit, dt.date(2026, 12, 1))
        self.assertEqual(start1, "2026-11-01")
        self.assertEqual(key1, key2)
        self.assertEqual(end1, "2026-11-26")
        self.assertEqual(end2, "2026-11-30")
        self.assertNotEqual(key2, key3)
        self.assertEqual(start3, "2026-12-01")

    def test_daemon_starts_with_fresh_interface_baseline(self) -> None:
        engine = MonitorEngine(self.db)
        self.assertEqual(engine.prev_iface_bytes, {})
        self.assertEqual(engine.prev_iface_status, {})

    def test_capabilities_probe(self) -> None:
        caps = detect_capabilities()
        self.assertTrue(caps.proc_net_dev)
        self.assertTrue(caps.proc_net_sockets)
        self.assertIsInstance(caps.limitations, list)

    def test_daemon_step_and_sqlite_persistence(self) -> None:
        run_historical_import(self.db, force=False)
        engine = MonitorEngine(self.db)
        out1 = engine.step()
        out2 = engine.step()
        self.assertTrue(out1["daemon_alive"])
        self.assertTrue(out2["daemon_alive"])

        integrity = self.db.integrity_check()
        self.assertTrue(integrity["ok"])

        state = query_dashboard_state(self.db)
        self.assertGreater(len(state["interfaces"]), 0)
        self.assertGreater(len(state["historical_imports"]), 0)
        self.assertTrue(
            any("unavailable before NETSCOPE installation" in r["notes"] for r in state["historical_imports"])
        )

    def test_exports_and_ipc_roundtrip(self) -> None:
        engine = MonitorEngine(self.db)
        engine.step()

        csv_out = export_csv(self.db, "complete")
        self.assertIn("NETSCOPE Network Usage Report", csv_out)

        json_out = json.loads(export_json(self.db, "complete"))
        self.assertEqual(json_out["application"], "NETSCOPE")

        pdf_bytes = export_pdf(self.db, "complete")
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
        self.assertIn(b"%%EOF", pdf_bytes)

        # Browser telemetry IPC test
        res = handle_request(
            self.db,
            {
                "action": "browser_telemetry",
                "params": {
                    "tabs": [
                        {
                            "browser_name": "Brave",
                            "tab_id": "42",
                            "tab_title": "Test Tab",
                            "domain": "example.org",
                            "is_active": True,
                            "rx_delta_bytes": 2048,
                            "tx_delta_bytes": 512,
                        }
                    ]
                },
            },
        )
        self.assertTrue(res["accepted"])
        dash = query_dashboard_state(self.db)
        self.assertEqual(len(dash["browser_tabs"]), 1)
        self.assertEqual(dash["browser_tabs"][0]["accuracy_label"], "browser_reported_estimate")

        # Period query test
        period_res = query_period_analytics(self.db, "today")
        self.assertEqual(period_res["period"], "today")


if __name__ == "__main__":
    unittest.main()
