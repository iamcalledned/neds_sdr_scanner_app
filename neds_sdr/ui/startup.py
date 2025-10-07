"""
startup.py — SDR Device Discovery and TCP Setup (full UI)

This dialog shows:
- USB-detected SDR devices (device index + description)
- Local rtl_tcp servers discovered via TCP scan
- Buttons to Start TCP for a device or Connect to an existing TCP server

Notes:
- 'Start TCP' runs rtl_tcp as an async subprocess and updates status.
- 'Connect' creates an SDRReceiver placeholder via DeviceManager.attach_tcp and
  calls its connect() (async) so the receiver actually connects to the server.
"""

from PyQt6 import QtWidgets, QtGui, QtCore
import asyncio
import logging

log = logging.getLogger("StartupDialog")


class StartupDialog(QtWidgets.QDialog):
    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self.device_manager = device_manager
        self.setWindowTitle("Neds SDR — SDR Device Setup")
        self.setMinimumSize(900, 420)

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel("Detected RTL-SDR Devices and local rtl_tcp servers")
        header.setStyleSheet("font-size:16px; font-weight:bold; margin-bottom:6px;")
        layout.addWidget(header)

        # Split view: left = USB devices, right = TCP servers
        h = QtWidgets.QHBoxLayout()
        layout.addLayout(h)

        # Left: USB devices
        left_v = QtWidgets.QVBoxLayout()
        left_v.addWidget(QtWidgets.QLabel("USB Devices (hardware)"))
        self.usb_table = QtWidgets.QTableWidget(0, 4)
        self.usb_table.setHorizontalHeaderLabels(["Index", "Description", "Default Port", "Start TCP"])
        self.usb_table.horizontalHeader().setStretchLastSection(True)
        left_v.addWidget(self.usb_table)
        h.addLayout(left_v, 2)

        # Right: TCP servers
        right_v = QtWidgets.QVBoxLayout()
        right_v.addWidget(QtWidgets.QLabel("Local rtl_tcp servers (discovered)"))
        self.tcp_table = QtWidgets.QTableWidget(0, 4)
        self.tcp_table.setHorizontalHeaderLabels(["Port", "Device Index", "Status", "Connect"])
        self.tcp_table.horizontalHeader().setStretchLastSection(True)
        right_v.addWidget(self.tcp_table)
        h.addLayout(right_v, 1)

        # Bottom controls
        controls = QtWidgets.QHBoxLayout()
        self.rescan_btn = QtWidgets.QPushButton("Rescan Devices")
        self.rescan_btn.clicked.connect(self.rescan)
        controls.addWidget(self.rescan_btn)

        self.tcp_scan_btn = QtWidgets.QPushButton("Scan Local TCP Ports")
        self.tcp_scan_btn.clicked.connect(self.tcp_scan)
        controls.addWidget(self.tcp_scan_btn)

        self.continue_btn = QtWidgets.QPushButton("Continue to Control Panel")
        self.continue_btn.setEnabled(False)
        self.continue_btn.clicked.connect(self.accept)
        controls.addWidget(self.continue_btn)

        layout.addLayout(controls)

        # data structures mapping table rows
        self._usb_rows = {}   # device_index -> row
        self._tcp_rows = {}   # port -> row

        # initial population
        self.rescan()
        self.tcp_scan()

        # periodic update: refresh status of started processes/connected receivers
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._refresh_statuses)
        self._timer.start(2000)

    # -----------------------
    # USB detection UI
    # -----------------------
    def rescan(self):
        devices = self.device_manager.detect_sdr_devices()
        self.usb_table.setRowCount(len(devices))
        self._usb_rows.clear()

        for row, dev in enumerate(devices):
            idx = dev["index"]
            desc = dev["description"]
            self.usb_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(idx)))
            self.usb_table.setItem(row, 1, QtWidgets.QTableWidgetItem(desc))

            port_edit = QtWidgets.QLineEdit(str(1234 + idx))
            port_edit.setMaximumWidth(100)
            self.usb_table.setCellWidget(row, 2, port_edit)

            start_btn = QtWidgets.QPushButton("Start TCP")
            start_btn.clicked.connect(
                lambda _, device_index=idx, pe=port_edit: asyncio.create_task(self._start_tcp(device_index, pe))
            )
            self.usb_table.setCellWidget(row, 3, start_btn)
            self._usb_rows[idx] = row

        # update continue button state (enabled if a receiver is connected)
        self._update_continue_state()

    # -----------------------
    # TCP scan UI
    # -----------------------
    def tcp_scan(self):
        # Synchronous scan (fast) using DeviceManager.tcp_scan
        open_ports = self.device_manager.tcp_scan()
        self._populate_tcp_table(open_ports)

    def _populate_tcp_table(self, ports):
        self.tcp_table.setRowCount(len(ports))
        self._tcp_rows.clear()
        for row, port in enumerate(ports):
            self.tcp_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(port)))

            dev_idx = self.device_manager.tcp_servers.get(port, {}).get("device_index")
            self.tcp_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(dev_idx) if dev_idx is not None else "-"))

            status = self.device_manager.tcp_servers.get(port, {}).get("status", "found")
            item = QtWidgets.QTableWidgetItem(status)
            color = "green" if status in ("running", "found") else "orange"
            item.setForeground(QtGui.QColor(color))
            self.tcp_table.setItem(row, 2, item)

            connect_btn = QtWidgets.QPushButton("Connect")
            connect_btn.clicked.connect(lambda _, p=port: asyncio.create_task(self._connect_to_tcp(p)))
            self.tcp_table.setCellWidget(row, 3, connect_btn)
            self._tcp_rows[port] = row

        self._update_continue_state()

    # -----------------------
    # Start rtl_tcp and update table
    # -----------------------
    async def _start_tcp(self, device_index: int, port_edit: QtWidgets.QLineEdit):
        port = int(port_edit.text())
        # set UI immediate feedback
        row = self._usb_rows.get(device_index)
        if row is not None:
            status_item = QtWidgets.QTableWidgetItem("Starting...")
            status_item.setForeground(QtGui.QColor("orange"))
            self.usb_table.setItem(row, 2, status_item)  # temporarily show status in port col

        try:
            proc = await self.device_manager.start_rtl_tcp(device_index, port)
            # update tcp server registry and table
            self.device_manager.tcp_servers[port] = {"proc": proc, "device_index": device_index, "status": "running"}
            self.tcp_scan()  # refresh tcp table to show this new server
            log.info("StartupDialog: rtl_tcp started for device %d on port %d", device_index, port)
        except Exception as e:
            log.error("StartupDialog: Failed to start rtl_tcp: %s", e)

    # -----------------------
    # Connect to a running rtl_tcp server
    # -----------------------
    async def _connect_to_tcp(self, port: int):
        # attach a receiver object to existing tcp server and attempt to connect
        host = "127.0.0.1"
        # create receiver placeholder
        recv = self.device_manager.attach_tcp(host, port)
        if not recv:
            log.error("StartupDialog: attach_tcp failed for %s:%d", host, port)
            return

        # Connect async
        try:
            await recv.connect()
            # register in UI if connected
            # store receiver in device_manager.receivers
            # reflect connection in tcp table
            row = self._tcp_rows.get(port)
            if row is not None:
                status_item = QtWidgets.QTableWidgetItem("Connected")
                status_item.setForeground(QtGui.QColor("green"))
                self.tcp_table.setItem(row, 2, status_item)
            self._update_continue_state()
            log.info("StartupDialog: connected to rtl_tcp %s:%d", host, port)
        except Exception as e:
            log.error("StartupDialog: Connection failed: %s", e)
            row = self._tcp_rows.get(port)
            if row is not None:
                item = QtWidgets.QTableWidgetItem("Connect failed")
                item.setForeground(QtGui.QColor("red"))
                self.tcp_table.setItem(row, 2, item)

    # -----------------------
    # Periodic refresh of statuses
    # -----------------------
    def _refresh_statuses(self):
        # update tcp table statuses from device_manager.tcp_servers
        for port, info in list(self.device_manager.tcp_servers.items()):
            row = self._tcp_rows.get(port)
            status = info.get("status", "unknown")
            # if proc was started by us, check if it still runs
            proc = info.get("proc")
            if proc is not None:
                try:
                    # proc.returncode is only available after wait/communicate in asyncio,
                    # but we can test proc._transport for liveliness; keep this simple:
                    rc = proc.returncode
                    if rc is None:
                        status = "running"
                    else:
                        status = "exited"
                except Exception:
                    pass
            info["status"] = status
            if row is not None:
                item = QtWidgets.QTableWidgetItem(status)
                item.setForeground(QtGui.QColor("green" if status in ("running","found","connected") else "red"))
                self.tcp_table.setItem(row, 2, item)

        # update continue button state (enabled if any receiver.connected)
        self._update_continue_state()

    # -----------------------
    # Helpers
    # -----------------------
    def _update_continue_state(self):
        # enable continue if any receivers are connected (in device_manager.receivers list)
        any_connected = any(
            getattr(r, "running", False) and getattr(r, "client", None) and getattr(r.client, "connected", False)
            for r in self.device_manager.receivers.values()
        )
        self.continue_btn.setEnabled(any_connected)
