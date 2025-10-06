from PyQt6 import QtWidgets

class SinkTab(QtWidgets.QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("PulseAudio Sink Management (coming soon)"))
