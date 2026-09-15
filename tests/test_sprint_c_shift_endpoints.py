"""
Sprint C — Shift Control Endpoint Tests v2
Genesis-081

Fixes from v1:
    - Set ORCHESTRATOR_TOKEN env var so auth passes in tests
    - Patch ShiftController at the correct import path inside the route
"""

from __future__ import annotations
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent():
    return MagicMock()


def _make_app(tmp_path):
    """Create test Flask app with all blueprints registered."""
    # Set token BEFORE importing app so _check_auth() finds it
    os.environ.setdefault("ORCHESTRATOR_TOKEN", "test-token-abc")
    from apps.server.app import create_app
    app = create_app(agent=_make_agent())
    app.config["project_root"] = tmp_path
    app.config["TESTING"] = True
    return app


def _headers():
    return {"X-Orchestrator-Token": os.environ.get("ORCHESTRATOR_TOKEN", "test-token-abc")}


def _wrong_headers():
    return {"X-Orchestrator-Token": "wrong-token"}


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestShiftEndpointAuth:

    def test_start_requires_auth(self, tmp_path):
        app = _make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post("/shift/start")
        assert resp.status_code == 401

    def test_stop_requires_auth(self, tmp_path):
        app = _make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post("/shift/stop")
        assert resp.status_code == 401

    def test_status_requires_auth(self, tmp_path):
        app = _make_app(tmp_path)
        with app.test_client() as c:
            resp = c.get("/shift/status")
        assert resp.status_code == 401

    def test_wrong_token_rejected(self, tmp_path):
        app = _make_app(tmp_path)
        with app.test_client() as c:
            resp = c.post("/shift/start", headers=_wrong_headers())
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /shift/start
# ---------------------------------------------------------------------------

class TestShiftStart:

    def test_start_returns_shift_id(self, tmp_path):
        app = _make_app(tmp_path)

        mock_ctrl = MagicMock()
        mock_ctrl.name = "shift_controller"
        mock_ctrl._manifest = MagicMock()
        mock_ctrl._manifest.shift_id = "test-shift-aaa"

        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True

        # ShiftController is imported locally inside the route function
        # Patch at the source module
        with patch("core.shift.shift_controller.ShiftController", return_value=mock_ctrl) as MockCtrl, \
             patch("threading.Thread", return_value=mock_thread):

            with app.test_client() as c:
                resp = c.post("/shift/start", headers=_headers())

        data = resp.get_json()
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
        assert data.get("status") == "started"
        assert "shift_id" in data

    def test_start_rejects_duplicate(self, tmp_path):
        """Second START while shift is running must be rejected."""
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)

        mock_ctrl = MagicMock()
        mock_ctrl.name = "shift_controller"

        original_ctrl = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            sr._active_shift_controller = mock_ctrl
            mock_thread = MagicMock(spec=threading.Thread)
            mock_thread.is_alive.return_value = True
            sr._active_shift_thread = mock_thread

            with app.test_client() as c:
                resp = c.post("/shift/start", headers=_headers())

            assert resp.status_code in (409, 400), \
                f"Expected 409 or 400, got {resp.status_code}"
            data = resp.get_json()
            assert "error" in data
        finally:
            sr._active_shift_controller = original_ctrl
            sr._active_shift_thread = original_thread

    def test_start_uses_worker_infrastructure(self, tmp_path):
        """ShiftController must be a Worker subclass."""
        from core.shift.shift_controller import ShiftController
        from core.workers.base import Worker
        assert issubclass(ShiftController, Worker), \
            "ShiftController must be a Worker subclass"

    def test_no_parallel_lifecycle_mechanism(self, tmp_path):
        """Only one active controller reference can exist at any time."""
        import apps.server.sprint_routes as sr
        assert hasattr(sr, "_active_shift_controller")
        assert hasattr(sr, "_active_shift_thread")

    def test_only_one_shift_at_a_time(self, tmp_path):
        """Concurrent START requests: second is rejected, still only one shift."""
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)
        original_ctrl = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            # Simulate running shift
            sr._active_shift_controller = MagicMock()
            mock_t = MagicMock(spec=threading.Thread)
            mock_t.is_alive.return_value = True
            sr._active_shift_thread = mock_t

            with app.test_client() as c:
                resp1 = c.post("/shift/start", headers=_headers())
                resp2 = c.post("/shift/start", headers=_headers())

            # Both should be rejected (shift already running)
            for resp in (resp1, resp2):
                assert resp.status_code in (409, 400)
        finally:
            sr._active_shift_controller = original_ctrl
            sr._active_shift_thread = original_thread


# ---------------------------------------------------------------------------
# POST /shift/stop
# ---------------------------------------------------------------------------

