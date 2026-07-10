"""
System Text-to-Speech Provider

Uses the system speech engine via pyttsx3.

Implementation Notes
--------------------
Thread Safety
    pyttsx3 has thread affinity on some platforms (Windows SAPI,
    macOS nsss). This provider is used exclusively by the VoiceWorker,
    ensuring all speech occurs on the dedicated background thread.

Windows Stability
    On Windows with SAPI, reusing the same pyttsx3 Engine instance has
    been observed to cause subsequent speech requests to fail after the
    first successful call to runAndWait(). A fresh Engine is therefore
    created for every chunk spoken.

Interruption (Genesis-011 Task 002.6, revised)
    Speech is NEVER stopped mid-utterance. Stopping an engine inside
    runAndWait() (e.g. from a word callback) can leave the engine — and
    pyttsx3's internal engine cache — in a wedged state on Windows,
    silently killing all future speech.

    Instead, the text is split into short chunks and the stop flag is
    checked BETWEEN chunks. Every chunk always runs to natural
    completion on its own fresh engine, so no engine is ever interrupted
    and nothing can wedge. Stop latency is at most one chunk (a few
    words).

    stop() may be called from any thread — it only sets a flag.
"""

import logging
import re
import threading

import pyttsx3

from core.voice.providers.base import VoiceProvider

logger = logging.getLogger(__name__)

# Maximum words per spoken chunk. Smaller = faster stop response but
# slightly choppier delivery; larger = smoother but slower to stop.
_MAX_CHUNK_WORDS = 12


class SystemTTSProvider(VoiceProvider):
    """
    System Text-to-Speech provider backed by pyttsx3.

    Speaks in short chunks, each on a fresh engine. Interruption takes
    effect at the next chunk boundary — engines are never stopped
    mid-utterance, which keeps Windows SAPI stable.
    """

    def __init__(self) -> None:
        """
        Initialise the provider.

        No speech engine is created here. A fresh engine is created for
        each chunk on the VoiceWorker background thread.
        """
        self._stop_requested = threading.Event()

    def speak(self, text: str) -> None:
        """
        Speak the supplied text, chunk by chunk.

        Checks the stop flag before every chunk; a stop request takes
        effect at the next chunk boundary.

        Args:
            text: The text to synthesise and speak.
        """

        text = text.strip()

        if not text:
            return

        # A fresh utterance always starts clean. Discarding of queued
        # (not yet started) utterances is governed by the VoiceWorker.
        self._stop_requested.clear()

        chunks = list(self._split_chunks(text))
        logger.info(
            "SystemTTSProvider: speech started (%d chunk(s), %d chars).",
            len(chunks), len(text),
        )

        for index, chunk in enumerate(chunks):
            if self._stop_requested.is_set():
                logger.info(
                    "SystemTTSProvider: speech stopped at chunk boundary (%d/%d spoken).",
                    index, len(chunks),
                )
                return
            self._speak_chunk(chunk)

        logger.info("SystemTTSProvider: speech completed (%d chunk(s)).", len(chunks))

    def stop(self) -> None:
        """
        Request that speech stop at the next chunk boundary.

        Safe to call from any thread — this only sets a flag. If nothing
        is currently speaking, it has no effect (the flag is cleared at
        the start of every utterance).
        """
        self._stop_requested.set()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _speak_chunk(self, chunk: str) -> None:
        """Speak one chunk to completion on a fresh engine."""

        engine = None

        try:
            engine = self._create_engine()
            engine.say(chunk)
            engine.runAndWait()

        except Exception:
            logger.exception("SystemTTSProvider failed while speaking a chunk.")

        finally:
            if engine is not None:
                try:
                    engine.stop()
                except Exception:
                    logger.exception(
                        "SystemTTSProvider failed while stopping the engine."
                    )
                # Drop our reference so pyttsx3's weak engine cache can
                # release it and the next init() builds a truly fresh one.
                del engine

    @staticmethod
    def _split_chunks(text: str):
        """
        Split text into speakable chunks.

        Splits on sentence-ending punctuation first, then caps each
        piece at _MAX_CHUNK_WORDS words so a single long sentence cannot
        delay a stop request indefinitely.
        """

        sentences = re.split(r"(?<=[.!?;:])\s+", text)

        for sentence in sentences:
            words = sentence.split()
            if not words:
                continue
            for i in range(0, len(words), _MAX_CHUNK_WORDS):
                yield " ".join(words[i:i + _MAX_CHUNK_WORDS])

    def _create_engine(self) -> pyttsx3.Engine:
        """
        Create and configure a new pyttsx3 engine.

        Returns:
            A configured pyttsx3 Engine instance.
        """

        engine = pyttsx3.init()
        engine.setProperty("rate", 180)
        engine.setProperty("volume", 1.0)

        return engine