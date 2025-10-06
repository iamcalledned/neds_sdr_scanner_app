"""
log_tab.py
Displays backend and event logs.
"""

from PyQt6 import QtWidgets


class LogTab(QtWidgets.QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.layout = QtWidgets.QVBoxLayout(self)

        self.textbox = QtWidgets.QPlainTextEdit()
        self.textbox.setReadOnly(True)
        self.layout.addWidget(self.textbox)

    def append_log(self, text: str):
        """Append log text to display."""
        self.textbox.appendPlainText(text)
