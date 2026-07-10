"""
Jarvis OS — Request Pipeline Telemetry

Timing instrumentation for the request pipeline (Genesis-011 Task 002.5).

Request identity
----------------
Telemetry does NOT invent its own request ids. The identity of a request
is its ``RequestToken`` — the same object that owns the conversation in
the InterruptManager. The ``req=N`` in every TIMING line is the token's
generation number, so telemetry correlates 1:1 with interrupt events.

Thread-local storage here is purely a *transport* mechanism: it carries
the bound token's id to code that must remain token-blind (the Agent
receives the token as opaque context and never inspects it). When
streaming/async execution arrives, ``threading.local`` will be replaced
by ``contextvars.ContextVar`` — an asyncio-aware drop-in — with no
changes to any call site.

Log format (machine-parseable, for the future Engineering Console F12)::

    TIMING | req=41 | stage=ai_manager | provider=openai | model=gpt-4.1-mini | 1823.0 ms

Usage::

    telemetry.begin_request(queued_at)   # worker thread, pipeline start
    telemetry.bind(token)                # JarvisCore, right after new_request()
    with telemetry.stage("agent_total"):
        ...
    telemetry.end_request()              # logs total_end_to_end
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

from core.logger import get_logger

# Per-thread request context. Transport only — identity comes from the
# bound RequestToken. Will become contextvars.ContextVar under async.
_local = threading.local()


def begin_request(queued_at: float | None = None) -> None:
    """Start timing on the current thread at pipeline entry.

    Args:
        queued_at: perf_counter timestamp of when the UI queued the
            request. If provided, the queue latency ("ui_to_worker") is
            emitted automatically once :func:`bind` supplies the request
            identity.
    """
    _local.req_id = None
    _local.start = time.perf_counter()
    _local.queued_at = queued_at


def bind(token) -> None:
    """Bind the request's identity to its RequestToken.

    Called by JarvisCore immediately after ``InterruptManager.new_request()``.
    All subsequent TIMING lines on this thread carry the token's
    generation number. Also emits the deferred "ui_to_worker" stage,
    measured from UI enqueue to worker start.
    """
    _local.req_id = getattr(token, "generation", 0)

    queued_at = getattr(_local, "queued_at", None)
    start = getattr(_local, "start", None)
    if queued_at is not None and start is not None:
        _log("ui_to_worker", start - queued_at)
        _local.queued_at = None


def current_request_id():
    """Return the RequestToken generation bound to this thread, or None.

    Lets other structured log lines (e.g. token USAGE lines from the AI
    layer) carry the same req=N as the TIMING lines.
    """
    return getattr(_local, "req_id", None)


def end_request() -> None:
    """Log the total end-to-end duration for the current request."""
    start = getattr(_local, "start", None)
    if start is not None:
        _log("total_end_to_end", time.perf_counter() - start)


def log_since(stage_name: str, start_ts: float, **fields: str) -> None:
    """Log the time elapsed since ``start_ts`` (a perf_counter value)."""
    _log(stage_name, time.perf_counter() - start_ts, **fields)


@contextmanager
def stage(name: str, **fields: str):
    """Time the enclosed block and log its duration.

    Extra keyword fields are appended to the log line, e.g.::

        with telemetry.stage("ai_manager", provider="openai", model="gpt-4.1-mini"):
            ...

    Always logs, even if the body raises — a failing stage's duration is
    still useful diagnostic data.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        _log(name, time.perf_counter() - start, **fields)


def _log(stage_name: str, duration_seconds: float, **fields: str) -> None:
    req_id = getattr(_local, "req_id", None)
    parts = [f"req={req_id if req_id is not None else '?'}", f"stage={stage_name}"]
    parts += [f"{key}={value}" for key, value in fields.items()]
    get_logger().info(
        "TIMING | %s | %.1f ms", " | ".join(parts), duration_seconds * 1000.0
    )