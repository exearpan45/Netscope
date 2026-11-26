#!/usr/bin/env python3
"""NETSCOPE Native Linux Desktop GUI & System Tray Application (PyQt6)."""

from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from netscope.analytics import query_dashboard_state, query_period_analytics  # noqa: E402
from netscope.db import NetscopeDB  # noqa: E402
from netscope.exporter import export_csv, export_json, export_pdf  # noqa: E402

try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QAction, QIcon
    from PyQt6.QtWidgets import (
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
        "PyQt6 is required for the native Qt desktop GUI. Install python3-pyqt6.\\n"
        f"Import error: {exc}\\n"
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
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(248)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 16, 12, 16)

        brand = QLabel("◈  NETSCOPE")
        brand.setObjectName("brand")
        sb_layout.addWidget(brand)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navigation")
        self.nav_list.addItems(SIDEBAR_PAGES)
        self.nav_list.setCurrentRow(0)
        sb_layout.addWidget(self.nav_list)
        main_layout.addWidget(sidebar)

        # Content column
        right_col = QWidget()
        right_col.setObjectName("content")
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(20, 16, 20, 16)

        # Top telemetry bar
        top_bar = QHBoxLayout()
        self.status_lbl = QLabel("●  Connecting...")
        self.status_lbl.setObjectName("connectionStatus")
        self.dl_lbl = QLabel("↓  0 B/s")
        self.dl_lbl.setObjectName("downloadRate")
        self.ul_lbl = QLabel("↑  0 B/s")
        self.ul_lbl.setObjectName("uploadRate")
        self.pause_btn = QPushButton("Ⅱ  Pause")
        self.pause_btn.setObjectName("secondaryButton")
        self.pause_btn.clicked.connect(self.toggle_pause)
        export_btn = QPushButton("⇩  Export report")
        export_btn.setObjectName("primaryButton")
        export_btn.clicked.connect(self.export_report)

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
        self.overview_lbl = QLabel("Live system telemetry, refreshed every second")
        self.overview_lbl.setObjectName("pageSubtitle")
        self.overview_lbl.setWordWrap(True)
        self.today_value = QLabel("Loading…")
        self.download_value = QLabel("Loading…")
        self.upload_value = QLabel("Loading…")
        self.lifetime_value = QLabel("Loading…")
        self.today_card = self._metric_card("TODAY'S USAGE", self.today_value, "↗", "accentBlue")
        self.download_card = self._metric_card("DOWNLOADED TODAY", self.download_value, "↓", "accentCyan")
        self.upload_card = self._metric_card("UPLOADED TODAY", self.upload_value, "↑", "accentViolet")
        self.lifetime_card = self._metric_card("LIFETIME TRAFFIC", self.lifetime_value, "◷", "accentGreen")
        self.apps_table = self._make_table(["Application", "PIDs", "Sockets", "Download", "Upload", "Source"])
        self.apps_table = self._make_table(["Application", "PIDs", "Sockets", "Download", "Upload", "Source"])
        self.ifaces_table = self._make_table(["Interface", "Type", "Status", "DL Rate", "UL Rate", "Recorded DL", "Recorded UL"])
        self.tabs_table = self._make_table(["Browser", "Tab Title", "Domain", "Download (Est.)", "Upload (Est.)", "Accuracy"])

        # Build pages
        ov_page = QWidget()
        ov_l = QVBoxLayout(ov_page)
        ov_l.setContentsMargins(4, 20, 4, 4)
        ov_l.setSpacing(18)
        page_title = QLabel("Network overview")
        page_title.setObjectName("pageTitle")
        ov_l.addWidget(page_title)
        ov_l.addWidget(self.overview_lbl)
        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        for card in (self.today_card, self.download_card, self.upload_card, self.lifetime_card):
            metrics.addWidget(card, 1)
        ov_l.addLayout(metrics)
        section_title = QLabel("Network interfaces")
        section_title.setObjectName("sectionTitle")
        ov_l.addWidget(section_title)
        ov_l.addWidget(self.ifaces_table, 1)
        self.stack.addWidget(ov_page)

        for idx in range(1, len(SIDEBAR_PAGES)):
            page = QWidget()
            pl = QVBoxLayout(page)
            title = QLabel(SIDEBAR_PAGES[idx])
            title.setObjectName("pageTitle")
            pl.addWidget(title)
            if idx == 2:
                pl.addWidget(self.apps_table)
            elif idx == 3:
                pl.addWidget(self.tabs_table)
            elif idx == 4:
                pl.addWidget(self._make_table(["Interface", "Type", "Status", "Since Boot DL", "Since Boot UL"]))
            elif idx == 9:
                self.alerts_table = self._make_table(["Time", "Limit ID", "Threshold", "Consumed", "Alert"])
                pl.addWidget(self.alerts_table)
            else:
                info = QLabel(f"Live SQLite-backed view for {SIDEBAR_PAGES[idx]}. Use the Web Dashboard on http://localhost:3000 for rich interactive SVG graphs.")
                info.setObjectName("pageSubtitle")
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
        with self.db.connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM alert_events").fetchone()
        self.last_alert_id = int(row[0] or 0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(1000)
        self.refresh_data()

    def _metric_card(self, caption: str, value: QLabel, symbol: str, accent: str) -> QFrame:
        card = QFrame()
        card.setObjectName("metricCard")
        card.setProperty("accent", accent)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        top = QHBoxLayout()
        label = QLabel(caption)
        label.setObjectName("metricCaption")
        icon = QLabel(symbol)
        icon.setObjectName("metricIcon")
        icon.setProperty("accent", accent)
        top.addWidget(label)
        top.addStretch()
        top.addWidget(icon)
        value.setObjectName("metricValue")
        layout.addLayout(top)
        layout.addWidget(value)
        return card

    def _make_table(self, headers: list[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tbl.setObjectName("dataTable")
        tbl.setAlternatingRowColors(True)
        tbl.setShowGrid(False)
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
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
        # Alert rows are persisted by the daemon. The Qt tray is the notification
        # owner while this GUI is running, preventing duplicate notify-send popups.
        new_alerts = sorted(
            (a for a in state["alerts"] if int(a["id"]) > self.last_alert_id),
            key=lambda a: int(a["id"]),
        )
        for alert in new_alerts:
            if (
                state["settings"].get("desktop_notifications", "true") == "true"
                and bool(alert.get("notify_desktop", 1))
            ):
                self.tray.showMessage(
                    "NETSCOPE Data Allowance Alert",
                    str(alert["message"]),
                )
            self.last_alert_id = max(self.last_alert_id, int(alert["id"]))

        st = state["status"]
        paused = st["monitoring_paused"]
        self.pause_btn.setText("▶  Resume" if paused else "Ⅱ  Pause")
        self.tray_pause_act.setText("Resume Monitoring" if paused else "Pause Monitoring")

        conn_text = "Connected" if st["connected"] else "Offline"
        if st["vpn_connected"]:
            conn_text += " (VPN Active)"
        if paused:
            conn_text += " [Paused]"
        self.status_lbl.setText(("●  " if st["connected"] else "○  ") + conn_text)
        dl_s = fmt_rate(st["current_rx_rate_bps"])
        ul_s = fmt_rate(st["current_tx_rate_bps"])
        self.dl_lbl.setText(f"↓  {dl_s}")
        self.ul_lbl.setText(f"↑  {ul_s}")
        self.tray.setToolTip(f"NETSCOPE | {conn_text}\nDL: {dl_s} | UL: {ul_s}")

        ov = state["overview"]
        self.overview_lbl.setText(
            f"Last 7 days  {fmt_bytes(ov['last_7_days']['total_bytes'])}     •     "
            f"This month  {fmt_bytes(ov['this_month']['total_bytes'])}"
        )
        self.today_value.setText(fmt_bytes(ov["today"]["total_bytes"]))
        self.download_value.setText(fmt_bytes(ov["today"]["total_rx_bytes"]))
        self.upload_value.setText(fmt_bytes(ov["today"]["total_tx_bytes"]))
        self.lifetime_value.setText(fmt_bytes(ov["lifetime"]["total_bytes"]))

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

        alerts = state["alerts"]
        self.alerts_table.setRowCount(len(alerts))
        for r, alert in enumerate(alerts):
            vals = [
                str(alert["created_at"]),
                str(alert["limit_id"]),
                f'{alert["threshold_pct"]}%',
                fmt_bytes(alert["consumed_bytes"]),
                str(alert["message"]),
            ]
            for c, value in enumerate(vals):
                self.alerts_table.setItem(r, c, QTableWidgetItem(value))

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
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget { color: #e6edf7; font-family: "Inter", "Noto Sans", sans-serif; font-size: 10pt; }
        QMainWindow { background: #0a1020; }
        #sidebar { background: #0d1528; border-right: 1px solid #202d45; }
        #brand { color: #f8fbff; font-size: 21pt; font-weight: 800; letter-spacing: 1px; padding: 8px 10px 22px; }
        #navigation { background: transparent; border: 0; outline: 0; padding: 4px; }
        #navigation::item { color: #9aabc4; padding: 12px 13px; margin: 3px 0; border-radius: 9px; }
        #navigation::item:hover { background: #17243b; color: #f4f8ff; }
        #navigation::item:selected { background: #173b68; color: #ffffff; font-weight: 700; border-left: 3px solid #49a6ff; }
        #content { background: #0a1020; }
        #pageTitle { color: #f4f7fc; font-size: 23pt; font-weight: 750; padding: 3px 0; }
        #pageSubtitle { color: #8ea1bd; font-size: 10pt; padding: 0 0 5px; }
        #sectionTitle { color: #e7eef9; font-size: 14pt; font-weight: 700; padding-top: 8px; }
        #metricCard { background: #111d32; border: 1px solid #22334e; border-radius: 14px; }
        #metricCard:hover { border: 1px solid #3a5c85; }
        #metricCaption { color: #8fa3bf; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
        #metricValue { color: #f5f8ff; font-size: 21pt; font-weight: 750; }
        #metricIcon { font-size: 17pt; font-weight: 700; padding: 4px 9px; border-radius: 9px; background: #1a3556; color: #69b6ff; }
        #connectionStatus, #downloadRate, #uploadRate { background: #111d32; border: 1px solid #243650; border-radius: 9px; padding: 9px 12px; color: #b9cbe3; font-weight: 600; }
        QPushButton { background: #1b2b43; color: #eaf2ff; border: 1px solid #2b405e; border-radius: 9px; padding: 9px 14px; font-weight: 650; }
        QPushButton:hover { background: #263d5d; border-color: #4c709c; }
        QPushButton:pressed { background: #13243b; }
        #primaryButton { background: #1677d2; border: 1px solid #258be9; color: white; }
        #primaryButton:hover { background: #258be9; }
        QTableWidget { background: #101a2c; alternate-background-color: #132139; border: 1px solid #22334e; border-radius: 11px; selection-background-color: #1b4b7d; selection-color: white; }
        QHeaderView::section { background: #17263d; color: #9fb4d0; border: 0; border-bottom: 1px solid #2a3d59; padding: 11px 9px; font-size: 8pt; font-weight: 700; }
        QTableWidget::item { padding: 8px; border: 0; }
        QScrollBar:vertical { background: #0c1526; width: 9px; margin: 0; }
        QScrollBar::handle:vertical { background: #304662; border-radius: 4px; min-height: 24px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QToolTip { background: #17263d; color: #f5f8ff; border: 1px solid #39516f; padding: 5px; }
    """)
    db = NetscopeDB()
    win = NetscopeWindow(db)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
