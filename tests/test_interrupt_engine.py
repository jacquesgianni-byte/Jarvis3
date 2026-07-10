"""Unit tests for the Conversation Interrupt Engine (Genesis-011 Task 002).

Covers every scenario required by the spec:
  * First request becomes active.
  * Second request interrupts the first.
  * Generation numbers increment correctly.
  * Old tokens become invalid.
  * Current token remains valid.
  * Completed requests are tracked correctly.
  * Multiple rapid requests behave correctly.
  * Edge cases involving repeated interruptions.
Plus extras: thread safety, illegal transitions, cancel/stop semantics.
"""

import sys
import threading
from pathlib import Path

import pytest

# Make the project root importable when running from the tests folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.conversation import (
    InterruptManager,
    InvalidStatusTransitionError,
    RequestStatus,
    RequestToken,
)


# ----------------------------------------------------------------------
# RequestToken basics
# ----------------------------------------------------------------------
class TestRequestToken:
    def test_new_token_is_active(self):
        token = RequestToken(generation=1)
        assert token.status is RequestStatus.ACTIVE
        assert token.is_active
        assert not token.is_terminal

    def test_identity_fields_are_read_only(self):
        token = RequestToken(generation=1)
        with pytest.raises(AttributeError):
            token.id = "hacked"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            token.generation = 99  # type: ignore[misc]
        with pytest.raises(AttributeError):
            token.status = RequestStatus.COMPLETED  # type: ignore[misc]

    def test_generation_must_be_positive(self):
        with pytest.raises(ValueError):
            RequestToken(generation=0)

    def test_tokens_have_unique_ids(self):
        ids = {RequestToken(generation=i + 1).id for i in range(100)}
        assert len(ids) == 100

    def test_terminal_states_are_final(self):
        token = RequestToken(generation=1)
        token._mark_completed()
        with pytest.raises(InvalidStatusTransitionError):
            token._mark_interrupted()
        with pytest.raises(InvalidStatusTransitionError):
            token._mark_cancelled()

    def test_same_state_transition_is_noop(self):
        token = RequestToken(generation=1)
        token._mark_completed()
        token._mark_completed()  # no exception
        assert token.status is RequestStatus.COMPLETED

    def test_equality_is_identity_based(self):
        a = RequestToken(generation=1)
        b = RequestToken(generation=1)
        assert a == a
        assert a != b
        assert len({a, b}) == 2


