"""
Jarvis OS Main Window (Genesis-023 MP-004 Sprint-006)

The primary application window for Jarvis OS Desktop.
Composes all widgets into the complete interface.

Genesis-011 Desktop Improvement — Input Independence:
    * The input field is never disabled; typing and speech are
      independent. Enter (with text) while Jarvis is thinking or
      speaking interrupts the current request and starts the new one.
    * Empty Enter never interrupts anything.

Genesis-011 Task 002 (Part 2) — Desktop Worker Integration:
    * The action button dispatches: Send when idle, Stop when processing.
    * Stop forwards to JarvisCore.stop() — the UI adds no interrupt logic.
    * JarvisCore.process() may return None, meaning a newer request owns
      the conversation; the worker result is then silently discarded.
    * Worker threads are tracked until finished so overlapping requests
      can never crash Qt ("QThread destroyed while running").

Genesis-023 MP-004 Sprint-006 — DesktopShell Integration:
    * Body area migrated from inline ChatView/InputBar to DesktopShell.
    * DesktopShell hosts ChatPage which owns ChatView and InputBar.
    * DesktopController introduced as the desktop behaviour coordinator.
    * SidebarWidget retained as a hidden compatibility layer so orb
      state calls continue to work without modification.

    TODO (Genesis-023 Sprint-008): Replace SidebarWidget compatibility
    layer with PresenceController + OrbController, then remove
    SidebarWidget completely.
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


class ProcessWorker(QObject):
    """
    Runs jarvis.process() on a background thread so the UI never blocks.

    The emitted result may be None — JarvisCore returns None when a newer
    request took ownership of the conversation while this one was being
    processed. The UI must silently discard None results.
    """

    finished = Signal(object)

    def __init__(self, jarvis, message: str, queued_at: float = None):
        super().__init__()
        self._jarvis = jarvis
        self._message = message
        self._queued_at = queued_at if queued_at is not None else time.perf_counter()

    def run(self):
        telemetry.begin_request(queued_at=self._queued_at)
        response = self._jarvis.process(self._message)
        telemetry.end_request()
        self.finished.emit(response)


class MainWindow(QMainWindow):
    """
    The main window for Jarvis OS Desktop.

    Sprint-006 layout:

        Header
        DesktopShell
            └── ChatPage (ChatView + InputBar)
        StatusBar

    SidebarWidget is instantiated but hidden — it serves as a
    compatibility shim for orb state calls until Sprint-007 replaces
    it with PresenceController + OrbController.
    """

    def __init__(self, jarvis):
        super().__init__()

        self.jarvis = jarvis
        self._busy = False

        # Speech lifecycle observation (Genesis-011 Task 002.6).
        self._awaiting_speech_end = False
        self._speech_timer = QTimer(self)
        self._speech_timer.setInterval(150)
        self._speech_timer.timeout.connect(self._check_speech_finished)

        # Live worker threads. Entries removed when thread finishes.
        self._jobs = []

        self.setWindowTitle(Theme.WINDOW_TITLE)
        self.resize(Theme.WINDOW_WIDTH, Theme.WINDOW_HEIGHT)
        self.setMinimumSize(900, 600)

        self._build_ui()
        self._apply_global_style()
        self._connect_signals()

        # Startup via controller — shows initial page.
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

        # Header — unchanged.
        self.header = HeaderWidget()
        root_layout.addWidget(self.header)

        # DesktopShell — owns all page navigation.
        # Sprint-006: ChatPage is the only registered page.
        self._shell = DesktopShell()
        root_layout.addWidget(self._shell, stretch=1)

        # SidebarWidget — hidden compatibility shim.
        # Retains set_orb_state() calls without visible presence.
        # TODO (Genesis-023 Sprint-007): Replace with PresenceController
        # + OrbController and remove SidebarWidget completely.
        self.sidebar = SidebarWidget()
        self.sidebar.setVisible(False)

        # DesktopController — coordinates shell and JarvisCore.
        self._controller = DesktopController(
            jarvis=self.jarvis,
            shell=self._shell,
        )

        # Status bar — unchanged.
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
    # Convenience accessors — route through DesktopShell's ChatPage
    # ------------------------------------------------------------------

    @property
    def chat_view(self):
        """The active ChatView, hosted inside ChatPage."""
        return self._shell.chat_page.chat_view

    @property
    def input_bar(self):
        """The active InputBar, hosted inside ChatPage."""
        return self._shell.chat_page.input_bar

    # ------------------------------------------------------------------
    # Message handling — unchanged from pre-Sprint-006
    # ------------------------------------------------------------------

    def _on_action_button(self):
        """
        Dispatch the send/stop button based on the input bar state.

        Idle       -> send the typed message.
        Processing -> stop the active request.
        """
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
        worker.finished.connect(self._on_response)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread: self._forget_job(t))

        self._jobs.append((thread, worker))
        thread.start()

    def _forget_job(self, thread):
        """Drop the finished thread's references so it can be collected."""
        self._jobs = [(t, w) for (t, w) in self._jobs if t is not thread]

    def _stop_request(self):
        """
        Stop the active request.

        The UI only forwards the request — JarvisCore owns all interrupt
        logic. Works in both phases:

        Thinking: ownership is released instantly; the abandoned worker
        keeps running and its discarded None result (arriving at
        _on_response) flips the status from "Stopping..." to "Ready".

        Speaking: JarvisCore halts speech at the next word boundary;
        the speech-watch timer observes silence and flips to "Ready"
        via _return_to_idle.
        """
        self.jarvis.stop()

        self.chat_view.hide_typing()
        self.status_bar_widget.set_status("Stopping...")
        self.sidebar.set_orb_state("idle")
        self._busy = False
        self.input_bar.set_processing(False)
        self.input_bar.focus()

    def _on_response(self, response):
        # None means a newer request owns the conversation (or Stop was
        # pressed). Silently discard and close out "Stopping..." if idle.
        if response is None:
            if not self._busy:
                self.status_bar_widget.set_status("Ready")
            return

        self.chat_view.hide_typing()
        self.chat_view.display_jarvis_message(response.message)
        self.sidebar.set_orb_state("speaking")
        self.status_bar_widget.set_status("Speaking...")

        if hasattr(response, "action") and response.action == "EXIT":
            self.status_bar_widget.set_status("Shutting down...")
            self.close()
            return

        self._awaiting_speech_end = True
        self._speech_timer.start()

    def _check_speech_finished(self):
        """Poll the voice state and return to Idle when speech truly ends."""
        if not self._awaiting_speech_end:
            self._speech_timer.stop()
            return

        if not self.jarvis.is_speaking:
            self._speech_timer.stop()
            self._return_to_idle()

    def _return_to_idle(self):
        self._busy = False
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
    # Public API — unchanged
    # ------------------------------------------------------------------

    def display_system_message(self, message: str):
        self.chat_view.display_system_message(message)

    def display_user_message(self, message: str):
        self.chat_view.display_user_message(message)

    def display_jarvis_message(self, message: str):
        self.chat_view.display_jarvis_message(message)