"""
Jarvis OS Main Window (Genesis-030 Sprint-002)

Genesis-030 Sprint-001: Responsive Conversation Framework
    * ProcessWorker emits 'acknowledged' signal before calling Agent.
    * ResponseCoordinator classifies requests as FAST/MEDIUM/LONG.
    * MEDIUM/LONG requests show an immediate acknowledgement in the chat.

Genesis-030 Sprint-002: Incremental AI Streaming
    * ProcessWorker uses JarvisCore.process_stream() for streaming providers.
    * Emits 'token' signal per chunk -- UI appends text progressively.
    * Falls back to process() for non-streaming providers automatically.
    * StreamCallbacks bridge between background thread and Qt signals.
"""

import time

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from PySide6.QtCore import QThread, Signal, QObject, QTimer

from core import telemetry

from apps.desktop.theme import Theme
from apps.desktop.widgets.header import HeaderWidget
from apps.desktop.widgets.sidebar import SidebarWidget
from apps.desktop.widgets.status_bar import StatusBar
from apps.desktop.shell.desktop_shell import DesktopShell
from apps.desktop.controller.desktop_controller import DesktopController
from core.response_coordinator import ResponseCoordinator
from core.ai.streaming import StreamCallbacks


class ProcessWorker(QObject):
    """
    Runs jarvis processing on a background thread so the UI never blocks.

    Genesis-030 Sprint-001: emits 'acknowledged' before processing.
    Genesis-030 Sprint-002: emits 'token' per streaming chunk.

    Signal order:
        acknowledged (str)  -- immediate ack for MEDIUM/LONG requests
        token (str)         -- one per streaming chunk (may be many)
        finished (object)   -- final Response (or None if interrupted)
    """

    acknowledged = Signal(str)
    token        = Signal(str)
    finished     = Signal(object)

    def __init__(self, jarvis, message: str, queued_at: float = None):
        super().__init__()
        self._jarvis = jarvis
        self._message = message
        self._queued_at = queued_at if queued_at is not None else time.perf_counter()
        self._coordinator = ResponseCoordinator()

    def run(self):
        telemetry.begin_request(queued_at=self._queued_at)

        # Classify and emit acknowledgement immediately.
        classification = self._coordinator.classify(self._message)
        if classification.needs_ack:
            self.acknowledged.emit(classification.acknowledgement)

        # Build StreamCallbacks that bridge to Qt signals.
        # on_token emits the token signal on the worker thread --
        # Qt queued connections deliver it safely to the main thread.
        _first_token = [True]  # track whether we've started streaming

        def on_token(text: str) -> None:
            if _first_token[0]:
                _first_token[0] = False
            self.token.emit(text)

        def on_complete(full_text: str) -> None:
            pass  # finished signal carries the final Response

        def on_error(exc: Exception) -> None:
            pass  # finished signal carries the Response with error message

        callbacks = StreamCallbacks(
            on_token=on_token,
            on_complete=on_complete,
            on_error=on_error,
        )

        # Use streaming path -- falls back to blocking if provider
        # does not support streaming.
        response = self._jarvis.process_stream(self._message, callbacks)
        telemetry.end_request()
        self.finished.emit(response)