class TestShiftStop:

    def test_stop_returns_stop_requested_not_stopped(self, tmp_path):
        """
        POST /shift/stop must return stop_requested, NEVER stopped.
        """
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)
        mock_ctrl = MagicMock()
        mock_ctrl.name = "shift_controller"

        original = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            sr._active_shift_controller = mock_ctrl
            mock_t = MagicMock(spec=threading.Thread)
            mock_t.is_alive.return_value = True
            sr._active_shift_thread = mock_t

            with app.test_client() as c:
                resp = c.post("/shift/stop", headers=_headers())

            assert resp.status_code == 200, f"Got {resp.status_code}: {resp.get_json()}"
            data = resp.get_json()
            assert data.get("status") == "stop_requested", \
                f"Must be stop_requested, not {data.get('status')!r}"
            assert data.get("status") != "stopped", \
                "Must NOT return stopped — only status poll can confirm that"
            mock_ctrl.request_stop.assert_called_once()
        finally:
            sr._active_shift_controller = original
            sr._active_shift_thread = original_thread

    def test_stop_when_no_shift_running_returns_error(self, tmp_path):
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)
        original = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            sr._active_shift_controller = None
            sr._active_shift_thread = None

            with app.test_client() as c:
                resp = c.post("/shift/stop", headers=_headers())

            assert resp.status_code in (400, 404, 409), \
                f"Expected error status, got {resp.status_code}"
            data = resp.get_json()
            assert "error" in data
        finally:
            sr._active_shift_controller = original
            sr._active_shift_thread = original_thread

    def test_stop_calls_request_stop_not_cancel(self, tmp_path):
        """Must call request_stop() not Worker.cancel()."""
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)
        mock_ctrl = MagicMock()

        original = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            sr._active_shift_controller = mock_ctrl
            mock_t = MagicMock(spec=threading.Thread)
            mock_t.is_alive.return_value = True
            sr._active_shift_thread = mock_t

            with app.test_client() as c:
                c.post("/shift/stop", headers=_headers())

            mock_ctrl.request_stop.assert_called_once()
            mock_ctrl.cancel.assert_not_called()
        finally:
            sr._active_shift_controller = original
            sr._active_shift_thread = original_thread


# ---------------------------------------------------------------------------
# GET /shift/status
# ---------------------------------------------------------------------------

class TestShiftStatus:

    def test_status_idle_when_no_shift(self, tmp_path):
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)
        original = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            sr._active_shift_controller = None
            sr._active_shift_thread = None

            with app.test_client() as c:
                resp = c.get("/shift/status", headers=_headers())

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["running"] is False
            assert data["shift_id"] is None
            assert data["shift_state"] is None
        finally:
            sr._active_shift_controller = original
            sr._active_shift_thread = original_thread

    def test_status_running_true_while_active(self, tmp_path):
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)
        mock_ctrl = MagicMock()
        mock_ctrl._manifest = MagicMock()
        mock_ctrl._manifest.shift_id = "test-shift-123"
        mock_ctrl._manifest.stop_reason = None
        mock_ctrl._shift_state = MagicMock()
        mock_ctrl._shift_state.label.return_value = "DISCOVERING"

        original = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            sr._active_shift_controller = mock_ctrl
            mock_t = MagicMock(spec=threading.Thread)
            mock_t.is_alive.return_value = True
            sr._active_shift_thread = mock_t

            with app.test_client() as c:
                resp = c.get("/shift/status", headers=_headers())

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["running"] is True
            assert data["shift_id"] == "test-shift-123"
            assert data["shift_state"] == "DISCOVERING"
        finally:
            sr._active_shift_controller = original
            sr._active_shift_thread = original_thread

    def test_status_running_false_after_thread_ends(self, tmp_path):
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)
        mock_ctrl = MagicMock()
        mock_ctrl._manifest = MagicMock()
        mock_ctrl._manifest.shift_id = "test-shift-456"
        mock_ctrl._manifest.stop_reason = MagicMock()
        mock_ctrl._manifest.stop_reason.label.return_value = "HARD_STOP_REMOTE_STOP"
        mock_ctrl._shift_state = MagicMock()
        mock_ctrl._shift_state.label.return_value = "HARD_STOP"

        original = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            sr._active_shift_controller = mock_ctrl
            mock_t = MagicMock(spec=threading.Thread)
            mock_t.is_alive.return_value = False
            sr._active_shift_thread = mock_t

            with app.test_client() as c:
                resp = c.get("/shift/status", headers=_headers())

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["running"] is False
        finally:
            sr._active_shift_controller = original
            sr._active_shift_thread = original_thread

    def test_stop_reason_present_after_remote_stop(self, tmp_path):
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)
        mock_ctrl = MagicMock()
        mock_ctrl._manifest = MagicMock()
        mock_ctrl._manifest.shift_id = "test-shift-789"
        mock_ctrl._manifest.stop_reason = MagicMock()
        mock_ctrl._manifest.stop_reason.label.return_value = "HARD_STOP_REMOTE_STOP"
        mock_ctrl._shift_state = MagicMock()
        mock_ctrl._shift_state.label.return_value = "HARD_STOP"

        original = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            sr._active_shift_controller = mock_ctrl
            mock_t = MagicMock(spec=threading.Thread)
            mock_t.is_alive.return_value = False
            sr._active_shift_thread = mock_t

            with app.test_client() as c:
                resp = c.get("/shift/status", headers=_headers())

            data = resp.get_json()
            assert data.get("stop_reason") == "HARD_STOP_REMOTE_STOP"
        finally:
            sr._active_shift_controller = original
            sr._active_shift_thread = original_thread

    def test_status_response_shape(self, tmp_path):
        """GET /shift/status must always return all four fields."""
        import apps.server.sprint_routes as sr

        app = _make_app(tmp_path)
        original = sr._active_shift_controller
        original_thread = sr._active_shift_thread
        try:
            sr._active_shift_controller = None
            sr._active_shift_thread = None

            with app.test_client() as c:
                resp = c.get("/shift/status", headers=_headers())

            data = resp.get_json()
            required = {"running", "shift_id", "shift_state", "stop_reason"}
            assert required.issubset(set(data.keys())), \
                f"Missing: {required - set(data.keys())}"
        finally:
            sr._active_shift_controller = original
            sr._active_shift_thread = original_thread
