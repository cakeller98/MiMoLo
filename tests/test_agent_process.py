from pathlib import Path

import pytest

from mimolo.core.agent_process import AgentProcessManager


def test_resolve_agent_script_rejects_path_traversal_relative_arg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_root = tmp_path / "workspace_agents"
    installed_root = tmp_path / "installed_agents"
    workspace_root.mkdir(parents=True, exist_ok=True)
    installed_root.mkdir(parents=True, exist_ok=True)
    outside_script = tmp_path / "evil.py"
    outside_script.write_text("# test\n", encoding="utf-8")

    mgr = AgentProcessManager(config={})
    monkeypatch.setattr(
        mgr,
        "_allowed_agent_roots",
        lambda: (workspace_root, installed_root),
    )

    with pytest.raises(FileNotFoundError):
        mgr._resolve_agent_script_arg("../evil.py")


def test_resolve_agent_script_allows_installed_plugins_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "mimolo_data"
    script_path = (
        data_root
        / "operations"
        / "plugins"
        / "agents"
        / "folder_watcher"
        / "0.1.0"
        / "files"
        / "folder_watcher.py"
    )
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("# test\n", encoding="utf-8")

    monkeypatch.setattr(
        "mimolo.core.agent_process.get_mimolo_data_dir",
        lambda: data_root,
    )

    mgr = AgentProcessManager(config={})
    resolved = mgr._resolve_agent_script_arg(str(script_path))
    assert resolved == str(script_path.resolve())


def test_resolve_agent_script_rejects_absolute_path_outside_allowed_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "mimolo_data"
    outside_script = tmp_path / "outside.py"
    outside_script.write_text("# test\n", encoding="utf-8")

    monkeypatch.setattr(
        "mimolo.core.agent_process.get_mimolo_data_dir",
        lambda: data_root,
    )

    mgr = AgentProcessManager(config={})
    with pytest.raises(FileNotFoundError):
        mgr._resolve_agent_script_arg(str(outside_script))