class MainWindow(QMainWindow):
    """
    The main window for Jarvis OS Desktop.
    """

    def __init__(self, jarvis):
        super().__init__()

        self.jarvis = jarvis
        self._busy = False
        self._streaming = False  # True while tokens are arriving

        self._awaiting_speech_end = False
        self._speech_timer = QTimer(self)
        self._speech_timer.setInterval(150)
        self._speech_timer.timeout.connect(self._check_speech_finished)

        self._jobs = []

        self.setWindowTitle(Theme.WINDOW_TITLE)
        self.resize(Theme.WINDOW_WIDTH, Theme.WINDOW_HEIGHT)
        self.setMinimumSize(900, 600)

        self._build_ui()
        self._apply_global_style()
        self._connect_signals()

        self._controller.startup()

        self.chat_view.display_system_message(
            "Good afternoon, Ludovic.\n\nWelcome back.\n\nJarvis is online and ready."
        )
        self.input_bar.focus()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.header = HeaderWidget()
        root_layout.addWidget(self.header)

        self._shell = DesktopShell()
        root_layout.addWidget(self._shell, stretch=1)

        self.sidebar = SidebarWidget()
        self.sidebar.setVisible(False)

        self._controller = DesktopController(
            jarvis=self.jarvis,
            shell=self._shell,
        )

        self.status_bar_widget = StatusBar()
        root_layout.addWidget(self.status_bar_widget)

    def _apply_global_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {Theme.BACKGROUND};
                color: {Theme.TEXT};
                font-family: "{Theme.FONT_FAMILY}";
                font-size: {Theme.FONT_NORMAL}px;
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

    def _connect_signals(self):
        self.input_bar.send_button.clicked.connect(self._on_action_button)
        self.input_bar.input_box.returnPressed.connect(self._send_message)
        self.input_bar.voice_button.clicked.connect(self._toggle_voice)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def chat_view(self):
        return self._shell.chat_page.chat_view

    @property
    def input_bar(self):
        return self._shell.chat_page.input_bar

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def _on_action_button(self):
        if self.input_bar.is_processing:
            self._stop_request()
        else:
            self._send_message()

    def _send_message(self):
        message = self.input_bar.text()

        if not message:
            return

        if self._busy:
            self.jarvis.stop()
            self.chat_view.hide_typing()

        self._busy = True
        self._streaming = False
        self._awaiting_speech_end = False
        self._speech_timer.stop()
        self.input_bar.clear()
        self.input_bar.focus()
        self.chat_view.display_user_message(message)
        self.chat_view.show_typing()
        self.status_bar_widget.set_status("Thinking...")
        self.sidebar.set_orb_state("thinking")
        self.input_bar.set_processing(True)

        thread = QThread()
        worker = ProcessWorker(self.jarvis, message, queued_at=time.perf_counter())
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.acknowledged.connect(self._on_acknowledgement)
        worker.token.connect(self._on_token)              # Genesis-030 Sprint-002
        worker.finished.connect(self._on_response)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread: self._forget_job(t))

        self._jobs.append((thread, worker))
        thread.start()

    def _forget_job(self, thread):
        self._jobs = [(t, w) for (t, w) in self._jobs if t is not thread]

    def _stop_request(self):
        self.jarvis.stop()
        self.chat_view.hide_typing()
        self.status_bar_widget.set_status("Stopping...")
        self.sidebar.set_orb_state("idle")
        self._busy = False
        self._streaming = False
        self.input_bar.set_processing(False)
        self.input_bar.focus()

    def _on_acknowledgement(self, text: str):
        """Display immediate acknowledgement (Genesis-030 Sprint-001)."""
        if not text:
            return
        self.chat_view.hide_typing()
        self.chat_view.display_jarvis_message(text)
        self.chat_view.show_typing()
        self.status_bar_widget.set_status("Working...")

    def _on_token(self, text: str):
        """
        Append a streaming token to the chat view (Genesis-030 Sprint-002).

        First token hides the typing indicator and starts a new message
        bubble. Subsequent tokens append to the same bubble.
        """
        if not text:
            return

        if not self._streaming:
            # First token -- hide typing indicator, start fresh message
            self._streaming = True
            self.chat_view.hide_typing()
            self.status_bar_widget.set_status("Responding...")

        # Append token to the current streaming message.
        # Falls back to display_jarvis_message if append_token not available.
        if hasattr(self.chat_view, "append_token"):
            self.chat_view.append_token(text)
        else:
            # Fallback: accumulate tokens and display when complete
            if not hasattr(self, "_token_buffer"):
                self._token_buffer = []
            self._token_buffer.append(text)

    def _on_response(self, response):
        """Handle final response (streaming or blocking)."""
        if response is None:
            if not self._busy:
                self.status_bar_widget.set_status("Ready")
            return

        # If we were streaming, the message is already shown token by token.
        # If not streaming (fast response or non-streaming provider),
        # display the complete message now.
        if not self._streaming:
            self.chat_view.hide_typing()
            self.chat_view.display_jarvis_message(response.message)
        else:
            # Flush any token buffer fallback
            if hasattr(self, "_token_buffer") and self._token_buffer:
                full = "".join(self._token_buffer)
                self._token_buffer = []
                self.chat_view.display_jarvis_message(full)
            # Finalise the streaming bubble if supported
            if hasattr(self.chat_view, "finalise_stream"):
                self.chat_view.finalise_stream()

        self._streaming = False
        self.sidebar.set_orb_state("speaking")
        self.status_bar_widget.set_status("Speaking...")

        if hasattr(response, "action") and response.action == "EXIT":
            self.status_bar_widget.set_status("Shutting down...")
            self.close()
            return

        self._awaiting_speech_end = True
        self._speech_timer.start()

    def _check_speech_finished(self):
        if not self._awaiting_speech_end:
            self._speech_timer.stop()
            return
        if not self.jarvis.is_speaking:
            self._speech_timer.stop()
            self._return_to_idle()

    def _return_to_idle(self):
        self._busy = False
        self._streaming = False
        self._awaiting_speech_end = False
        self._speech_timer.stop()
        self.sidebar.set_orb_state("idle")
        self.status_bar_widget.set_status("Ready")
        self.input_bar.set_processing(False)
        self.input_bar.focus()

    def _toggle_voice(self):
        self.sidebar.set_orb_state("listening")
        self.status_bar_widget.set_status("Listening...")
        self.input_bar.set_voice_active(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def display_system_message(self, message: str):
        self.chat_view.display_system_message(message)

    def display_user_message(self, message: str):
        self.chat_view.display_user_message(message)

    def display_jarvis_message(self, message: str):
        self.chat_view.display_jarvis_message(message)
