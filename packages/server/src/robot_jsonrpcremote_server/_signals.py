"""Patch Robot Framework's signal handling so the embedded runner shuts down cleanly.

While a suite runs on the main thread, Robot installs its own SIGINT/SIGTERM handlers
(`robot.running.signalhandler._StopSignalMonitor`). On a signal the default handler
writes "Second signal will force exit." to stderr and aborts execution with
``ExecutionFailed(exit=True)``. Since this server runs Robot as a long-lived hook loop
(a single never-returning keyword), that produces noisy output and an aborted run.

We replace the monitor's ``__call__`` so an incoming signal instead quietly triggers a
registered, graceful stop callback (``RobotRemoteContext.stop``). The hook loop then ends
normally, the suite completes, and the process exits with code 0 -- no stderr noise.

This mirrors the approach used in robotcode's REPL interpreter. The patch is process-wide,
which is fine because the server process only ever runs this single internal REPL suite.
"""

from typing import Any, Callable, Optional

from robot.running.signalhandler import _StopSignalMonitor

_stop_callback: Optional[Callable[[], None]] = None
_patched = False


def _patched_call(self: Any, signum: Any, frame: Any) -> None:
    # Quietly trigger a graceful stop instead of Robot's noisy force-exit behaviour.
    if _stop_callback is not None:
        _stop_callback()


def patch_robot_signal_handling(stop_callback: Callable[[], None]) -> None:
    """Register the graceful stop callback and patch Robot's signal monitor (idempotent)."""
    global _stop_callback, _patched
    _stop_callback = stop_callback
    if not _patched:
        _StopSignalMonitor.__call__ = _patched_call
        _patched = True
