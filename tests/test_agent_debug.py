from __future__ import annotations

from types import SimpleNamespace

from pytest import MonkeyPatch

from mimolo.core import agent_debug


def test_open_tail_window_uses_argument_list(monkeypatch: MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_popen(
        args: list[str], *unused_args: object, **unused_kwargs: object
    ) -> object:
        calls.append(args)
        if len(calls) == 1:
            raise FileNotFoundError("xterm not found")
        return object()

    # Monkeypatch to avoid spawning real terminals/subprocesses in tests.
    monkeypatch.setattr(
        agent_debug, "subprocess", SimpleNamespace(Popen=fake_popen), raising=True
    )
    monkeypatch.setattr(agent_debug, "os", SimpleNamespace(name="posix"), raising=True)
    monkeypatch.setattr(agent_debug, "sys", SimpleNamespace(platform="linux"), raising=True)

    agent_debug.open_tail_window("/tmp/evil;rm -rf /.log")

    assert calls
    for args in calls:
        assert isinstance(args, list)
        assert args[0] in {"xterm", "gnome-terminal"}
        assert "sh" not in args
