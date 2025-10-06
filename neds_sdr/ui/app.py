"""
app.py
Main GUI controller for Neds SDR Control System.
"""

import asyncio
import logging
from PyQt6 import QtWidgets, QtCore
import qasync

from neds_sdr.ui.tabs.tcp_tab import TcpTab
from neds_sdr.ui.tabs.sdr_tab import SdrTab
from neds_sdr.ui.tabs.sink_tab import SinkTab
from neds_sdr.ui.tabs.log_tab import LogTab
from neds_sdr.ui.tabs.system_tab import SystemTab

log = logging.getLogger("UIController")


class UIController(QtWidgets.QMainWindow):
    """Main window and controller for SDR Control UI."""

    def __init__(self, device_manager, config_manager, event_bus):
        super().__init__()
        self.setWindowTitle("Neds SDR Control")
        self.resize(1100, 700)
        self.device_manager = device_manager
        self.config = config_manager
        self.event_bus = event_bus


        self.setStyleSheet("""
        QWidget { background-color: #1e1e1e; color: #dcdcdc; }
        QLineEdit, QTableWidget { background-color: #252526; color: #ffffff; border: 1px solid #3c3c3c; }
        QPushButton { background-color: #007acc; border: none; color: white; padding: 6px; border-radius: 4px; }
        QPushButton:hover { background-color: #005f99; }
        QHeaderView::section { background-color: #2d2d2d; color: #ffffff; padding: 4px; }
            """)

        # Tabbed layout
        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        # Individual tabs
        self.tcp_tab = TcpTab(self)
        self.sdr_tab = SdrTab(self)
        self.sink_tab = SinkTab(self)
        self.log_tab = LogTab(self)
        self.system_tab = SystemTab(self)

        # Add tabs
        self.tabs.addTab(self.tcp_tab, "Dongles")
        self.tabs.addTab(self.sdr_tab, "Channels")
        self.tabs.addTab(self.sink_tab, "Sinks")
        self.tabs.addTab(self.log_tab, "Logs")
        self.tabs.addTab(self.system_tab, "System")

        # Subscribe to backend events
        self.event_bus.subscribe("dongle_connected", self.on_dongle_event)
        self.event_bus.subscribe("dongle_disconnected", self.on_dongle_event)
        self.event_bus.subscribe("squelch_open", self.on_squelch_event)
        self.event_bus.subscribe("squelch_closed", self.on_squelch_event)
        self.event_bus.subscribe("log_event", self.on_log_event)
        self.event_bus.subscribe("channel_added", self.on_channel_event)
        self.event_bus.subscribe("channel_removed", self.on_channel_event)
        self.event_bus.subscribe("signal_update", self.on_signal_update)


    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def on_dongle_event(self, data):
        """Handle dongle connect/disconnect events."""
        msg = f"Dongle event: {data}"
        self.log_tab.append_log(msg)

    def on_squelch_event(self, data):
        """Handle squelch open/close events."""
        msg = f"Squelch event: {data}"
        self.log_tab.append_log(msg)

    def on_channel_event(self, data):
        """Handle channel add/remove/squelch events."""
        self.sdr_tab.refresh_table()
        self.log_tab.append_log(f"[Channel] {data}")

    def on_signal_update(self, data):
        """Handle power updates from receivers."""
        self.sdr_tab.update_signal(data)


        

    def on_log_event(self, data):
        """Handle general log events."""
        self.log_tab.append_log(data.get("message", str(data)))

    # ------------------------------------------------------------------
    # Start UI Event Loop
    # ------------------------------------------------------------------

    def start(self):
        """Launch the PyQt UI integrated with asyncio."""
        loop = asyncio.get_event_loop()
        app = QtWidgets.QApplication([])
        qloop = qasync.QEventLoop(app)
        asyncio.set_event_loop(qloop)

        log.info("Starting Neds SDR Control UI.")
        with qloop:
            self.show()
            qloop.run_forever()
