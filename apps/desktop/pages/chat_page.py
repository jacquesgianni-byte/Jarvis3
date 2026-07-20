"""Jarvis Chat Page."""

from PySide6.QtWidgets import QWidget, QVBoxLayout

from apps.desktop.widgets.chat_view import ChatView
from apps.desktop.widgets.input_bar import InputBar


class ChatPage(QWidget):
    """Desktop page hosting the conversation UI."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.chat_view = ChatView()
        self.input_bar = InputBar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self.chat_view, stretch=1)
        layout.addWidget(self.input_bar)