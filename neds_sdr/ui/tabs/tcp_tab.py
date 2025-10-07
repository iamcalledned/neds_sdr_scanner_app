""" tcp_tab.py
Dongle management and live control interface for Neds SDR Control.
"""

from PyQt6 import QtWidgets, QtGui, QtCore
import asyncio


class TcpTab(QtWidgets.QWidget):
    """Displays SDR dongles, allows connection control and gain adjustment."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.layout = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel("Active SDR Dongles")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 8px;")
        self.layout.addWidget(title)

        # --- Table setup ---
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Host", "Port", "Gain (dB)", "Status", "Connect", "Disconnect"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.layout.addWidget(self.table)

        # --- Add Dongle Form ---
        form = QtWidgets.QHBoxLayout()
        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("Dongle name")
        self.host_input = QtWidgets.QLineEdit("127.0.0.1")
        self.port_input = QtWidgets.QLineEdit("1234")
        self.gain_input = QtWidgets.QLineEdit("30")
        add_button = QtWidgets.QPushButton("Add Dongle")
        add_button.clicked.connect(self.add_dongle)
        form.addWidget(self.name_input)
        form.addWidget(self.host_input)
        form.addWidget(self.port_input)
        form.addWidget(self.gain_input)
        form.addWidget(add_button)
        self.layout.addLayout(form)

        # Initial population
        self.refresh_table()

        # Auto refresh
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.refresh_table)
        self.timer.start(3000)

    # ------------------------------------------------------------------
    def refresh_table(self):
        """Refresh dongle list from backend."""
        dongles = self.app.device_manager.dongles
        self.table.setRowCount(len(dongles))

        for row, (name, receiver) in enumerate(dongles.items()):
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))

            # These next three fields depend on whether it's a receiver or USB info dict
            host = getattr(receiver, "host", "-")
            port = getattr(receiver, "port", "-")
            gain_val = getattr(receiver, "gain", 0)

            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(host)))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(port)))

            # Gain slider
            # Note: Using lambda with default arguments `n=name` is important for capturing the current row's name.
            gain_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            gain_slider.setMinimum(0)
            gain_slider.setMaximum(50)
            gain_slider.setValue(int(gain_val))
            gain_slider.valueChanged.connect(
                lambda val, n=name: asyncio.create_task(self.set_gain(n, val))
            )
            self.table.setCellWidget(row, 3, gain_slider)

            # Status
            running = getattr(receiver, "running", False)
            status_text = "Connected" if running else "Offline"
            status_item = QtWidgets.QTableWidgetItem(status_text)
            status_item.setForeground(QtGui.QColor("green" if running else "red"))
            self.table.setItem(row, 4, status_item)

            # Connect button
            connect_btn = QtWidgets.QPushButton("Connect")
            connect_btn.setEnabled(not running)
            connect_btn.clicked.connect(lambda _, n=name: asyncio.create_task(self.connect_dongle(n)))
            self.table.setCellWidget(row, 5, connect_btn)

            # Disconnect button
            disconnect_btn = QtWidgets.QPushButton("Disconnect")
            disconnect_btn.setEnabled(running)
            disconnect_btn.clicked.connect(lambda _, n=name: asyncio.create_task(self.disconnect_dongle(n)))
            self.table.setCellWidget(row, 6, disconnect_btn)

    # ------------------------------------------------------------------
    def add_dongle(self):
        """Add new dongle from input form."""
        name = self.name_input.text().strip()
        host = self.host_input.text().strip()
        port = int(self.port_input.text())
        gain = float(self.gain_input.text())
        self.app.log_tab.append_log(f"[UI] Adding dongle {name} ({host}:{port}) gain={gain}")
        asyncio.create_task(self.app.device_manager.add_dongle(name, host, port, gain))
        self.refresh_table()

    async def set_gain(self, name: str, gain: int):
        """Adjust gain live."""
        await self.app.device_manager.set_gain(name, gain)
        self.app.log_tab.append_log(f"[UI] Set {name} gain → {gain} dB")

    async def connect_dongle(self, name: str):
        """Connect dongle live and create a default channel."""
        d = self.app.device_manager.dongles.get(name)
        # If the receiver exists and isn't already running, connect it
        if d and not getattr(d, "running", False):
            print("awaiting to connect dongle...")
            await d.connect()
            
            # Create a default channel on connect.
            # This relies on d.add_channel() to correctly call channel.start()
            # which performs the tuning.
            await d.add_channel({
                "id": "ch0",
                "frequency": 145_500_000.0,  # 145.500 MHz
                "squelch": -50.0,
                "tone_type": None,
                "tone_value": None,
                "sink": "default",
            })
            self.app.log_tab.append_log(f"[UI] Connected dongle {name} and created ch0")
            # The incorrect print statement was removed here.
            self.refresh_table()

    async def disconnect_dongle(self, name: str):
        """Disconnect dongle live."""
        d = self.app.device_manager.dongles.get(name)
        if d and getattr(d, "running", False):
            await d.disconnect()
            self.app.log_tab.append_log(f"[UI] Disconnected dongle {name}")
            self.refresh_table()
