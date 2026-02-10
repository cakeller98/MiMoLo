from __future__ import annotations

import signal
from collections.abc import Callable
from types import FrameType

from mimolo.cli import _install_graceful_sigterm_handler
from mimolo.core.config import Config
from mimolo.core.runtime import Runtime


def test_install_graceful_sigterm_handler_requests_runtime_stop(
    monkeypatch,
) -> None:
    runtime = Runtime(Config())
    runtime._running = True

    registered: dict[int, Callable[[int, FrameType | None], None]] = {}

    def _capture_signal(
        sig: int, handler: Callable[[int, FrameType | None], None]
    ) -> None:
        registered[sig] = handler

    monkeypatch.setattr(signal, "signal", _capture_signal)

    _install_graceful_sigterm_handler(runtime)

    assert signal.SIGTERM in registered
    handler = registered[signal.SIGTERM]
    handler(signal.SIGTERM, None)
    assert runtime._running is False
