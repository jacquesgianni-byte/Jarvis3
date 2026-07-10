"""
Voice Worker

Runs speech synthesis on a dedicated background thread.
The UI never calls a voice provider directly — all speech requests
are queued and processed sequentially by this worker.

The worker accepts any VoiceProvider implementation.
It has no knowledge of pyttsx3, the UI, JarvisCore, or any AI provider.
Its sole responsibility is to own the queue and the background thread.
"""

import logging
import queue
import threading
from typing import Optional

from core.voice.providers.base import VoiceProvider

logger = logging.getLogger(__name__)

# Sentinel value used to signal the worker to shut down cleanly.
_SHUTDOWN_SIGNAL = None


class VoiceWorker:
    """
    Processes speech requests on a dedicated background thread.

    Accepts any VoiceProvider at construction time.
    Speech requests are queued and processed one at a time
    in the order they were received.

    The calling thread is never blocked waiting for speech to complete.
    """

    def __init__(self, provider: VoiceProvider) -> None:
        """
        Initialise the VoiceWorker.

        Args:
            provider: Any VoiceProvider implementation.
        """

        self._provider = provider
        self._queue: queue.Queue[Optional[str]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Interruption support (Genesis-011 Task 002.6).
        # _interrupt: set by stop_speaking(); queued-but-unstarted
        #             utterances are skipped while it is set. Cleared
        #             when new speech is legitimately queued.
        # _pending:   number of utterances queued or currently speaking.
        #             This is the source of truth for is_speaking().
        #             Incremented BEFORE enqueue, decremented AFTER the
        #             utterance finishes or is skipped — so there is no
        #             instant where speech is imminent but _pending is 0.
        self._interrupt = threading.Event()
        self._pending = 0

    def start(self) -> None:
        """
        Start the background worker thread.
        Safe to call only once.
        """

        with self._lock:
            if self._running:
                return

            self._running = True

            self._thread = threading.Thread(
                target=self._run,
                name="VoiceWorker",
                daemon=True,
            )
            self._thread.start()

    def speak(self, text: str) -> None:
        """
        Queue a speech request.
        Returns immediately.
        """

        text = text.strip()

        if not text:
            return

        with self._lock:
            if not self._running:
                return

            # New speech is a fresh start — lift any prior interruption
            # and count this utterance before it becomes visible to the
            # worker loop.
            self._interrupt.clear()
            self._pending += 1
            self._queue.put(text)

    def stop(self) -> None:
        """
        Shut the worker down cleanly.

        Any queued speech is completed before the thread exits.
        """

        with self._lock:
            if not self._running:
                return

            self._running = False

        self._queue.put(_SHUTDOWN_SIGNAL)

        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def is_running(self) -> bool:
        """
        Return True if the worker is running.
        """

        return self._running

    def stop_speaking(self) -> None:
        """
        Interrupt speech without shutting the worker down.

        Queued-but-unstarted utterances are discarded, and the provider
        is asked to halt the current utterance. The worker thread stays
        alive and will happily accept new speech afterwards.

        Safe to call from any thread. Distinct from stop(), which shuts
        the worker down entirely.
        """

        with self._lock:
            if not self._running:
                return

            self._interrupt.set()

            # Drain anything not yet started — but never swallow the
            # shutdown sentinel; put it back and stop draining.
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is _SHUTDOWN_SIGNAL:
                    self._queue.put(item)
                    break
                self._pending -= 1

        # Halt the utterance currently being spoken, if any. Providers
        # that cannot interrupt simply ignore this.
        self._provider.stop()

    def is_speaking(self) -> bool:
        """
        Return True while any utterance is queued or being spoken.
        """

        with self._lock:
            return self._pending > 0

    def _run(self) -> None:
        """
        Background worker loop.
        """

        try:
            while True:
                try:
                    text = self._queue.get()

                    if text is _SHUTDOWN_SIGNAL:
                        break

                    # Skip utterances that were queued before an
                    # interruption — they belong to a stopped response.
                    if self._interrupt.is_set():
                        with self._lock:
                            self._pending -= 1
                        continue

                    try:
                        self._provider.speak(text)
                    finally:
                        with self._lock:
                            self._pending -= 1

                except Exception:
                    logger.exception(
                        "VoiceWorker failed while processing speech request."
                    )

        finally:
            logger.info("VoiceWorker stopped.")