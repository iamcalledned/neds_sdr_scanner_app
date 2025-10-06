"""
sdr_tab.py
Live channel control and signal monitor for Neds SDR Control.
"""

from PyQt6 import QtWidgets, QtGui, QtCore
import asyncio


class SdrTab(QtWidgets.QWidget):
    """Live view and control for all channels."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        layout = QtWidgets.QVBoxLayout(self)
        self.setLayout(layout)

        title = QtWidgets.QLabel("Active Channels")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

        # Table setup
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Dongle", "Channel ID", "Freq (MHz)", "Squelch (dB)",
            "Tone Type", "Tone Value", "Apply", "Signal"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # Timer refresh
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.refresh_table)
        self.timer.start(4000)
        self.refresh_table()

    # ------------------------------------------------------------------
    def refresh_table(self):
        """Refresh the list of channels from backend."""
        dongles = self.app.device_manager.dongles
        total_channels = sum(len(r.channels) for r in dongles.values())
        self.table.setRowCount(total_channels)
        row = 0

        for d_name, r in dongles.items():
            for ch_id, ch in r.channels.items():
                self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(d_name))
                self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(ch.id))

                # Frequency input
                freq_edit = QtWidgets.QLineEdit(f"{ch.frequency / 1e6:.4f}")
                freq_edit.setMaximumWidth(100)
                self.table.setCellWidget(row, 2, freq_edit)

                # Squelch slider
                squelch_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
                squelch_slider.setMinimum(-100)
                squelch_slider.setMaximum(0)
                squelch_slider.setValue(int(ch.squelch_level))
                squelch_slider.setFixedWidth(120)
                self.table.setCellWidget(row, 3, squelch_slider)

                # Tone type selector
                tone_type = QtWidgets.QComboBox()
                tone_type.addItems(["None", "PL", "DPL"])
                tone_type.setCurrentText(ch.tone_type or "None")
                tone_type.setFixedWidth(70)
                self.table.setCellWidget(row, 4, tone_type)

                # Tone value
                tone_value = QtWidgets.QLineEdit(str(ch.tone_value or ""))
                tone_value.setMaximumWidth(70)
                self.table.setCellWidget(row, 5, tone_value)

                # Apply button
                apply_btn = QtWidgets.QPushButton("Apply")
                apply_btn.clicked.connect(lambda _, dn=d_name, cid=ch_id,
                                          fe=freq_edit, ss=squelch_slider,
                                          tt=tone_type, tv=tone_value:
                                          asyncio.create_task(self.apply_changes(dn, cid, fe, ss, tt, tv)))
                self.table.setCellWidget(row, 6, apply_btn)

                # Signal power placeholder
                sig_item = QtWidgets.QTableWidgetItem("Idle")
                sig_item.setForeground(QtGui.QColor("gray"))
                self.table.setItem(row, 7, sig_item)

                row += 1

    # ------------------------------------------------------------------
    async def apply_changes(self, dongle, channel, freq_edit, squelch_slider, tone_type, tone_value):
        """Apply user edits to a specific channel."""
        try:
            freq_mhz = float(freq_edit.text())
            squelch = float(squelch_slider.value())
            ttype = tone_type.currentText() if tone_type.currentText() != "None" else None
            tvalue = tone_value.text().strip()
            if tvalue == "":
                tvalue = None

            dm = self.app.device_manager
            await dm.retune_channel(dongle, channel, freq_mhz)

            # Apply squelch/tone immediately
            ch = dm.dongles[dongle].channels[channel]
            ch.squelch.threshold_db = squelch
            ch.tone.tone_type = ttype
            ch.tone.tone_value = float(tvalue) if tvalue else None

            # Save to config
            cfg = dm.config_manager.config
            for d in cfg.get("dongles", []):
                if d["name"] == dongle:
                    for c in d.get("channels", []):
                        if c["name"] == channel:
                            c["frequency"] = freq_mhz * 1e6
                            c["squelch"] = squelch
                            c["tone_type"] = ttype
                            c["tone_value"] = float(tvalue) if tvalue else None
            dm.config_manager.save(cfg)

            self.app.log_tab.append_log(
                f"[UI] Updated {dongle}/{channel}: {freq_mhz:.4f} MHz, "
                f"squelch={squelch}, tone={ttype} {tvalue or ''}"
            )
        except Exception as e:
            self.app.log_tab.append_log(f"[UI] Apply failed: {e}")

    # ------------------------------------------------------------------
    def update_signal(self, data: dict):
        """Update channel signal column."""
        dongle = data.get("dongle")
        power = data.get("power", None)
        if power is None:
            return
        for row in range(self.table.rowCount()):
            d_name = self.table.item(row, 0).text()
            if d_name == dongle:
                sig_item = QtWidgets.QTableWidgetItem(f"{power:.1f} dB")
                color = "green" if power > -45 else "gray"
                sig_item.setForeground(QtGui.QColor(color))
                self.table.setItem(row, 7, sig_item)
