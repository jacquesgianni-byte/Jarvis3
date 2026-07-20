"""
Genesis-023 MP-001 Sprint-001 — Desktop Presence Foundation Tests
Completely self-contained. No Qt dependencies.

Coverage:
  EventBus:
    - subscribe + emit (legacy, unchanged)
    - unsubscribe removes handler
    - unsubscribe unknown callback safe
    - unsubscribe twice safe
    - multiple subscribers
    - emit with no subscribers safe
    - global event_bus preserved

  PresenceEvents:
    - STATE_CHANGED constant exists and correct value
    - cannot instantiate

  DesktopState:
    - all five states exist
    - labels correct, values unique

  PresenceController:
    - initial state IDLE
    - set_state changes state
    - duplicate transition ignored (no event emitted)
    - reset returns to IDLE
    - reset from IDLE idempotent
    - event emitted on valid transition
    - event carries old_state and new_state kwargs
    - state property read-only
    - summary / repr

  DesktopCoordinator:
    - presence controller accessible
    - presence initially IDLE
    - uses injected bus
    - shutdown resets presence to IDLE
    - shutdown twice safe
    - repr

  Integration:
    - set_state → bus → subscriber receives event
    - multiple transitions in order
    - shutdown emits IDLE transition

  No Qt in any new file
  Backward compatibility
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.events import EventBus, event_bus
from apps.desktop.presence.presence_events import PresenceEvents
from apps.desktop.presence.presence_controller import PresenceController, DesktopState
from apps.desktop.coordinator import DesktopCoordinator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bus() -> EventBus:
    return EventBus()


def make_controller(bus=None) -> PresenceController:
    return PresenceController(event_bus=bus or make_bus())


def make_coordinator(bus=None) -> DesktopCoordinator:
    return DesktopCoordinator(event_bus=bus or make_bus())


def capture(bus: EventBus, event_name: str) -> list[dict]:
    """Subscribe and capture kwargs dicts from emit() calls."""
    received = []
    bus.subscribe(event_name, lambda **kw: received.append(kw))
    return received


# ===========================================================================
# 1. EVENT BUS
# ===========================================================================

class TestEventBus:

    def test_subscribe_and_emit(self):
        bus = make_bus()
        received = []
        bus.subscribe("TEST", lambda x: received.append(x))
        bus.emit("TEST", "hello")
        assert received == ["hello"]

    def test_emit_kwargs(self):
        bus = make_bus()
        received = []
        bus.subscribe("TEST", lambda **kw: received.append(kw))
        bus.emit("TEST", key="value")
        assert received[0]["key"] == "value"

    def test_multiple_subscribers_all_called(self):
        bus = make_bus()
        r1, r2 = [], []
        bus.subscribe("TEST", r1.append)
        bus.subscribe("TEST", r2.append)
        bus.emit("TEST", "x")
        assert r1 == ["x"] and r2 == ["x"]

    def test_emit_no_subscribers_safe(self):
        make_bus().emit("UNSUBSCRIBED")  # must not raise

    def test_unsubscribe_removes_handler(self):
        bus = make_bus()
        received = []
        cb = received.append
        bus.subscribe("TEST", cb)
        bus.unsubscribe("TEST", cb)
        bus.emit("TEST", "x")
        assert received == []

    def test_unsubscribe_unknown_callback_safe(self):
        bus = make_bus()
        bus.unsubscribe("NEVER_SUBSCRIBED", lambda x: None)  # must not raise

    def test_unsubscribe_twice_safe(self):
        bus = make_bus()
        cb = lambda x: None
        bus.subscribe("TEST", cb)
        bus.unsubscribe("TEST", cb)
        bus.unsubscribe("TEST", cb)  # must not raise

    def test_unsubscribe_only_removes_one(self):
        bus = make_bus()
        r1, r2 = [], []
        bus.subscribe("TEST", r1.append)
        bus.subscribe("TEST", r2.append)
        bus.unsubscribe("TEST", r1.append)
        bus.emit("TEST", "x")
        assert r2 == ["x"]

    def test_global_event_bus_exists(self):
        assert isinstance(event_bus, EventBus)

    def test_global_event_bus_subscribe_works(self):
        received = []
        cb = received.append
        event_bus.subscribe("MP001_GLOBAL_TEST", cb)
        event_bus.emit("MP001_GLOBAL_TEST", "ok")
        event_bus.unsubscribe("MP001_GLOBAL_TEST", cb)
        assert "ok" in received


# ===========================================================================
# 2. PRESENCE EVENTS
# ===========================================================================

class TestPresenceEvents:

    def test_state_changed_constant(self):
        assert PresenceEvents.STATE_CHANGED == "PRESENCE_STATE_CHANGED"

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            PresenceEvents()


# ===========================================================================
# 3. DESKTOP STATE
# ===========================================================================

class TestDesktopState:

    def test_all_states_exist(self):
        for name in ["IDLE", "LISTENING", "THINKING", "SPEAKING", "ERROR"]:
            assert hasattr(DesktopState, name)

    def test_values_unique(self):
        values = [s.value for s in DesktopState]
        assert len(values) == len(set(values))

    def test_labels(self):
        assert DesktopState.IDLE.label()      == "Idle"
        assert DesktopState.LISTENING.label() == "Listening"
        assert DesktopState.THINKING.label()  == "Thinking"
        assert DesktopState.SPEAKING.label()  == "Speaking"
        assert DesktopState.ERROR.label()     == "Error"


# ===========================================================================
# 4. PRESENCE CONTROLLER
# ===========================================================================

class TestPresenceControllerDefaults:

    def test_initial_state_is_idle(self):
        assert make_controller().state == DesktopState.IDLE

    def test_state_property_read_only(self):
        with pytest.raises(AttributeError):
            make_controller().state = DesktopState.THINKING


class TestPresenceControllerSetState:

    def test_set_state_changes_state(self):
        c = make_controller()
        c.set_state(DesktopState.THINKING)
        assert c.state == DesktopState.THINKING

    def test_all_states_reachable(self):
        c = make_controller()
        for state in DesktopState:
            if state != DesktopState.IDLE:
                c.set_state(state)
                assert c.state == state
                c.reset()

    def test_duplicate_ignored_no_event(self):
        bus = make_bus()
        c = make_controller(bus)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        c.set_state(DesktopState.THINKING)
        c.set_state(DesktopState.THINKING)  # duplicate
        assert len(received) == 1

    def test_emits_event_on_valid_transition(self):
        bus = make_bus()
        c = make_controller(bus)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        c.set_state(DesktopState.LISTENING)
        assert len(received) == 1

    def test_event_has_old_state(self):
        bus = make_bus()
        c = make_controller(bus)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        c.set_state(DesktopState.LISTENING)
        assert received[0]["old_state"] == "IDLE"

    def test_event_has_new_state(self):
        bus = make_bus()
        c = make_controller(bus)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        c.set_state(DesktopState.LISTENING)
        assert received[0]["new_state"] == "LISTENING"


class TestPresenceControllerReset:

    def test_reset_returns_to_idle(self):
        c = make_controller()
        c.set_state(DesktopState.THINKING)
        c.reset()
        assert c.state == DesktopState.IDLE

    def test_reset_from_idle_idempotent(self):
        bus = make_bus()
        c = make_controller(bus)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        c.reset()
        assert len(received) == 0

    def test_reset_emits_event_when_not_idle(self):
        bus = make_bus()
        c = make_controller(bus)
        c.set_state(DesktopState.ERROR)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        c.reset()
        assert received[0]["new_state"] == "IDLE"


class TestPresenceControllerIntrospection:

    def test_summary_has_state(self):
        assert make_controller().summary()["state"] == "IDLE"

    def test_repr_includes_state(self):
        assert "Idle" in repr(make_controller())


# ===========================================================================
# 5. DESKTOP COORDINATOR
# ===========================================================================

class TestDesktopCoordinator:

    def test_has_presence_controller(self):
        assert isinstance(make_coordinator().presence, PresenceController)

    def test_presence_initially_idle(self):
        assert make_coordinator().presence.state == DesktopState.IDLE

    def test_uses_injected_bus(self):
        bus = make_bus()
        coord = DesktopCoordinator(event_bus=bus)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        coord.presence.set_state(DesktopState.LISTENING)
        assert len(received) == 1

    def test_shutdown_resets_presence_to_idle(self):
        coord = make_coordinator()
        coord.presence.set_state(DesktopState.THINKING)
        coord.shutdown()
        assert coord.presence.state == DesktopState.IDLE

    def test_shutdown_twice_safe(self):
        coord = make_coordinator()
        coord.shutdown()
        coord.shutdown()  # must not raise

    def test_repr_includes_presence(self):
        assert "Idle" in repr(make_coordinator())


# ===========================================================================
# 6. INTEGRATION
# ===========================================================================

class TestIntegration:

    def test_full_flow(self):
        bus = make_bus()
        coord = DesktopCoordinator(event_bus=bus)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        coord.presence.set_state(DesktopState.THINKING)
        assert received[0]["old_state"] == "IDLE"
        assert received[0]["new_state"] == "THINKING"

    def test_multiple_transitions_in_order(self):
        bus = make_bus()
        coord = DesktopCoordinator(event_bus=bus)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        coord.presence.set_state(DesktopState.LISTENING)
        coord.presence.set_state(DesktopState.THINKING)
        coord.presence.set_state(DesktopState.SPEAKING)
        coord.presence.reset()
        assert [e["new_state"] for e in received] == [
            "LISTENING", "THINKING", "SPEAKING", "IDLE"
        ]

    def test_shutdown_emits_idle(self):
        bus = make_bus()
        coord = DesktopCoordinator(event_bus=bus)
        coord.presence.set_state(DesktopState.ERROR)
        received = capture(bus, PresenceEvents.STATE_CHANGED)
        coord.shutdown()
        assert received[0]["new_state"] == "IDLE"

    def test_multiple_subscribers_all_notified(self):
        bus = make_bus()
        coord = DesktopCoordinator(event_bus=bus)
        r1, r2 = [], []
        bus.subscribe(PresenceEvents.STATE_CHANGED, lambda **kw: r1.append(kw))
        bus.subscribe(PresenceEvents.STATE_CHANGED, lambda **kw: r2.append(kw))
        coord.presence.set_state(DesktopState.THINKING)
        assert len(r1) == 1 and len(r2) == 1


# ===========================================================================
# 7. NO QT / BACKWARD COMPATIBILITY
# ===========================================================================

class TestNoQtAndBackwardCompat:

    def _read(self, *path_parts) -> str:
        return (Path(REPO_ROOT) / Path(*path_parts)).read_text()

    def test_no_qt_in_events(self):
        assert "PySide6" not in self._read("core", "events.py")

    def test_no_qt_in_presence_controller(self):
        assert "PySide6" not in self._read(
            "apps", "desktop", "presence", "presence_controller.py"
        )

    def test_no_qt_in_coordinator(self):
        assert "PySide6" not in self._read("apps", "desktop", "coordinator.py")

    def test_global_event_bus_preserved(self):
        from core.events import event_bus, EventBus
        assert isinstance(event_bus, EventBus)

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_genesis_022_engine_unchanged(self):
        from core.conversation.conversation_engine import ConversationEngine
        assert ConversationEngine().process("Hello.") is not None

    def test_genesis_021_workers_unchanged(self):
        from core.workers.manager import WorkerManager
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(EngineeringWorker())
        assert m.has_worker("engineering")