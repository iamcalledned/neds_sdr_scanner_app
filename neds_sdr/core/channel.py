"""
channels_tab.py
Provides the Channels UI tab for adding, editing, and tuning SDR channels.
"""

import asyncio
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QDoubleSpinBox,
    QSpinBox, QListWidget, QListWidgetItem, QMessageBox
)
from PySide6.QtCore import Qt


class ChannelsTab(QWidget):
    """
    UI tab for channel preset management and live tuning.
    """

    def __init__(self, app_ctx, event_bus, parent=None):
        super().__init__(parent)
        self.app = app_ctx
        self.event_bus = event_bus

        self._setup_ui()
        self._connect_signals()

        self.current_dongle = None
        self.presets = {}

    # ------------------------------------------------------------------
    # UI layout
    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Receiver selection ---
        recv_layout = QHBoxLayout()
        recv_layout.addWidget(QLabel("Receiver:"))
        self.receiver_combo = QComboBox()
        recv_layout.addWidget(self.receiver_combo)
        layout.addLayout(recv_layout)

        # --- Preset list ---
        self.preset_list = QListWidget()
        layout.addWidget(QLabel("Channel Presets:"))
        layout.addWidget(self.preset_list)

        # --- Channel configuration form ---
        form_layout = QHBoxLayout()
        form_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        form_layout.addWidget(self.name_input)

        form_layout.addWidget(QLabel("Freq (MHz):"))
        self.freq_input = QDoubleSpinBox()
        self.freq_input.setRange(0.01, 3000.0)
        self.freq_input.setDecimals(6)
        form_layout.addWidget(self.freq_input)

        form_layout.addWidget(QLabel("Gain (dB):"))
        self.gain_input = QSpinBox()
        self.gain_input.setRange(0, 60)
        form_layout.addWidget(self.gain_input)

        form_layout.addWidget(QLabel("Squelch (dB):"))
        self.squelch_input = QSpinBox()
        self.squelch_input.setRange(-120, 0)
        self.squelch_input.setValue(-50)
        form_layout.addWidget(self.squelch_input)

        layout.addLayout(form_layout)

        # --- Tone + Sink ---
        tone_layout = QHBoxLayout()
        tone_layout.addWidget(QLabel("Tone Type:"))
        self.tone_type_combo = QComboBox()
        self.tone_type_combo.addItems(["None", "PL", "DPL"])
        tone_layout.addWidget(self.tone_type_combo)

        tone_layout.addWidget(QLabel("Tone Value:"))
        self.tone_value_input = QDoubleSpinBox()
        self.tone_value_input.setRange(0.0, 300.0)
        self.tone_value_input.setDecimals(1)
        tone_layout.addWidget(self.tone_value_input)

        tone_layout.addWidget(QLabel("Sink:"))
        self.sink_input = QLineEdit("default")
        tone_layout.addWidget(self.sink_input)
        layout.addLayout(tone_layout)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add Preset")
        self.remove_btn = QPushButton("Remove")
        self.tune_btn = QPushButton("Tune")
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.tune_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Signals & events
    # ------------------------------------------------------------------
    def _connect_signals(self):
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        self.tune_btn.clicked.connect(self._on_tune_clicked)
        self.receiver_combo.currentIndexChanged.connect(self._on_receiver_changed)

        self.event_bus.on("channel_presets_updated", self._on_presets_updated)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_receiver_changed(self, idx):
        if idx < 0:
            return
        name = self.receiver_combo.currentText()
        self.current_dongle = name
        self._refresh_presets()

    def _on_presets_updated(self, data):
        dongle = data["dongle"]
        if dongle == self.current_dongle:
            self._refresh_presets()

    def _refresh_presets(self):
        self.preset_list.clear()
        if not self.current_dongle:
            return
        receiver = self.app.device_manager.receivers.get(self.current_dongle)
        if receiver:
            for name in receiver.presets.list_presets():
                item = QListWidgetItem(name)
                self.preset_list.addItem(item)

    async def _do_tune(self, name):
        receiver = self.app.device_manager.receivers.get(self.current_dongle)
        if not receiver:
            QMessageBox.warning(self, "No Receiver", "Please select a receiver first.")
            return
        await receiver.set_channel(name)

    def _on_tune_clicked(self):
        item = self.preset_list.currentItem()
        if not item:
            return
        asyncio.create_task(self._do_tune(item.text()))

    def _on_add_clicked(self):
        if not self.current_dongle:
            QMessageBox.warning(self, "No Receiver", "Select a receiver first.")
            return
        receiver = self.app.device_manager.receivers.get(self.current_dongle)
        if not receiver:
            return

        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a channel name.")
            return

        freq_mhz = self.freq_input.value()
        gain = self.gain_input.value()
        squelch = self.squelch_input.value()
        tone_type = self.tone_type_combo.currentText()
        tone_value = self.tone_value_input.value()
        sink = self.sink_input.text().strip() or "default"

        receiver.presets.add_preset(
            name=name,
            frequency=freq_mhz * 1e6,
            squelch=squelch,
            tone_type=None if tone_type == "None" else tone_type,
            tone_value=tone_value if tone_type != "None" else None,
            sink=sink
        )

        self._refresh_presets()

    def _on_remove_clicked(self):
        item = self.preset_list.currentItem()
        if not item:
            return
        name = item.text()
        receiver = self.app.device_manager.receivers.get(self.current_dongle)
        if receiver:
            receiver.presets.remove_preset(name)
            self._refresh_presets()

    # ------------------------------------------------------------------
    # API for parent window
    # ------------------------------------------------------------------
    def refresh_receivers(self):
        """Populate receiver list when devices connect."""
        self.receiver_combo.clear()
        for name in self.app.device_manager.receivers.keys():
            self.receiver_combo.addItem(name)
        if self.receiver_combo.count() > 0:
            self.receiver_combo.setCurrentIndex(0)