# ----------------------------------------------------------------------
# Spec-required behaviour
# ----------------------------------------------------------------------
class TestInterruptManager:
    def test_first_request_becomes_active(self):
        mgr = InterruptManager()
        token = mgr.new_request()
        assert token.is_active
        assert mgr.active_token is token
        assert mgr.is_current(token)

    def test_second_request_interrupts_first(self):
        mgr = InterruptManager()
        first = mgr.new_request()
        second = mgr.new_request()
        assert first.status is RequestStatus.INTERRUPTED
        assert second.is_active
        assert mgr.active_token is second

    def test_generation_numbers_increment(self):
        mgr = InterruptManager()
        assert mgr.generation == 0
        tokens = [mgr.new_request() for _ in range(5)]
        assert [t.generation for t in tokens] == [1, 2, 3, 4, 5]
        assert mgr.generation == 5

    def test_old_tokens_become_invalid(self):
        mgr = InterruptManager()
        old = mgr.new_request()
        mgr.new_request()
        assert not mgr.is_current(old)

    def test_current_token_remains_valid(self):
        mgr = InterruptManager()
        mgr.new_request()
        mgr.new_request()
        current = mgr.new_request()
        assert mgr.is_current(current)

    def test_completed_requests_tracked(self):
        mgr = InterruptManager()
        token = mgr.new_request()
        assert mgr.complete(token) is True
        assert token.status is RequestStatus.COMPLETED
        assert mgr.completed_count() == 1
        # A completed token no longer owns the conversation.
        assert not mgr.is_current(token)

    def test_stale_completion_is_silently_rejected(self):
        """Simulates a slow AI response arriving after a newer request."""
        mgr = InterruptManager()
        slow = mgr.new_request()
        fast = mgr.new_request()  # user asked something else
        # Old response finally arrives:
        assert mgr.complete(slow) is False   # discard, don't deliver
        assert slow.status is RequestStatus.INTERRUPTED
        # New response arrives:
        assert mgr.complete(fast) is True    # deliver

    def test_multiple_rapid_requests(self):
        mgr = InterruptManager()
        tokens = [mgr.new_request() for _ in range(50)]
        # Only the last one is current.
        for t in tokens[:-1]:
            assert t.status is RequestStatus.INTERRUPTED
            assert not mgr.is_current(t)
        assert mgr.is_current(tokens[-1])
        assert mgr.interrupted_count() == 49

    def test_repeated_interruptions_edge_case(self):
        """Interrupt, complete, interrupt again — statuses never corrupt."""
        mgr = InterruptManager()
        a = mgr.new_request()
        b = mgr.new_request()          # interrupts a
        assert mgr.complete(b)          # b completes normally
        c = mgr.new_request()           # nothing active; must not raise
        d = mgr.new_request()           # interrupts c
        assert a.status is RequestStatus.INTERRUPTED
        assert b.status is RequestStatus.COMPLETED
        assert c.status is RequestStatus.INTERRUPTED
        assert d.is_active
        assert mgr.generation == 4

    def test_is_current_with_none(self):
        mgr = InterruptManager()
        assert mgr.is_current(None) is False

    def test_active_token_none_before_first_request(self):
        mgr = InterruptManager()
        assert mgr.active_token is None

    def test_active_token_none_after_completion(self):
        mgr = InterruptManager()
        token = mgr.new_request()
        mgr.complete(token)
        assert mgr.active_token is None

    def test_history(self):
        mgr = InterruptManager()
        tokens = [mgr.new_request() for _ in range(3)]
        assert mgr.history() == tokens
        assert mgr.history(limit=2) == tokens[1:]


# ----------------------------------------------------------------------
# Stop button / cancellation semantics
# ----------------------------------------------------------------------
class TestInterruptAndCancel:
    def test_interrupt_all_stops_active_request(self):
        mgr = InterruptManager()
        token = mgr.new_request()
        stopped = mgr.interrupt_all()
        assert stopped is token
        assert token.status is RequestStatus.INTERRUPTED
        assert mgr.active_token is None
        assert not mgr.is_current(token)

    def test_interrupt_all_with_nothing_active(self):
        mgr = InterruptManager()
        assert mgr.interrupt_all() is None

    def test_cancel_active_token(self):
        mgr = InterruptManager()
        token = mgr.new_request()
        assert mgr.cancel(token) is True
        assert token.status is RequestStatus.CANCELLED
        assert mgr.active_token is None

    def test_cancel_stale_token_is_noop(self):
        mgr = InterruptManager()
        old = mgr.new_request()
        mgr.new_request()
        assert mgr.cancel(old) is False
        assert old.status is RequestStatus.INTERRUPTED  # unchanged

    def test_new_request_after_interrupt_all(self):
        mgr = InterruptManager()
        mgr.new_request()
        mgr.interrupt_all()
        fresh = mgr.new_request()
        assert fresh.is_active
        assert fresh.generation == 2


# ----------------------------------------------------------------------
# Thread safety
# ----------------------------------------------------------------------
class TestThreadSafety:
    def test_concurrent_new_requests_unique_generations(self):
        mgr = InterruptManager()
        results = []
        lock = threading.Lock()

        def worker():
            for _ in range(100):
                token = mgr.new_request()
                with lock:
                    results.append(token.generation)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 800
        assert len(set(results)) == 800          # no duplicate generations
        assert mgr.generation == 800
        # Exactly one token can still be active.
        active = [t for t in mgr.history() if t.is_active]
        assert len(active) == 1

    def test_concurrent_complete_only_delivers_once(self):
        """Many threads race to complete the same token; only one wins."""
        mgr = InterruptManager()
        token = mgr.new_request()
        wins = []
        lock = threading.Lock()

        def worker():
            if mgr.complete(token):
                with lock:
                    wins.append(True)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(wins) == 1
        assert token.status is RequestStatus.COMPLETED