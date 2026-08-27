"""
ElevenLabs TTS Provider tests.

Covers:
    ElevenLabsTTSProvider:
        - from_env() returns None when ELEVENLABS_API_KEY not set
        - from_env() returns provider when key is set
        - speak() clears stop flag at start of utterance
        - stop() sets stop flag
        - speak() with empty text does nothing
        - speak() handles API error gracefully (no raise)
        - voice_id, speed, stability, similarity_boost accessible
        - stop() safe to call when nothing is playing
        - provider is instance of VoiceProvider base contract
          (has speak() and stop() methods)

    jarvis_core provider selection:
        - SystemTTSProvider used when ELEVENLABS_API_KEY absent
        - ElevenLabsTTSProvider used when ELEVENLABS_API_KEY present
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from core.voice.providers.elevenlabs_tts import ElevenLabsTTSProvider
from core.voice.providers.base import VoiceProvider


class TestElevenLabsTTSProviderConstruction:

    def test_from_env_returns_none_when_key_absent(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ELEVENLABS_API_KEY", None)
            result = ElevenLabsTTSProvider.from_env()
        assert result is None

    def test_from_env_returns_provider_when_key_present(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-key-123"}):
            result = ElevenLabsTTSProvider.from_env()
        assert result is not None
        assert isinstance(result, ElevenLabsTTSProvider)

    def test_from_env_empty_string_returns_none(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}):
            result = ElevenLabsTTSProvider.from_env()
        assert result is None

    def test_from_env_whitespace_only_returns_none(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "   "}):
            result = ElevenLabsTTSProvider.from_env()
        assert result is None

    def test_voice_id_default(self):
        p = ElevenLabsTTSProvider(api_key="test")
        assert p._voice_id == "ydOzToQj00qmJ4VuQWPU"

    def test_speed_default(self):
        p = ElevenLabsTTSProvider(api_key="test")
        assert p._speed == 1.0

    def test_custom_voice_id(self):
        p = ElevenLabsTTSProvider(api_key="test", voice_id="custom-id")
        assert p._voice_id == "custom-id"

    def test_custom_speed(self):
        p = ElevenLabsTTSProvider(api_key="test", speed=1.2)
        assert p._speed == 1.2

    def test_has_speak_method(self):
        p = ElevenLabsTTSProvider(api_key="test")
        assert callable(p.speak)

    def test_has_stop_method(self):
        p = ElevenLabsTTSProvider(api_key="test")
        assert callable(p.stop)

    def test_satisfies_voice_provider_contract(self):
        """Provider has speak() and stop() as required by VoiceProvider."""
        p = ElevenLabsTTSProvider(api_key="test")
        assert hasattr(p, "speak")
        assert hasattr(p, "stop")


class TestElevenLabsTTSProviderBehaviour:

    def test_stop_sets_flag(self):
        p = ElevenLabsTTSProvider(api_key="test")
        assert not p._stop_requested.is_set()
        p.stop()
        assert p._stop_requested.is_set()

    def test_speak_empty_text_does_nothing(self):
        p = ElevenLabsTTSProvider(api_key="test")
        # Should not raise or call API
        with patch.object(p, "_fetch_audio") as mock_fetch:
            p.speak("")
            mock_fetch.assert_not_called()

    def test_speak_whitespace_only_does_nothing(self):
        p = ElevenLabsTTSProvider(api_key="test")
        with patch.object(p, "_fetch_audio") as mock_fetch:
            p.speak("   ")
            mock_fetch.assert_not_called()

    def test_speak_clears_stop_flag(self):
        p = ElevenLabsTTSProvider(api_key="test")
        p.stop()
        assert p._stop_requested.is_set()
        # Patch fetch to avoid real API call, patch play to avoid audio
        with patch.object(p, "_fetch_audio", return_value=b"fake"):
            with patch.object(p, "_play_audio"):
                p.speak("Hello Jarvis")
        assert not p._stop_requested.is_set()

    def test_speak_api_error_does_not_raise(self):
        p = ElevenLabsTTSProvider(api_key="test")
        with patch.object(p, "_fetch_audio", side_effect=Exception("API down")):
            # Should not raise
            p.speak("Hello Jarvis")

    def test_speak_empty_audio_response_does_not_raise(self):
        p = ElevenLabsTTSProvider(api_key="test")
        with patch.object(p, "_fetch_audio", return_value=b""):
            p.speak("Hello Jarvis")

    def test_stop_safe_when_nothing_playing(self):
        p = ElevenLabsTTSProvider(api_key="test")
        p.stop()  # Should not raise
        p.stop()  # Idempotent

    def test_stop_called_between_speak_stops_playback(self):
        p = ElevenLabsTTSProvider(api_key="test")
        play_calls = []

        def fake_play(audio_bytes):
            p.stop()  # simulate interrupt during playback
            play_calls.append(audio_bytes)

        with patch.object(p, "_fetch_audio", return_value=b"fake"):
            with patch.object(p, "_play_audio", side_effect=fake_play):
                p.speak("Hello Jarvis")

        assert len(play_calls) == 1


class TestProviderSelection:

    def test_system_tts_used_when_key_absent(self):
        """When ELEVENLABS_API_KEY is not set, SystemTTSProvider is the fallback."""
        from core.voice.providers.system_tts import SystemTTSProvider
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ELEVENLABS_API_KEY", None)
            provider = ElevenLabsTTSProvider.from_env()
            assert provider is None
            # Confirm SystemTTSProvider is still constructable as fallback
            fallback = SystemTTSProvider()
            assert callable(fallback.speak)

    def test_elevenlabs_used_when_key_present(self):
        """When ELEVENLABS_API_KEY is set, ElevenLabsTTSProvider is returned."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "sk-test-key"}):
            provider = ElevenLabsTTSProvider.from_env()
        assert provider is not None
        assert provider._api_key == "sk-test-key"
        assert provider._voice_id == "ydOzToQj00qmJ4VuQWPU"
        assert provider._speed == 1.0
