"""
Tests for Genesis-047 Sprint-002: InterfaceSource tagging.

Coverage:
    - InterfaceSource enum values and membership
    - PersistedTimelineEvent v2: interface_source field
    - from_dict() v1 compat: missing interface_source -> UNKNOWN
    - ConversationTimeline.set_interface_source() stamped on _persist()
    - Agent.process() accepts source kwarg, defaults to UNKNOWN
"""
from __future__ import annotations

import pytest

from core.conversation.interface_source import InterfaceSource
from core.conversation.timeline_repository import PersistedTimelineEvent


# ── InterfaceSource enum ──────────────────────────────────────────────────────

class TestInterfaceSourceEnum:
    def test_all_members_exist(self):
        names = {m.name for m in InterfaceSource}
        assert names == {"ANDROID", "DESKTOP", "HTTP", "VOICE", "UNKNOWN"}

    def test_values(self):
        assert InterfaceSource.ANDROID.value == "android"
        assert InterfaceSource.DESKTOP.value == "desktop"
        assert InterfaceSource.HTTP.value    == "http"
        assert InterfaceSource.VOICE.value   == "voice"
        assert InterfaceSource.UNKNOWN.value == "unknown"

    def test_default_is_unknown(self):
        # The safe default must always be UNKNOWN
        assert InterfaceSource.UNKNOWN.value == "unknown"

    def test_lookup_by_value(self):
        assert InterfaceSource("http")    is InterfaceSource.HTTP
        assert InterfaceSource("unknown") is InterfaceSource.UNKNOWN


# ── PersistedTimelineEvent v2 ─────────────────────────────────────────────────

def _make_event(**kwargs) -> PersistedTimelineEvent:
    defaults = dict(
        event_id="ev-001",
        session_id="sess-001",
        event_type="General",
        value="test value",
        turn=1,
        timestamp="2026-08-14T10:00:00Z",
        source="auto",
    )
    defaults.update(kwargs)
    return PersistedTimelineEvent(**defaults)


class TestPersistedTimelineEventV2:
    def test_default_interface_source_is_unknown(self):
        event = _make_event()
        assert event.interface_source == InterfaceSource.UNKNOWN.value

    def test_http_interface_source(self):
        event = _make_event(interface_source=InterfaceSource.HTTP.value)
        assert event.interface_source == "http"

    def test_schema_version_is_2(self):
        event = _make_event()
        assert event.schema_version == 2

    def test_to_dict_includes_interface_source(self):
        event = _make_event(interface_source=InterfaceSource.HTTP.value)
        d = event.to_dict()
        assert "interface_source" in d
        assert d["interface_source"] == "http"

    def test_to_dict_schema_version_2(self):
        event = _make_event()
        assert event.to_dict()["schema_version"] == 2


# ── from_dict() — v1 compat ───────────────────────────────────────────────────

class TestFromDictV1Compat:
    def _v1_dict(self, **kwargs) -> dict:
        """A v1 record — no interface_source key."""
        base = {
            "event_id":       "ev-v1",
            "session_id":     "sess-v1",
            "event_type":     "Decision",
            "value":          "use Python",
            "turn":           3,
            "timestamp":      "2026-08-13T07:00:00Z",
            "source":         "auto",
            "raw":            "",
            "schema_version": 1,
            # intentionally no interface_source
        }
        base.update(kwargs)
        return base

    def test_v1_loads_as_unknown(self):
        event = PersistedTimelineEvent.from_dict(self._v1_dict())
        assert event.interface_source == InterfaceSource.UNKNOWN.value

    def test_v2_loads_interface_source(self):
        d = self._v1_dict(interface_source="http", schema_version=2)
        event = PersistedTimelineEvent.from_dict(d)
        assert event.interface_source == "http"

    def test_unknown_value_loads_gracefully(self):
        d = self._v1_dict(interface_source="unknown", schema_version=2)
        event = PersistedTimelineEvent.from_dict(d)
        assert event.interface_source == "unknown"

    def test_missing_event_id_gets_uuid(self):
        d = self._v1_dict()
        del d["event_id"]
        event = PersistedTimelineEvent.from_dict(d)
        assert len(event.event_id) > 0

    def test_roundtrip_preserves_interface_source(self):
        event = _make_event(interface_source=InterfaceSource.HTTP.value)
        restored = PersistedTimelineEvent.from_dict(event.to_dict())
        assert restored.interface_source == "http"
        assert restored.schema_version == 2


