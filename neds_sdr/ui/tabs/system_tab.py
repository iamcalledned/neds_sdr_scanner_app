from PyQt6 import QtWidgets

class SystemTab(QtWidgets.QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("System Controls (start/stop services, version, etc.)"))
