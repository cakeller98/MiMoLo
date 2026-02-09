from __future__ import annotations

from pathlib import Path

from mimolo.agents.screen_tracker.screen_tracker import (
    ScreenTrackerAgent,
    WindowLookupResult,
    compute_thumbnail_size,
    normalize_capture_mode,
    normalize_image_format,
    parse_window_lookup_output,
)


def _make_agent(tmp_path: Path) -> ScreenTrackerAgent:
    return ScreenTrackerAgent(
        agent_id="screen_tracker-test-001",
        agent_label="screen_tracker_test",
        capture_interval_s=5.0,
        heartbeat_interval=15.0,
        mode="app_window",
        target_app="Plasticity",
        target_window_title_contains="Model",
        image_format="jpg",
        jpeg_quality=60,
        scale=0.25,
        letterbox=False,
        capture_max_dimension_px=1920,
        thumbnail_width_px=640,
        thumbnail_height_px=360,
        max_summary_captures=20,
    )


def test_normalize_capture_mode_alias_and_default() -> None:
    assert normalize_capture_mode("active_window") == "app_window"
    assert normalize_capture_mode("app_window") == "app_window"
    assert normalize_capture_mode("full_screen") == "full_screen"
    assert normalize_capture_mode("unknown") == "full_screen"


def test_normalize_image_format_alias_and_default() -> None:
    assert normalize_image_format("jpeg") == "jpg"
    assert normalize_image_format("jpg") == "jpg"
    assert normalize_image_format("png") == "png"
    assert normalize_image_format("gif") == "jpg"


def test_compute_thumbnail_size_preserves_aspect() -> None:
    out_w, out_h = compute_thumbnail_size(2000, 1000, 640, 360)
    assert out_w == 640
    assert out_h == 320


def test_parse_window_lookup_output_variants() -> None:
    assert parse_window_lookup_output("WINDOW_ID:123").window_id == 123
    assert parse_window_lookup_output("APP_NOT_OPEN").reason == "app_not_open"
    assert parse_window_lookup_output("WINDOW_NOT_OPEN").reason == "window_not_open"
    assert parse_window_lookup_output("WINDOW_NOT_FOUND").reason == "window_not_found"
    assert parse_window_lookup_output("").reason == "window_not_found"


def test_write_placeholder_svg_contains_not_open_message(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MIMOLO_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path)
    out_path = tmp_path / "placeholder.svg"
    agent._write_placeholder_svg(out_path, "Plasticity not open")
    text = out_path.read_text(encoding="utf-8")
    assert "<svg" in text
    assert "Plasticity not open" in text
    assert 'width="640"' in text
    assert 'height="360"' in text


def test_build_placeholder_message_for_not_open(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MIMOLO_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path)
    assert agent._build_placeholder_message("app_not_open") == "Plasticity not open"
    assert agent._build_placeholder_message("window_not_open") == "Plasticity not open"
    assert agent._build_placeholder_message("lookup_error") == "Plasticity inaccessible"


def test_parse_window_lookup_output_invalid_window_id() -> None:
    result: WindowLookupResult = parse_window_lookup_output("WINDOW_ID:not_a_number")
    assert result.window_id is None
    assert result.reason == "window_not_found"
    assert result.detail == "invalid_window_id"
