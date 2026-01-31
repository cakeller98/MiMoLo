import sys

import pytest

from mimolo.core.ipc import check_platform_support


def test_check_platform_support_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32", raising=False)

    class P:
        @staticmethod
        def version() -> str:
            # Build 17064 should be supported
            return "10.0.17064"

    import mimolo.core.ipc as ipc_mod

    monkeypatch.setattr(ipc_mod, "platform", P)
    supported, reason = check_platform_support()
    assert supported and "Windows 10+" in reason


def test_check_platform_support_windows_old_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32", raising=False)

    class P:
        @staticmethod
        def version() -> str:
            # Build 17062 is too old
            return "10.0.17062"

    import mimolo.core.ipc as ipc_mod

    monkeypatch.setattr(ipc_mod, "platform", P)
    supported, reason = check_platform_support()
    assert not supported and "< 17063" in reason


def test_check_platform_support_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin", raising=False)

    class P:
        @staticmethod
        def mac_ver() -> tuple[str, tuple[int, int, int], str]:
            return ("10.13.6", (0, 0, 0), "")

    import mimolo.core.ipc as ipc_mod

    monkeypatch.setattr(ipc_mod, "platform", P)
    supported, reason = check_platform_support()
    assert supported and "macOS" in reason


def test_check_platform_support_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux", raising=False)

    class P:
        @staticmethod
        def release() -> str:
            return "6.0.0"

    import mimolo.core.ipc as ipc_mod

    monkeypatch.setattr(ipc_mod, "platform", P)
    supported, reason = check_platform_support()
    assert supported and "Linux" in reason
