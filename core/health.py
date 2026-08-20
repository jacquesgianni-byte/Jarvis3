"""
Health check utility.

Exposes a minimal, side-effect-free health indicator. The health() function
returns a constant payload {"status": "ok"} intended for service liveness and
readiness probes, monitoring checks, and load balancer health tests. It performs
no I/O or external calls to remain fast and reliable.
"""

def health():
    """Return a simple health status payload."""
    return {"status": "ok"}