# ── ConversationTimeline.set_interface_source() ───────────────────────────────

class TestConversationTimelineInterfaceSource:
    def _make_timeline(self):
        from core.conversation.conversation_timeline import ConversationTimeline
        return ConversationTimeline()

    def test_default_interface_source_is_unknown(self):
        tl = self._make_timeline()
        assert tl._interface_source is InterfaceSource.UNKNOWN

    def test_set_interface_source_http(self):
        tl = self._make_timeline()
        tl.set_interface_source(InterfaceSource.HTTP)
        assert tl._interface_source is InterfaceSource.HTTP

    def test_set_interface_source_persisted(self):
        """set_interface_source value is stamped on PersistedTimelineEvent."""
        from unittest.mock import MagicMock
        from core.conversation.timeline_repository import TimelineRepository

        saved = []

        class CapturingRepo(TimelineRepository):
            def save(self, event): saved.append(event)
            def load_by_session(self, sid): return []
            def load_by_date(self, d): return []
            def load_by_type(self, t, limit=100): return []
            def load_recent(self, days=7, limit=500): return []
            def purge_before(self, cutoff): return 0
            def count(self): return 0

        from core.conversation.conversation_timeline import ConversationTimeline
        tl = ConversationTimeline(repository=CapturingRepo())
        tl.set_session_id("sess-test")
        tl.set_interface_source(InterfaceSource.HTTP)
        tl.record_turn("hello jarvis", turn=1)

        assert len(saved) == 1
        assert saved[0].interface_source == "http"

    def test_set_interface_source_unknown_is_default_when_not_set(self):
        """If set_interface_source is never called, persisted value is unknown."""
        saved = []

        class CapturingRepo:
            def save(self, event): saved.append(event)
            def load_by_session(self, sid): return []
            def load_by_date(self, d): return []
            def load_by_type(self, t, limit=100): return []
            def load_recent(self, days=7, limit=500): return []
            def purge_before(self, cutoff): return 0
            def count(self): return 0

        from core.conversation.conversation_timeline import ConversationTimeline
        tl = ConversationTimeline(repository=CapturingRepo())
        tl.set_session_id("sess-test")
        tl.record_turn("hello", turn=1)

        assert saved[0].interface_source == "unknown"


# ── Agent.process() source kwarg ─────────────────────────────────────────────

class TestAgentProcessSourceKwarg:
    def _make_agent(self):
        from core.agent import Agent
        return Agent()

    def test_process_accepts_source_kwarg(self):
        agent = self._make_agent()
        # Should not raise
        response = agent.process("hello", source=InterfaceSource.HTTP)
        assert response is not None

    def test_process_default_source_is_unknown(self):
        """Calling process() without source= leaves timeline at UNKNOWN."""
        agent = self._make_agent()
        agent.process("hello")
        assert agent.timeline._interface_source is InterfaceSource.UNKNOWN

    def test_process_http_source_sets_timeline(self):
        agent = self._make_agent()
        agent.process("hello", source=InterfaceSource.HTTP)
        assert agent.timeline._interface_source is InterfaceSource.HTTP

    def test_process_unknown_source_explicit(self):
        agent = self._make_agent()
        agent.process("hello", source=InterfaceSource.UNKNOWN)
        assert agent.timeline._interface_source is InterfaceSource.UNKNOWN
