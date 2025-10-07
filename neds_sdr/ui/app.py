"""
sdr_tab.py
Channels management and tuning tab for Ned's SDR Control UI.
"""

import asyncio
from PyQt6 import QtWidgets, QtCore


class SdrTab(QtWidgets.QWidget):
    """UI tab for managing SDR channel presets and live tuning."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main = main_window
        self.device_manager = main_window.device_manager
        self.event_bus = main_window.event_bus

        self._setup_ui()
        self._connect_signals()

        self.current_receiver = None
        self.refresh_receivers()

        # Subscribe to backend updates
        self.event_bus.subscribe("receiver_created", self._on_receiver_event)
        self.event_bus.subscribe("receiver_connected", self._on_receiver_event)
        self.event_bus.subscribe("channel_presets_updated", self._on_presets_updated)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # --- Receiver selection ---
        recv_layout = QtWidgets.QHBoxLayout()
        recv_layout.addWidget(QtWidgets.QLabel("Receiver:"))
        self.receiver_combo = QtWidgets.QComboBox()
        recv_layout.addWidget(self.receiver_combo)
        layout.addLayout(recv_layout)

        # --- Preset list ---
        self.preset_list = QtWidgets.QListWidget()
        layout.addWidget(QtWidgets.QLabel("Channel Presets:"))
        layout.addWidget(self.preset_list)

        # --- Channel configuration ---
        form = QtWidgets.QFormLayout()
        self.name_input = QtWidgets.QLineEdit()
        self.freq_input = QtWidgets.QDoubleSpinBox()
        self.freq_input.setRange(0.01, 3000.0)
        self.freq_input.setDecimals(6)
        self.gain_input = QtWidgets.QSpinBox()
        self.gain_input.setRange(0, 60)
        self.squelch_input = QtWidgets.QSpinBox()
        self.squelch_input.setRange(-120, 0)
        self.squelch_input.setValue(-50)
        self.tone_type_combo = QtWidgets.QComboBox()
        self.tone_type_combo.addItems(["None", "PL", "DPL"])
        self.tone_value_input = QtWidgets.QDoubleSpinBox()
        self.tone_value_input.setRange(0.0, 300.0)
        self.tone_value_input.setDecimals(1)
        self.sink_input = QtWidgets.QLineEdit("default")

        form.addRow("Name:", self.name_input)
        form.addRow("Freq (MHz):", self.freq_input)
        form.addRow("Gain (dB):", self.gain_input)
        form.addRow("Squelch (dB):", self.squelch_input)
        form.addRow("Tone Type:", self.tone_type_combo)
        form.addRow("Tone Value:", self.tone_value_input)
        form.addRow("Sink:", self.sink_input)

        layout.addLayout(form)

        # --- Buttons ---
        btn_layout = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton("Add Preset")
        self.remove_btn = QtWidgets.QPushButton("Remove Preset")
        self.tune_btn = QtWidgets.QPushButton("Tune")
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.tune_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------
    def _connect_signals(self):
        self.receiver_combo.currentIndexChanged.connect(self._on_receiver_changed)
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        self.tune_btn.clicked.connect(self._on_tune_clicked)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_receiver_event(self, data):
        self.refresh_receivers()

    def _on_receiver_changed(self, idx):
        if idx < 0:
            return
        name = self.receiver_combo.currentText()
        self.current_receiver = self.device_manager.receivers.get(name)
        self._refresh_presets()

    def _on_presets_updated(self, data):
        if self.current_receiver and data["dongle"] == self.current_receiver.name:
            self._refresh_presets()

    def _on_add_clicked(self):
        """Add new preset for current receiver."""
        if not self.current_receiver:
            self._warn("Select a receiver first.")
            return

        name = self.name_input.text().strip()
        if not name:
            self._warn("Enter a channel name.")
            return

        freq_hz = self.freq_input.value() * 1e6
        squelch = self.squelch_input.value()
        tone_type = self.tone_type_combo.currentText()
        tone_value = self.tone_value_input.value()
        sink = self.sink_input.text().strip() or "default"

        # Add to receiver preset manager
        self.current_receiver.presets.add_preset(
            name=name,
            frequency=freq_hz,
            squelch=squelch,
            tone_type=None if tone_type == "None" else tone_type,
            tone_value=tone_value if tone_type != "None" else None,
            sink=sink,
        )

        self._refresh_presets()

    def _on_remove_clicked(self):
        item = self.preset_list.currentItem()
        if not item or not self.current_receiver:
            return
        self.current_receiver.presets.remove_preset(item.text())
        self._refresh_presets()

    def _on_tune_clicked(self):
        item = self.preset_list.currentItem()
        if not item or not self.current_receiver:
            return
        name = item.text()
        asyncio.create_task(self.current_receiver.set_channel(name))

    # ------------------------------------------------------------------
    # Refreshers
    # ------------------------------------------------------------------
    def refresh_receivers(self):
        """Repopulate receiver dropdown."""
        self.receiver_combo.clear()
        for name in self.device_manager.receivers.keys():
            self.receiver_combo.addItem(name)
        if self.receiver_combo.count() > 0:
            self.receiver_combo.setCurrentIndex(0)
            self._on_receiver_changed(0)

    def _refresh_presets(self):
        self.preset_list.clear()
        if not self.current_receiver:
            return
        presets = self.current_receiver.presets.list_presets()
        self.preset_list.addItems(presets)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _warn(self, msg):
        QtWidgets.QMessageBox.warning(self, "Warning", msg)

    def refresh_table(self):
        """Compatibility method for UIController expectations."""
        self._refresh_presets()

    def update_signal(self, data):
        """Compatibility stub: could show signal levels later."""
        pass
