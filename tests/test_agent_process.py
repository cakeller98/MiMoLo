from pathlib import Path

import pytest

from mimolo.core.agent_process import AgentProcessManager


class DummyPluginConfig:
    def __init__(self, args: list[str]) -> None:
        self.args = args
        self.executable = "python"


def test_spawn_agent_rejects_path_traversal(tmp_path) -> None:
    # Create a file outside agents to ensure exists() would be true
    agents_root = Path(__file__).resolve().parents[1] / "mimolo" / "agents"
    outside_path = (agents_root / ".." / "evil.py").resolve()
    outside_path.write_text("# test\n", encoding="utf-8")

    try:
        mgr = AgentProcessManager(config={})
        cfg = DummyPluginConfig(args=["..\\evil.py"])
        with pytest.raises(FileNotFoundError):
            mgr.spawn_agent("evil", cfg)
    finally:
        try:
            outside_path.unlink()
        except FileNotFoundError:
            pass

    # Ensure we did not accidentally create or resolve inside agents
    assert not (agents_root / "evil.py").exists()
