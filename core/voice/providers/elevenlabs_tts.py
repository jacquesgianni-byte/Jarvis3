"""
ElevenLabs Text-to-Speech Provider

Streams audio from the ElevenLabs API and plays it via sounddevice.

Design:
    - Inherits VoiceProvider ? drop-in replacement for SystemTTSProvider.
    - API key read from environment only ? never stored in source or config.
    - Voice ID and speed configured at construction time.
    - Interruption: stop flag checked between audio chunks during playback.
    - Fallback: if API call fails, logs warning and returns silently.
      VoiceManager will continue operating; next speak() will retry.
    - No changes to VoiceWorker, VoiceManager, or SystemTTSProvider.

Audio pipeline:
    ElevenLabs API (streaming MP3)
        ?
    httpx streaming response (chunks)
        ?
    io.BytesIO buffer (accumulated)
        ?
    soundfile decode (PCM frames)
        ?
    sounddevice playback (chunked, stop-flag checked between chunks)
"""
from __future__ import annotations

import io
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Audio playback chunk size in frames.
# Smaller = faster stop response; larger = smoother playback.
_PLAYBACK_CHUNK_FRAMES = 4096

# ElevenLabs API endpoint
_API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsTTSProvider:
    """
    ElevenLabs Text-to-Speech provider.

    Reads ELEVENLABS_API_KEY from the environment.
    Falls back silently if the API is unavailable.
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str = "ydOzToQj00qmJ4VuQWPU",
        speed: float = 1.08,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> None:
        self._api_key         = api_key
        self._voice_id        = voice_id
        self._speed           = speed
        self._stability       = stability
        self._similarity_boost = similarity_boost
        self._stop_requested  = threading.Event()

    @classmethod
    def from_env(
        cls,
        voice_id: str = "ydOzToQj00qmJ4VuQWPU",
        speed: float = 1.08,
    ) -> Optional["ElevenLabsTTSProvider"]:
        """
        Construct from environment variable ELEVENLABS_API_KEY.
        Returns None if the key is not set.
        """
        api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not api_key:
            logger.info(
                "[ElevenLabsTTSProvider] ELEVENLABS_API_KEY not set ? provider not created."
            )
            return None
        return cls(api_key=api_key, voice_id=voice_id, speed=speed)

    def speak(self, text: str) -> None:
        """
        Synthesise and play text via ElevenLabs.
        Checks stop flag between audio chunks.
        Falls back silently on API error.
        """
        text = text.strip()
        if not text:
            return

        self._stop_requested.clear()

        try:
            audio_bytes = self._fetch_audio(text)
        except Exception as e:
            logger.warning(
                "[ElevenLabsTTSProvider] API call failed: %s ? skipping utterance.", e
            )
            return

        if audio_bytes is None or len(audio_bytes) == 0:
            logger.warning("[ElevenLabsTTSProvider] Empty audio response ? skipping.")
            return

        self._play_audio(audio_bytes)

    def stop(self) -> None:
        """
        Request playback stop at the next chunk boundary.
        Safe to call from any thread.
        """
        self._stop_requested.set()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_audio(self, text: str) -> bytes:
        """
        Call ElevenLabs API and return raw audio bytes (MP3).
        Raises on HTTP error.
        """
        import httpx

        url = f"{_API_BASE}/text-to-speech/{self._voice_id}"
        headers = {
            "xi-api-key":   self._api_key,
            "Content-Type": "application/json",
            "Accept":       "audio/mpeg",
        }
        payload = {
            "text":           text,
            "model_id":       "eleven_turbo_v2_5",
            "voice_settings": {
                "stability":        self._stability,
                "similarity_boost": self._similarity_boost,
                "speed":            self._speed,
            },
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.content

    def _play_audio(self, audio_bytes: bytes) -> None:
        """
        Decode MP3 bytes and play via sounddevice.
        Checks stop flag between chunks.
        """
        try:
            import soundfile as sf
            import sounddevice as sd
            import numpy as np

            buffer = io.BytesIO(audio_bytes)
            data, samplerate = sf.read(buffer, dtype="float32")

            # Mono: reshape to (frames, 1) for sounddevice
            if data.ndim == 1:
                data = data.reshape(-1, 1)

            total_frames = len(data)
            pos = 0

            while pos < total_frames:
                if self._stop_requested.is_set():
                    logger.info(
                        "[ElevenLabsTTSProvider] Playback stopped at chunk boundary."
                    )
                    return

                chunk = data[pos: pos + _PLAYBACK_CHUNK_FRAMES]
                sd.play(chunk, samplerate=samplerate)
                sd.wait()
                pos += _PLAYBACK_CHUNK_FRAMES

            logger.info("[ElevenLabsTTSProvider] Playback complete.")

        except Exception as e:
            logger.warning(
                "[ElevenLabsTTSProvider] Playback failed: %s", e
            )
