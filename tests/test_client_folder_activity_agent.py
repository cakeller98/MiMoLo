from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import typer

from mimolo.agents.client_folder_activity.client_folder_activity import (
    ClientFolderActivityAgent,
    main,
)


def _make_agent(watch_root: Path) -> ClientFolderActivityAgent:
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
        sample_interval=0.5,
        heartbeat_interval=10.0,
        emit_path_samples_limit=50,
    )


def test_main_requires_absolute_watch_paths() -> None:
    with pytest.raises(typer.BadParameter, match="--watch-path must be absolute"):
        main(watch_paths=["relative/path"])


def test_main_requires_non_empty_watch_paths() -> None:
    with pytest.raises(typer.BadParameter, match="at least one --watch-path is required"):
        main(watch_paths=[])


def test_summary_reports_created_and_modified_paths(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    watch_root.mkdir(parents=True, exist_ok=True)
    target_file = watch_root / "example.txt"
    agent = _make_agent(watch_root)

    # Baseline scan establishes initial empty snapshot.
    agent._accumulate(datetime.now(UTC))
    agent._take_snapshot(datetime.now(UTC))

    # New file appears -> created.
    target_file.write_text("alpha", encoding="utf-8")
    agent._accumulate(datetime.now(UTC))
    _, _, created_snapshot = agent._take_snapshot(datetime.now(UTC))
    created_counts = created_snapshot["counts"]
    assert int(created_counts.get("created", 0)) == 1
    assert int(created_counts.get("modified", 0)) == 0
    created_paths = created_snapshot["created_paths"]
    assert len(created_paths) == 1
    assert created_paths[0]["path"] == "example.txt"
    assert created_paths[0]["size"] == 5

    # Existing file changes -> modified.
    target_file.write_text("alpha-beta", encoding="utf-8")
    agent._accumulate(datetime.now(UTC))
    _, _, modified_snapshot = agent._take_snapshot(datetime.now(UTC))
    modified_counts = modified_snapshot["counts"]
    assert int(modified_counts.get("created", 0)) == 0
    assert int(modified_counts.get("modified", 0)) == 1
    modified_paths = modified_snapshot["modified_paths"]
    assert len(modified_paths) == 1
    assert modified_paths[0]["path"] == "example.txt"
    assert modified_paths[0]["size"] == 10


def test_summary_schema_version_and_path_lists(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    watch_root.mkdir(parents=True, exist_ok=True)
    target_file = watch_root / "artifact.log"
    target_file.write_text("x", encoding="utf-8")
    agent = _make_agent(watch_root)
    agent._accumulate(datetime.now(UTC))
    start, end, snapshot = agent._take_snapshot(datetime.now(UTC))
    summary = agent._format_summary(snapshot, start, end)
    assert summary["schema"] == "client_folder_activity.summary.v2"
    assert "created_paths" in summary
    assert "modified_paths" in summary
    assert isinstance(summary["created_paths"], list)
    assert isinstance(summary["modified_paths"], list)
