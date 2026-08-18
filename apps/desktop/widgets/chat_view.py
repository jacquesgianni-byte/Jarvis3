"""
Jarvis OS Chat View Widget

Single-document conversation area — the entire chat history lives in one
QTextEdit, making the full conversation selectable and copyable as one block.
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QScrollArea, QFrame, QHBoxLayout, QSizePolicy,
    QTextEdit,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor

from apps.desktop.theme import Theme


class TypingIndicator(QFrame):
    """Animated typing indicator shown while Jarvis is thinking."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)

        self._dots = []
        for _ in range(3):
            dot = QLabel("\u25cf")
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
                dot.setStyleSheet(
                    f"color: {Theme.ACCENT}; font-size: 8px; background: transparent;"
                )
            else:
                dot.setStyleSheet(
                    f"color: {Theme.TEXT_MUTED}; font-size: 8px; background: transparent;"
                )
        self._step += 1


class ChatView(QWidget):
    """
    Scrollable conversation area using a single QTextEdit document.

    The entire conversation history is one document — fully selectable
    and copyable across all messages, like Claude or ChatGPT.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Single document for the entire conversation
        self._doc = QTextEdit()
        self._doc.setReadOnly(True)
        self._doc.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._doc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._doc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._doc.setStyleSheet(f"""
            QTextEdit {{
                background: {Theme.BACKGROUND};
                color: {Theme.TEXT};
                font-family: "{Theme.FONT_FAMILY}";
                font-size: {Theme.FONT_NORMAL}px;
                border: none;
                padding: 16px;
                selection-background-color: {Theme.ACCENT_DIM};
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

        self._layout.addWidget(self._doc, stretch=1)

        # Typing indicator sits below the doc, hidden by default
        self._typing_row = QWidget()
        typing_layout = QHBoxLayout(self._typing_row)
        typing_layout.setContentsMargins(Theme.CHAT_PADDING, 4, Theme.CHAT_PADDING, 4)
        self._typing_indicator = TypingIndicator()
        typing_layout.addWidget(self._typing_indicator, stretch=0)
        typing_layout.addStretch()
        self._typing_row.setStyleSheet(f"background: {Theme.BACKGROUND};")
        self._typing_row.hide()
        self._layout.addWidget(self._typing_row)

        self._is_first_message = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_html(self, html: str):
        """Append an HTML block to the document and scroll to bottom."""
        cursor = self._doc.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self._is_first_message:
            cursor.insertHtml("<br>")
        cursor.insertHtml(html)
        self._is_first_message = False
        QTimer.singleShot(30, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        self._doc.verticalScrollBar().setValue(
            self._doc.verticalScrollBar().maximum()
        )

    def _format_message(self, text: str, role: str) -> str:
        """Format a message as an HTML block."""
        timestamp = datetime.now().strftime("%H:%M")

        if role == "jarvis":
            sender_color = Theme.ACCENT
            sender = "Jarvis"
            bubble_bg = Theme.BUBBLE_JARVIS
            border_color = Theme.BORDER
        elif role == "user":
            sender_color = Theme.TEXT_SECONDARY
            sender = "You"
            bubble_bg = Theme.BUBBLE_USER
            border_color = Theme.BORDER_ACCENT
        else:
            # System message — no header, muted style
            return (
                f'<div style="color: {Theme.TEXT_SECONDARY}; font-size: 12px; '
                f'padding: 4px 0; font-style: italic;">{text}</div>'
            )

        # Escape HTML special chars in text
        safe_text = (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

        return (
            f'<div style="margin-bottom: 4px;">' +
            f'<span style="color: {sender_color}; font-size: 11px; font-weight: 600;">{sender}</span>' +
            f'<span style="color: {Theme.TEXT_MUTED}; font-size: 11px;">  ·  {timestamp}</span>' +
            f'</div>' +
            f'<div style="' +
            f'background: {bubble_bg}; ' +
            f'border: 1px solid {border_color}; ' +
            f'border-radius: 8px; ' +
            f'padding: 10px 14px; ' +
            f'color: {Theme.TEXT}; ' +
            f'font-size: {Theme.FONT_NORMAL}px; ' +
            f'line-height: 1.5; ' +
            f'">{safe_text}</div>'
        )

    # ------------------------------------------------------------------
    # Public API — unchanged from original ChatView
    # ------------------------------------------------------------------

    def display_jarvis_message(self, text: str):
        """Display a message from Jarvis."""
        self._typing_row.hide()
        self._append_html(self._format_message(text, "jarvis"))

    def display_user_message(self, text: str):
        """Display a message from the user."""
        self._append_html(self._format_message(text, "user"))

    def display_system_message(self, text: str):
        """Display a system message."""
        self._append_html(self._format_message(text, "system"))

    def show_typing(self):
        """Show the typing indicator."""
        self._typing_row.show()
        QTimer.singleShot(30, self._scroll_to_bottom)

    def hide_typing(self):
        """Hide the typing indicator."""
        self._typing_row.hide()
