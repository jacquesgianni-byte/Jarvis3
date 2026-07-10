"""
Jarvis OS Input Bar Widget

The bottom input area containing the voice button,
text input and send/stop button.

The send button transitions to a stop button while Jarvis is processing.
Call set_processing(True) to enter processing state.
Call set_processing(False) to restore the idle state.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLineEdit
from PySide6.QtCore import Qt

from apps.desktop.theme import Theme


class InputBar(QWidget):
    """
    Bottom input bar for Jarvis OS Desktop.

    Supports two states:
        Idle       — Send button (➤), input editable.
        Processing — Stop button (■), input shows status, editing disabled.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(Theme.INPUT_HEIGHT + 20)
        self._processing = False
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            Theme.SPACING_MD, Theme.SPACING_SM,
            Theme.SPACING_MD, Theme.SPACING_SM
        )
        layout.setSpacing(Theme.SPACING_SM)

        # Voice button
        self.voice_button = QPushButton("🎤")
        self.voice_button.setFixedSize(Theme.INPUT_HEIGHT, Theme.INPUT_HEIGHT)
        self.voice_button.setCursor(Qt.PointingHandCursor)
        self.voice_button.setFocusPolicy(Qt.NoFocus)
        self.voice_button.setToolTip("Voice input")
        self._style_voice_button(active=False)

        # Text input
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ask Jarvis...")
        self.input_box.setFixedHeight(Theme.INPUT_HEIGHT)
        self.input_box.setStyleSheet(f"""
            QLineEdit {{
                background: {Theme.SURFACE_ELEVATED};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: {Theme.RADIUS_MD}px;
                padding: 0 16px;
                font-family: "{Theme.FONT_FAMILY}";
                font-size: {Theme.FONT_NORMAL}px;
                selection-background-color: {Theme.ACCENT_DIM};
            }}
            QLineEdit:focus {{
                border-color: {Theme.ACCENT};
            }}
            QLineEdit:disabled {{
                color: {Theme.TEXT_MUTED};
                border-color: {Theme.BORDER};
            }}
        """)

        # Send / Stop button
        self.send_button = QPushButton("➤")
        self.send_button.setFixedSize(Theme.INPUT_HEIGHT, Theme.INPUT_HEIGHT)
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setFocusPolicy(Qt.NoFocus)
        self._style_send_button(processing=False)

        layout.addWidget(self.voice_button)
        layout.addWidget(self.input_box, stretch=1)
        layout.addWidget(self.send_button)

    def _apply_style(self):
        self.setStyleSheet(f"""
            InputBar {{
                background: {Theme.SURFACE};
                border-top: 1px solid {Theme.BORDER};
            }}
        """)

    def _style_send_button(self, processing: bool):
        """Apply idle (send) or processing (stop) styling to the action button."""
        if processing:
            self.send_button.setText("■")
            self.send_button.setToolTip("Stop")
            self.send_button.setStyleSheet(f"""
                QPushButton {{
                    background: {Theme.ERROR};
                    color: #FFFFFF;
                    border: none;
                    border-radius: {Theme.RADIUS_FULL}px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: #FF6B6B;
                }}
                QPushButton:pressed {{
                    background: #CC3333;
                }}
            """)
        else:
            self.send_button.setText("➤")
            self.send_button.setToolTip("Send  (Enter)")
            self.send_button.setStyleSheet(f"""
                QPushButton {{
                    background: {Theme.ACCENT};
                    color: #000000;
                    border: none;
                    border-radius: {Theme.RADIUS_FULL}px;
                    font-size: 16px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: {Theme.ACCENT_HOVER};
                }}
                QPushButton:pressed {{
                    background: {Theme.ACCENT_DIM};
                }}
            """)

    def _style_voice_button(self, active: bool):
        """Apply idle or active styling to the voice button."""
        if active:
            self.voice_button.setStyleSheet(f"""
                QPushButton {{
                    background: {Theme.ACCENT};
                    color: #000000;
                    border: none;
                    border-radius: {Theme.RADIUS_FULL}px;
                    font-size: 16px;
                }}
            """)
        else:
            self.voice_button.setStyleSheet(f"""
                QPushButton {{
                    background: {Theme.SURFACE_ELEVATED};
                    color: {Theme.TEXT_SECONDARY};
                    border: 1px solid {Theme.BORDER};
                    border-radius: {Theme.RADIUS_FULL}px;
                    font-size: 16px;
                }}
                QPushButton:hover {{
                    background: {Theme.SURFACE_HOVER};
                    border-color: {Theme.ACCENT};
                    color: {Theme.ACCENT};
                }}
            """)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_processing(self, processing: bool):
        """
        Switch the input bar between idle and processing states.

        When processing=True:
            - Send button becomes a Stop button (■, red).
            - Input field STAYS ENABLED — typing and processing are
              independent activities (Input Independence). Pressing
              Enter while processing interrupts the current request and
              starts the new one; the window owns that logic.
            - Placeholder hints at the busy state when the field is empty.
            - Voice button is disabled (voice flow is not yet
              interrupt-aware).

        When processing=False:
            - Stop button reverts to Send button (➤, blue).
            - Placeholder returns to the idle prompt.
            - Voice button is re-enabled.

        Args:
            processing: True to enter processing state, False to return to idle.
        """

        self._processing = processing
        self._style_send_button(processing)

        if processing:
            self.input_box.setPlaceholderText("Jarvis is thinking... (type to queue a new request)")
            self.voice_button.setEnabled(False)
        else:
            self.input_box.setPlaceholderText("Ask Jarvis...")
            self.voice_button.setEnabled(True)

    def set_voice_active(self, active: bool):
        """Update voice button appearance when listening."""
        self._style_voice_button(active)

    def text(self) -> str:
        """Return the current input text."""
        return self.input_box.text().strip()

    def clear(self):
        """Clear the input field."""
        self.input_box.clear()

    def focus(self):
        """Set focus to the input field."""
        self.input_box.setFocus()

    @property
    def is_processing(self) -> bool:
        """Return True if the input bar is currently in processing state."""
        return self._processing