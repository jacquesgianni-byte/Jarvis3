"""Jarvis Home Page."""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from apps.desktop.widgets.home_widget import HomeWidget


class HomePage(QWidget):
    """Primary Jarvis experience."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.home = HomeWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self.home)