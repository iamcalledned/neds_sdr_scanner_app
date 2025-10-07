"""
app.py

Main window and controller for Ned's SDR Control UI.

This module defines UIController, the top-level Qt window that
coordinates the various control tabs (dongles, channels, sinks, logs, system).
It wires up the backend event bus to the UI and provides helper methods
used by the tabs.
"""

from __future__ import annotations
import asyncio
from typing import Optional, Any
from PyQt6 import QtWidgets, QtGui, QtCore

# Import tab implementations
from .tabs.tcp_tab import TcpTab
from .tabs.sdr_tab import SdrTab
from .tabs.sink_tab import SinkTab
from .tabs.log_tab import LogTab
from .tabs.system_tab import SystemTab

class UIController(QtWidgets.QMainWindow):
    """Top‑level application window.

    UIController constructs the main tabbed interface,
    exposes references to each tab, and subscribes to backend events.
    """

    def __init__(self, device_manager, config_manager: Optional[Any], event_bus,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.device_manager = device_manager
        self.config_manager = config_manager
        self.event_bus = event_bus

        self.setWindowTitle("Ned's SDR Control")
        self.resize(1024, 768)

        # Central tab widget
        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        # Instantiate tabs, passing self so tabs can access device_manager, log_tab, etc.
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
        if self.event_bus is not None:
            # When receivers are created or connected, refresh dongle/channel tables
            self.event_bus.subscribe("receiver_created",
                                     lambda data: self._refresh())
            self.event_bus.subscribe("receiver_connected",
                                     lambda data: self._refresh())
            # When channel presets change or signal-power updates come in, update SdrTab
            self.event_bus.subscribe("channel_presets_updated",
                                     lambda data: self.sdr_tab.refresh_table())
            self.event_bus.subscribe("signal_power", self.sdr_tab.update_signal)

    def _refresh(self):
        """Refresh UI when receivers appear or connect."""
        self.tcp_tab.refresh_table()
        self.sdr_tab.refresh_table()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Gracefully shut down the backend when the window closes."""
        if hasattr(self.device_manager, "shutdown"):
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.device_manager.shutdown())
            except RuntimeError:
                # No running loop; run shutdown synchronously
                asyncio.run(self.device_manager.shutdown())
        super().closeEvent(event)

__all__ = ["UIController"]
