"""
sdr_tab.py
Live channel control and signal monitor for Ned’s SDR Control.
"""

from __future__ import annotations
from PyQt6 import QtWidgets, QtGui, QtCore
import asyncio

class SdrTab(QtWidgets.QWidget):
    """Live view and control for all channels (per‑receiver)."""

    def __init__(self, app):
        super().__init__()
        self.app = app

        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Active Channels")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

        # Nine columns: dongle, chan id, freq, gain, squelch, tone?, tone type, tone value, apply, signal
        self.table = QtWidgets.QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Dongle", "Channel ID", "Freq (MHz)", "Gain (dB)",
            "Squelch (dB)", "Tone?", "Tone Type", "Tone Value",
            "Apply", "Signal"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # Periodically refresh the table to pick up new channels
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.refresh_table)
        self.timer.start(4000)
        self.refresh_table()

    def refresh_table(self):
        """Populate/refresh the channel table."""
        dongles = self.app.device_manager.dongles
        total_channels = sum(len(r.channels) for r in dongles.values() if hasattr(r, "channels"))
        self.table.setRowCount(total_channels)
        row = 0

        for d_name, recv in dongles.items():
            for ch_id, ch in recv.channels.items():
                # basic info
                self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(d_name))
                self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(ch.id))

                # Frequency editor
                freq_edit = QtWidgets.QLineEdit(f"{ch.frequency / 1e6:.4f}")
                freq_edit.setMaximumWidth(100)
                self.table.setCellWidget(row, 2, freq_edit)

                # Gain slider (per‑dongle; adjusting any row will update the dongle’s gain)
                gain_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
                gain_slider.setMinimum(0)
                gain_slider.setMaximum(50)
                gain_slider.setValue(int(getattr(recv, "gain", 0)))
                gain_slider.setFixedWidth(120)
                gain_slider.valueChanged.connect(
                    lambda val, dn=d_name: asyncio.create_task(self.set_gain(dn, val))
                )
                self.table.setCellWidget(row, 3, gain_slider)

                # Noise squelch slider
                squelch_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
                squelch_slider.setMinimum(-100)
                squelch_slider.setMaximum(0)
                squelch_slider.setValue(int(ch.squelch_level))
                squelch_slider.setFixedWidth(120)
                self.table.setCellWidget(row, 4, squelch_slider)

                # Tone‑squelch checkbox
                tone_check = QtWidgets.QCheckBox()
                tone_enabled = ch.tone_type is not None
                tone_check.setChecked(tone_enabled)
                self.table.setCellWidget(row, 5, tone_check)

                # Tone type selector
                tone_type = QtWidgets.QComboBox()
                tone_type.addItems(["None", "PL", "DPL"])
                tone_type.setCurrentText(ch.tone_type or "None")
                tone_type.setFixedWidth(70)
                tone_type.setEnabled(tone_enabled)
                self.table.setCellWidget(row, 6, tone_type)

                # Tone value editor
                tone_value = QtWidgets.QLineEdit(str(ch.tone_value or ""))
                tone_value.setMaximumWidth(70)
                tone_value.setEnabled(tone_enabled)
                self.table.setCellWidget(row, 7, tone_value)

                # Toggle enable/disable of tone widgets when checkbox changes
                def on_tone_toggle(state, tt=tone_type, tv=tone_value):
                    checked = state == QtCore.Qt.CheckState.Checked
                    tt.setEnabled(checked)
                    tv.setEnabled(checked)
                tone_check.stateChanged.connect(on_tone_toggle)

                # Apply button
                apply_btn = QtWidgets.QPushButton("Apply")
                apply_btn.clicked.connect(lambda _,
                                          dn=d_name, cid=ch_id,
                                          fe=freq_edit, gs=gain_slider,
                                          ss=squelch_slider, tc=tone_check,
                                          tt=tone_type, tv=tone_value:
                    asyncio.create_task(
                        self.apply_changes(dn, cid, fe, gs, ss, tc, tt, tv)
                    )
                )
                self.table.setCellWidget(row, 8, apply_btn)

                # Signal power placeholder
                sig_item = QtWidgets.QTableWidgetItem("Idle")
                sig_item.setForeground(QtGui.QColor("gray"))
                self.table.setItem(row, 9, sig_item)

                row += 1

    async def set_gain(self, dongle: str, gain: int):
        """Update dongle gain immediately when slider is moved."""
        try:
            await self.app.device_manager.set_gain(dongle, gain)
            self.app.log_tab.append_log(f"[UI] Set {dongle} gain → {gain} dB")
        except Exception as e:
            self.app.log_tab.append_log(f"[UI] Gain update failed: {e}")

    async def apply_changes(self, dongle: str, channel: str,
                            freq_edit: QtWidgets.QLineEdit,
                            gain_slider: QtWidgets.QSlider,
                            squelch_slider: QtWidgets.QSlider,
                            tone_check: QtWidgets.QCheckBox,
                            tone_type: QtWidgets.QComboBox,
                            tone_value: QtWidgets.QLineEdit):
        """Apply user edits to frequency, squelch, tone and gain."""
        try:
            freq_mhz = float(freq_edit.text())
            gain = int(gain_slider.value())
            squelch = float(squelch_slider.value())

            # Determine tone settings
            use_tone = tone_check.isChecked()
            if not use_tone:
                ttype = None
                tval = None
            else:
                ttype = tone_type.currentText() if tone_type.currentText() != "None" else None
                tval_str = tone_value.text().strip()
                tval = float(tval_str) if tval_str else None

            dm = self.app.device_manager

            # Retune channel frequency
            await dm.retune_channel(dongle, channel, freq_mhz)

            # Update channel object’s squelch and tone attributes
            ch = dm.dongles[dongle].channels[channel]
            ch.squelch.threshold_db = squelch
            ch.tone.tone_type = ttype
            ch.tone.tone_value = tval

            # Update receiver gain
            await dm.set_gain(dongle, gain)

            # Persist changes to configuration
            cfg = dm.config_manager.config
            for d in cfg.get("dongles", []):
                if d.get("name") == dongle:
                    d["gain"] = gain
                    for c in d.get("channels", []):
                        if c.get("name") == channel:
                            c["frequency"] = freq_mhz * 1e6
                            c["squelch"] = squelch
                            c["tone_type"] = ttype
                            c["tone_value"] = tval
            dm.config_manager.save(cfg)

            self.app.log_tab.append_log(
                f"[UI] Updated {dongle}/{channel}: {freq_mhz:.4f} MHz, "
                f"gain={gain}, squelch={squelch}, tone={ttype or 'None'} {tval or ''}"
            )
        except Exception as e:
            self.app.log_tab.append_log(f"[UI] Apply failed: {e}")

    def update_signal(self, data: dict):
        """Update signal column for a dongle."""
        dongle = data.get("dongle")
        power = data.get("power")
        if power is None:
            return
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text() == dongle:
                sig_item = QtWidgets.QTableWidgetItem(f"{power:.1f} dB")
                sig_item.setForeground(QtGui.QColor("green" if power > -45 else "gray"))
                self.table.setItem(row, 9, sig_item)
