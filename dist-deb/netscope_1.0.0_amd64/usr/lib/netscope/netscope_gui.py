#!/usr/bin/env python3
"""NETSCOPE Native Linux Desktop GUI & System Tray Application (PySide6)."""

from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from netscope.analytics import query_dashboard_state, query_period_analytics  # noqa: E402
from netscope.db import NetscopeDB  # noqa: E402
from netscope.exporter import export_csv, export_json, export_pdf  # noqa: E402

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QStackedWidget,
        QSystemTrayIcon,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
        QMenu,
    )
except ImportError as exc:
    sys.stderr.write(
        "PySide6 is required for the native Qt desktop GUI. Install python3-pyside6 or pip install PySide6.\n"
        f"Import error: {exc}\n"
    )
    raise SystemExit(1)


def fmt_bytes(val: int | float | None) -> str:
    if val is None:
        return "Not available"
    num = float(val)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0 or unit == "TB":
            return f"{num:.2f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return f"{num:.2f} TB"


def fmt_rate(bps: float | None) -> str:
    if bps is None:
        return "Unavailable"
    return f"{fmt_bytes(bps)}/s"


SIDEBAR_PAGES = [
    "Overview",
    "Live Monitor",
    "Applications",
    "Browser Tracking",
    "Network Interfaces",
    "Daily Usage",
    "Weekly Usage",
    "Monthly Usage",
    "Historical Analytics",
    "Data Limits",
    "Settings",
    "About NETSCOPE",
]


