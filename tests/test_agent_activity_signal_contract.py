from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mimolo.agents.base_agent import BaseAgent
from mimolo.agents.client_folder_activity.client_folder_activity import (
    ClientFolderActivityAgent,
)


class _PassiveAgent(BaseAgent):
    def _accumulate(self, now: datetime) -> None:
        return

    def _take_snapshot(self, now: datetime) -> tuple[datetime, datetime, Any]:
        return now, now, {}

    def _format_summary(
        self, snapshot: Any, start: datetime, end: datetime
    ) -> dict[str, Any]:
        return {"schema": "test.summary.v1"}


def _make_folder_agent(watch_root: Path) -> ClientFolderActivityAgent:
    return ClientFolderActivityAgent(
        agent_id="client_folder_activity-test-001",
        agent_label="client_folder_activity_test",
        client_id="test-client",
        client_name="Test Client",
        watch_paths=[str(watch_root)],
        include_globs=["**/*"],
        exclude_globs=[],
        follow_symlinks=False,
        coalesce_window_s=2.0,
        capture_window_s=300.0,
        reemit_cooldown_s=0.0,
        watchfiles_debounce_ms=1000,
        sample_interval=0.5,
        heartbeat_interval=10.0,
        emit_path_samples_limit=50,
        use_watchfiles=False,
    )


def test_base_agent_injects_passive_activity_signal() -> None:
    agent = _PassiveAgent(
        agent_id="test-001",
        agent_label="test-passive",
        sample_interval=1.0,
        heartbeat_interval=5.0,
        protocol_version="0.3",
        agent_version="0.1.0",
        min_app_version="0.3.0",
    )
    emitted: list[dict[str, Any]] = []
    object.__setattr__(agent, "send_message", emitted.append)

    now = datetime.now(UTC)
    agent._emit_summary(now, now, {})

    assert len(emitted) == 1
    msg = emitted[0]
    assert msg["type"] == "summary"
    summary = msg["data"]
    assert summary["activity_signal"]["mode"] == "passive"
    assert summary["activity_signal"]["keep_alive"] is None
    assert summary["activity_signal"]["reason"] is None


def test_client_folder_activity_signal_emits_keep_alive_on_changes(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    watch_root.mkdir(parents=True, exist_ok=True)
    target_file = watch_root / "example.txt"
    agent = _make_folder_agent(watch_root)

    # Establish baseline state.
    agent._accumulate(datetime.now(UTC))
    agent._take_snapshot(datetime.now(UTC))

    # Create one new file to produce activity.
    target_file.write_text("alpha", encoding="utf-8")
    agent._accumulate(datetime.now(UTC))
    start, end, changed_snapshot = agent._take_snapshot(datetime.now(UTC))
    changed_signal = agent._activity_signal(changed_snapshot, start, end)
    assert changed_signal["mode"] == "active"
    assert changed_signal["keep_alive"] is True

    emitted: list[dict[str, Any]] = []
    object.__setattr__(agent, "send_message", emitted.append)
    agent._emit_summary(start, end, changed_snapshot)
    changed_summary_signal = emitted[-1]["data"]["activity_signal"]
    assert changed_summary_signal["mode"] == "active"
    assert changed_summary_signal["keep_alive"] is True

    # Next immediate snapshot should be no-change and emit keep_alive false.
    no_change_start, no_change_end, no_change_snapshot = agent._take_snapshot(datetime.now(UTC))
    no_change_signal = agent._activity_signal(
        no_change_snapshot, no_change_start, no_change_end
    )
    assert no_change_signal["mode"] == "active"
    assert no_change_signal["keep_alive"] is False
    agent._emit_summary(no_change_start, no_change_end, no_change_snapshot)
    no_change_summary_signal = emitted[-1]["data"]["activity_signal"]
    assert no_change_summary_signal["mode"] == "active"
    assert no_change_summary_signal["keep_alive"] is False
