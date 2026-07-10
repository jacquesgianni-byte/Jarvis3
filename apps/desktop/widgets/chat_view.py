"""
Jarvis OS Chat View Widget

The main conversation area displaying message bubbles
for Jarvis, user and system messages.
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QScrollArea, QFrame, QHBoxLayout, QSizePolicy, QTextEdit
)
from PySide6.QtCore import Qt, QTimer

from apps.desktop.theme import Theme


class MessageBubble(QFrame):
    """
    A single message bubble in the conversation view.

    Uses QTextEdit for the bubble content to support:
    - Ctrl+C text copying
    - Right-click context menu
    - Multi-line text selection
    """

    def __init__(self, text: str, role: str, parent=None):
        """
        Args:
            text:   The message text.
            role:   One of 'jarvis', 'user', 'system'.
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Sender label
        if role != "system":
            sender = "Jarvis" if role == "jarvis" else "You"
            timestamp = datetime.now().strftime("%H:%M")
            header = QLabel(f"{sender}  ·  {timestamp}")
            header.setStyleSheet(f"""
                color: {Theme.TEXT_MUTED};
                font-size: {Theme.FONT_XS}px;
                padding: 0;
                background: transparent;
            """)
            layout.addWidget(header)

        # Colour scheme per role
        if role == "jarvis":
            bg = Theme.BUBBLE_JARVIS
            color = Theme.TEXT
            border = f"1px solid {Theme.BORDER}"
        elif role == "user":
            bg = Theme.BUBBLE_USER
            color = Theme.TEXT
            border = f"1px solid {Theme.BORDER_ACCENT}"
        else:
            bg = "transparent"
            color = Theme.TEXT_SECONDARY
            border = "none"

        # QTextEdit for full desktop text interaction
        bubble = _BubbleText(text, bg, color, border)
        layout.addWidget(bubble)

        self.setStyleSheet("background: transparent;")

        if role == "user":
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)


class _BubbleText(QTextEdit):
    """
    Read-only text widget used inside MessageBubble.

    Provides Ctrl+C, right-click copy and multi-line selection
    while maintaining the bubble appearance.
    Auto-sizes to fit content without a scrollbar.
    """

    def __init__(self, text: str, bg: str, color: str, border: str, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)
        self.setPlainText(text)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.setStyleSheet(f"""
            QTextEdit {{
                background: {bg};
                color: {color};
                font-family: "{Theme.FONT_FAMILY}";
                font-size: {Theme.FONT_NORMAL}px;
                border: {border};
                border-radius: {Theme.RADIUS_MD}px;
                padding: 12px 16px;
                selection-background-color: {Theme.ACCENT_DIM};
            }}
            QScrollBar {{
                width: 0px;
                height: 0px;
            }}
        """)

        # Size to content after document is populated
        self.document().contentsChanged.connect(self._resize_to_content)
        self._resize_to_content()

    def _resize_to_content(self):
        """Resize the widget to fit its text content exactly."""
        doc = self.document()
        doc.setTextWidth(self.viewport().width() if self.viewport().width() > 0 else 500)
        doc_height = doc.size().height()
        # Fallback: estimate from line count if doc height is zero
        if doc_height < 10:
            lines = max(1, self.toPlainText().count(chr(10)) + 1)
            doc_height = lines * 22
        self.setFixedHeight(int(doc_height) + 28)


class TypingIndicator(QFrame):
    """Animated typing indicator shown while Jarvis is thinking."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)

        self._dots = []
        for _ in range(3):
            dot = QLabel("●")
            dot.setStyleSheet(f"""
                color: {Theme.ACCENT};
                font-size: 8px;
                background: transparent;
            """)
            layout.addWidget(dot)
            self._dots.append(dot)

        layout.addStretch()

        self.setStyleSheet(f"""
            background: {Theme.BUBBLE_JARVIS};
            border: 1px solid {Theme.BORDER};
            border-radius: {Theme.RADIUS_MD}px;
        """)
        self.setFixedHeight(44)

        self._step = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(300)

    def _animate(self):
        for i, dot in enumerate(self._dots):
            if i == self._step % 3:
                dot.setStyleSheet(f"color: {Theme.ACCENT}; font-size: 8px; background: transparent;")
            else:
                dot.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 8px; background: transparent;")
        self._step += 1


class ChatView(QScrollArea):
    """
    Scrollable conversation area containing message bubbles.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(
            Theme.CHAT_PADDING,
            Theme.CHAT_PADDING,
            Theme.CHAT_PADDING,
            Theme.CHAT_PADDING
        )
        self._layout.setSpacing(Theme.SPACING_MD)
        self._layout.addStretch()

        self.setWidget(self._container)
        self._typing_indicator = None

        self.setStyleSheet(f"""
            QScrollArea {{
                background: {Theme.BACKGROUND};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {Theme.SURFACE};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.BORDER};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

    def _add_bubble(self, text: str, role: str):
        """Add a message bubble and scroll to bottom."""
        self._remove_typing()

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        bubble = MessageBubble(text, role)

        if role == "user":
            row.addStretch()
            row.addWidget(bubble, stretch=0)
            bubble.setMaximumWidth(560)
        elif role == "system":
            row.addWidget(bubble)
        else:
            row.addWidget(bubble, stretch=0)
            row.addStretch()
            bubble.setMaximumWidth(620)

        wrapper = QWidget()
        wrapper.setLayout(row)
        wrapper.setStyleSheet("background: transparent;")

        self._layout.insertWidget(self._layout.count() - 1, wrapper)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _remove_typing(self):
        if self._typing_indicator is not None:
            self._typing_indicator.setParent(None)
            self._typing_indicator.deleteLater()
            self._typing_indicator = None

    def _scroll_to_bottom(self):
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        )

    def display_jarvis_message(self, text: str):
        """Display a message from Jarvis."""
        self._add_bubble(text, "jarvis")

    def display_user_message(self, text: str):
        """Display a message from the user."""
        self._add_bubble(text, "user")

    def display_system_message(self, text: str):
        """Display a system message."""
        self._add_bubble(text, "system")

    def show_typing(self):
        """Show the typing indicator."""
        self._remove_typing()
        self._typing_indicator = TypingIndicator()

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._typing_indicator, stretch=0)
        row.addStretch()

        wrapper = QWidget()
        wrapper.setLayout(row)
        wrapper.setStyleSheet("background: transparent;")

        self._layout.insertWidget(self._layout.count() - 1, wrapper)
        self._typing_indicator._wrapper = wrapper
        QTimer.singleShot(50, self._scroll_to_bottom)

    def hide_typing(self):
        """Remove the typing indicator."""
        self._remove_typing()