class NetscopeWindow(QMainWindow):
    def __init__(self, db: NetscopeDB) -> None:
        super().__init__()
        self.db = db
        self.setWindowTitle("NETSCOPE — Complete Network Intelligence for Linux")
        self.resize(1280, 820)

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet("background: #0f172a; color: #e2e8f0; border-right: 1px solid #1e293b;")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 16, 12, 16)

        brand = QLabel("NETSCOPE")
        brand.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff; padding: 4px 8px;")
        sb_layout.addWidget(brand)

        self.nav_list = QListWidget()
        self.nav_list.addItems(SIDEBAR_PAGES)
        self.nav_list.setCurrentRow(0)
        self.nav_list.setStyleSheet(
            "QListWidget { border: none; background: transparent; outline: none; }"
            "QListWidget::item { padding: 9px 10px; border-radius: 6px; margin-bottom: 2px; }"
            "QListWidget::item:selected { background: #0284c7; color: #ffffff; font-weight: 600; }"
        )
        sb_layout.addWidget(self.nav_list)
        main_layout.addWidget(sidebar)

        # Content column
        right_col = QWidget()
        right_col.setStyleSheet("background: #0b1120; color: #f1f5f9;")
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(20, 16, 20, 16)

        # Top telemetry bar
        top_bar = QHBoxLayout()
        self.status_lbl = QLabel("Connecting...")
        self.dl_lbl = QLabel("DL: 0 B/s")
        self.ul_lbl = QLabel("UL: 0 B/s")
        self.pause_btn = QPushButton("Pause Monitoring")
        self.pause_btn.clicked.connect(self.toggle_pause)
        export_btn = QPushButton("Export Report")
        export_btn.clicked.connect(self.export_report)

        for lbl in (self.status_lbl, self.dl_lbl, self.ul_lbl):
            lbl.setStyleSheet("font-family: monospace; font-size: 13px; color: #cbd5e1;")

        top_bar.addWidget(self.status_lbl)
        top_bar.addStretch()
        top_bar.addWidget(self.dl_lbl)
        top_bar.addSpacing(16)
        top_bar.addWidget(self.ul_lbl)
        top_bar.addSpacing(16)
        top_bar.addWidget(self.pause_btn)
        top_bar.addWidget(export_btn)
        right_layout.addLayout(top_bar)

        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack)

        # Overview Table & Summary
        self.overview_lbl = QLabel("Loading real kernel telemetry...")
        self.overview_lbl.setWordWrap(True)
        self.overview_lbl.setStyleSheet("font-size: 14px; padding: 12px; background: #111827; border: 1px solid #1e293b; border-radius: 8px;")
        self.apps_table = self._make_table(["Application", "PIDs", "Sockets", "Download", "Upload", "Source"])
        self.ifaces_table = self._make_table(["Interface", "Type", "Status", "DL Rate", "UL Rate", "Recorded DL", "Recorded UL"])
        self.tabs_table = self._make_table(["Browser", "Tab Title", "Domain", "Download (Est.)", "Upload (Est.)", "Accuracy"])

        # Build pages
        ov_page = QWidget()
        ov_l = QVBoxLayout(ov_page)
        ov_l.addWidget(self.overview_lbl)
        ov_l.addWidget(self.ifaces_table)
        self.stack.addWidget(ov_page)

        for idx in range(1, len(SIDEBAR_PAGES)):
            page = QWidget()
            pl = QVBoxLayout(page)
            title = QLabel(SIDEBAR_PAGES[idx])
            title.setStyleSheet("font-size: 18px; font-weight: 700; margin-bottom: 8px;")
            pl.addWidget(title)
            if idx == 2:
                pl.addWidget(self.apps_table)
            elif idx == 3:
                pl.addWidget(self.tabs_table)
            elif idx == 4:
                pl.addWidget(self._make_table(["Interface", "Type", "Status", "Since Boot DL", "Since Boot UL"]))
            else:
                info = QLabel(f"Live SQLite-backed view for {SIDEBAR_PAGES[idx]}. Use the Web Dashboard on http://localhost:3000 for rich interactive SVG graphs.")
                info.setWordWrap(True)
                pl.addWidget(info)
            self.stack.addWidget(page)

        self.nav_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        main_layout.addWidget(right_col)

        # System Tray Integration
        self.tray = QSystemTrayIcon(self)
        icon_path = "/usr/share/icons/hicolor/scalable/apps/netscope.svg"
        if os.path.exists(icon_path):
            self.tray.setIcon(QIcon(icon_path))
        else:
            self.tray.setIcon(QIcon.fromTheme("network-transmit-receive"))
        tray_menu = QMenu()
        open_act = QAction("Open NETSCOPE", self)
        open_act.triggered.connect(self.showNormal)
        self.tray_pause_act = QAction("Pause Monitoring", self)
        self.tray_pause_act.triggered.connect(self.toggle_pause)
        quit_act = QAction("Quit NETSCOPE", self)
        quit_act.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(open_act)
        tray_menu.addAction(self.tray_pause_act)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_act)
        self.tray.setContextMenu(tray_menu)
        self.tray.show()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(1000)
        self.refresh_data()

    def _make_table(self, headers: list[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.setStyleSheet("QTableWidget { background: #111827; gridline-color: #1e293b; border: 1px solid #1e293b; }")
        return tbl

    def toggle_pause(self) -> None:
        settings = self.db.get_settings()
        cur = settings.get("monitoring_paused", "false") == "true"
        self.db.update_setting("monitoring_paused", "false" if cur else "true")
        self.refresh_data()

    def export_report(self) -> None:
        path, selected = QFileDialog.getSaveFileName(
            self, "Export NETSCOPE Report", "netscope-report.csv", "CSV (*.csv);;JSON (*.json);;PDF (*.pdf)"
        )
        if not path:
            return
        if path.endswith(".pdf") or "PDF" in selected:
            with open(path, "wb") as fh:
                fh.write(export_pdf(self.db, "complete"))
        elif path.endswith(".json") or "JSON" in selected:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(export_json(self.db, "complete"))
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(export_csv(self.db, "complete"))
        QMessageBox.information(self, "Export Complete", f"Saved report to {path}")

    def refresh_data(self) -> None:
        state = query_dashboard_state(self.db)
        st = state["status"]
        paused = st["monitoring_paused"]
        self.pause_btn.setText("Resume Monitoring" if paused else "Pause Monitoring")
        self.tray_pause_act.setText("Resume Monitoring" if paused else "Pause Monitoring")

        conn_text = "Connected" if st["connected"] else "Offline"
        if st["vpn_connected"]:
            conn_text += " (VPN Active)"
        if paused:
            conn_text += " [Paused]"
        self.status_lbl.setText(conn_text)
        dl_s = fmt_rate(st["current_rx_rate_bps"])
        ul_s = fmt_rate(st["current_tx_rate_bps"])
        self.dl_lbl.setText(f"DL: {dl_s}")
        self.ul_lbl.setText(f"UL: {ul_s}")
        self.tray.setToolTip(f"NETSCOPE | {conn_text}\nDL: {dl_s} | UL: {ul_s}")

        ov = state["overview"]
        self.overview_lbl.setText(
            f"Today: {fmt_bytes(ov['today']['total_bytes'])} (DL {fmt_bytes(ov['today']['total_rx_bytes'])} / UL {fmt_bytes(ov['today']['total_tx_bytes'])})\n"
            f"Last 7 Days: {fmt_bytes(ov['last_7_days']['total_bytes'])}  |  This Month: {fmt_bytes(ov['this_month']['total_bytes'])}  |  Lifetime: {fmt_bytes(ov['lifetime']['total_bytes'])}"
        )

        ifaces = state["interfaces"]
        self.ifaces_table.setRowCount(len(ifaces))
        for r, iface in enumerate(ifaces):
            vals = [
                iface["iface"],
                iface["iface_type"],
                iface["status"],
                fmt_rate(iface["rx_rate_bps"]),
                fmt_rate(iface["tx_rate_bps"]),
                fmt_bytes(iface["recorded_rx_bytes"]),
                fmt_bytes(iface["recorded_tx_bytes"]),
            ]
            for c, v in enumerate(vals):
                self.ifaces_table.setItem(r, c, QTableWidgetItem(str(v)))

        apps = state["applications"]
        self.apps_table.setRowCount(len(apps))
        for r, app in enumerate(apps):
            vals = [
                app["app_name"],
                ", ".join(str(p) for p in app["pids"]),
                str(app["active_sockets"]),
                fmt_bytes(app["total_rx_bytes"]) if app["bytes_available"] else "Not available with current capabilities",
                fmt_bytes(app["total_tx_bytes"]) if app["bytes_available"] else "Not available with current capabilities",
                app["measurement_source"],
            ]
            for c, v in enumerate(vals):
                self.apps_table.setItem(r, c, QTableWidgetItem(str(v)))


def main() -> int:
    app = QApplication(sys.argv)
    db = NetscopeDB()
    win = NetscopeWindow(db)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
