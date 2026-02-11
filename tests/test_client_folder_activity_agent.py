from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import typer

from mimolo.agents.client_folder_activity.client_folder_activity import (
    ClientFolderActivityAgent,
    main,
)


def _make_agent(
    watch_root: Path, *, widget_recent_rows_limit: int = 24
) -> ClientFolderActivityAgent:
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
        widget_recent_rows_limit=widget_recent_rows_limit,
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
    assert int(modified_counts.get("modified", 0)) >= 1
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


def test_take_snapshot_runs_polling_pipeline_without_explicit_accumulate(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    watch_root.mkdir(parents=True, exist_ok=True)
    target_file = watch_root / "manual_only.txt"
    target_file.write_text("alpha", encoding="utf-8")

    agent = _make_agent(watch_root)
    _, _, snapshot = agent._take_snapshot(datetime.now(UTC))
    counts = snapshot["counts"]
    assert int(counts.get("created", 0)) == 1
    assert int(counts.get("total", 0)) == 1


def test_watch_path_logs_emit_only_on_transition(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch_missing"
    agent = _make_agent(watch_root)
    emitted: list[dict[str, object]] = []

    def _capture_message(msg: dict[str, object]) -> None:
        emitted.append(msg)

    transport = cast(Any, agent)  # Any: test-only override of message transport.
    transport.send_message = _capture_message

    now = datetime.now(UTC)
    agent._accumulate(now)
    agent._accumulate(now)
    watch_root.mkdir(parents=True, exist_ok=True)
    agent._accumulate(now)
    watch_root.rmdir()
    agent._accumulate(now)

    transition_logs: list[dict[str, object]] = []
    for msg in emitted:
        if msg.get("type") != "log":
            continue
        extra = msg.get("extra")
        if not isinstance(extra, dict):
            continue
        if "watch_path" not in extra:
            continue
        transition_logs.append(msg)
    warning_logs = [msg for msg in transition_logs if msg.get("level") == "warning"]
    info_logs = [msg for msg in transition_logs if msg.get("level") == "info"]
    assert len(warning_logs) == 2
    assert len(info_logs) == 1


def test_widget_recent_rows_persist_when_no_new_changes(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    watch_root.mkdir(parents=True, exist_ok=True)
    target_file = watch_root / "persist.txt"
    agent = _make_agent(watch_root)

    # Baseline snapshot.
    agent._take_snapshot(datetime.now(UTC))

    target_file.write_text("alpha", encoding="utf-8")
    _, _, first_snapshot = agent._take_snapshot(datetime.now(UTC))
    first_rows = first_snapshot["recent_widget_rows"]
    assert len(first_rows) == 1
    assert first_rows[0]["path"] == "persist.txt"

    # No new file system changes; widget rows should stay visible.
    _, _, second_snapshot = agent._take_snapshot(datetime.now(UTC))
    second_rows = second_snapshot["recent_widget_rows"]
    assert second_rows == first_rows


def test_widget_recent_rows_newest_first_and_bounded(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    watch_root.mkdir(parents=True, exist_ok=True)
    agent = _make_agent(watch_root, widget_recent_rows_limit=3)

    agent._take_snapshot(datetime.now(UTC))

    one = watch_root / "one.txt"
    two = watch_root / "two.txt"
    three = watch_root / "three.txt"
    four = watch_root / "four.txt"

    one.write_text("1", encoding="utf-8")
    _, _, snapshot_one = agent._take_snapshot(datetime.now(UTC))
    assert [row["path"] for row in snapshot_one["recent_widget_rows"]] == ["one.txt"]

    two.write_text("2", encoding="utf-8")
    _, _, snapshot_two = agent._take_snapshot(datetime.now(UTC))
    assert [row["path"] for row in snapshot_two["recent_widget_rows"]][:2] == [
        "two.txt",
        "one.txt",
    ]

    three.write_text("3", encoding="utf-8")
    _, _, snapshot_three = agent._take_snapshot(datetime.now(UTC))
    assert [row["path"] for row in snapshot_three["recent_widget_rows"]][:3] == [
        "three.txt",
        "two.txt",
        "one.txt",
    ]

    four.write_text("4", encoding="utf-8")
    _, _, snapshot_four = agent._take_snapshot(datetime.now(UTC))
    assert [row["path"] for row in snapshot_four["recent_widget_rows"]] == [
        "four.txt",
        "three.txt",
        "two.txt",
    ]
