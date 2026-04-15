from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from mimolo.analyst.day_blip_chart import (
    BLOCK_FUTURE,
    BLOCK_FULL,
    BLOCK_LEFT,
    BLOCK_RIGHT,
    CHUNKS_PER_DAY,
    DEFAULT_EXCLUDED_LABELS,
    DayActivityRecord,
    build_day_blip_chart,
    build_label_aliases,
    clean_record_labels,
    format_chart_panel,
    is_lifecycle_event,
    is_meaningful_record,
    next_quarter_hour_bucket,
    normalize_label_filter,
    render_bins,
)


def _record(
    *,
    local_dt: datetime,
    label: str,
    event: str,
    keep_alive: bool | None,
) -> DayActivityRecord:
    return DayActivityRecord(
        timestamp=local_dt.astimezone(UTC),
        local_timestamp=local_dt,
        label=label,
        event=event,
        keep_alive=keep_alive,
    )


def test_render_bins_uses_half_blocks_per_quarter_hour_pair() -> None:
    bins = [False] * CHUNKS_PER_DAY
    bins[0] = True
    bins[3] = True
    bins[4] = True
    bins[5] = True

    rendered = render_bins(bins)

    assert rendered.startswith(BLOCK_LEFT + BLOCK_RIGHT + BLOCK_FULL)
    assert len(rendered) == 48


def test_is_meaningful_record_uses_keep_alive_or_lifecycle() -> None:
    local_dt = datetime(2026, 4, 14, 9, 0, tzinfo=timezone(timedelta(hours=-7)))

    assert is_lifecycle_event("creo_trail_session_close")
    assert is_meaningful_record(
        _record(
            local_dt=local_dt,
            label="Creo Tracker",
            event="creo_trail_session_close",
            keep_alive=False,
        )
    )
    assert not is_meaningful_record(
        _record(
            local_dt=local_dt,
            label="Watch Belker",
            event="summary",
            keep_alive=False,
        )
    )
    assert is_meaningful_record(
        _record(
            local_dt=local_dt,
            label="Watch Belker",
            event="summary",
            keep_alive=True,
        )
    )


def test_build_day_blip_chart_summary_is_or_of_visible_agent_rows() -> None:
    tz = timezone(timedelta(hours=-7))
    target_date = date(2026, 4, 14)
    records = [
        _record(
            local_dt=datetime(2026, 4, 14, 8, 5, tzinfo=tz),
            label="Watch Belker",
            event="summary",
            keep_alive=False,
        ),
        _record(
            local_dt=datetime(2026, 4, 14, 8, 20, tzinfo=tz),
            label="Watch Belker",
            event="summary",
            keep_alive=True,
        ),
        _record(
            local_dt=datetime(2026, 4, 14, 9, 40, tzinfo=tz),
            label="Creo Tracker",
            event="creo_trail_session_close",
            keep_alive=False,
        ),
    ]

    chart = build_day_blip_chart(
        records,
        target_date,
        tz,
        now_reference=datetime(2026, 4, 14, 9, 1, tzinfo=tz),
    )

    agent_lines = dict(chart.agent_lines)
    assert "Watch Belker" in agent_lines
    assert "Creo Tracker" in agent_lines
    assert agent_lines["Watch Belker"][16] == BLOCK_RIGHT
    assert agent_lines["Creo Tracker"][19] == BLOCK_LEFT
    assert chart.all_activity_line[16] == BLOCK_RIGHT
    assert chart.all_activity_line[19] == BLOCK_LEFT


def test_clean_record_labels_applies_default_alias_and_excludes() -> None:
    tz = timezone(timedelta(hours=-7))
    records = [
        _record(
            local_dt=datetime(2026, 4, 14, 8, 20, tzinfo=tz),
            label="Watch Belker Dropbox Bedrock",
            event="summary",
            keep_alive=True,
        ),
        _record(
            local_dt=datetime(2026, 4, 14, 8, 35, tzinfo=tz),
            label="Watch Belker Dropbox",
            event="summary",
            keep_alive=True,
        ),
        _record(
            local_dt=datetime(2026, 4, 14, 9, 10, tzinfo=tz),
            label="agent_template",
            event="summary",
            keep_alive=True,
        ),
        _record(
            local_dt=datetime(2026, 4, 14, 9, 25, tzinfo=tz),
            label="Screen Shotter",
            event="summary",
            keep_alive=True,
        ),
    ]

    cleaned = list(
        clean_record_labels(
            records,
            aliases=build_label_aliases([]),
            excluded_labels=set(DEFAULT_EXCLUDED_LABELS),
            included_labels=normalize_label_filter([]),
        )
    )

    assert [record.label for record in cleaned] == [
        "Watch Belker Dropbox",
        "Watch Belker Dropbox",
    ]


def test_next_quarter_hour_bucket_rounds_up_within_current_day() -> None:
    tz = timezone(timedelta(hours=-7))
    local_now = datetime(2026, 4, 14, 18, 26, 30, tzinfo=tz)

    assert next_quarter_hour_bucket(local_now) == 74


def test_current_day_chart_marks_future_range_on_all_non_time_rows() -> None:
    tz = timezone(timedelta(hours=-7))
    target_date = date(2026, 4, 14)
    records = [
        _record(
            local_dt=datetime(2026, 4, 14, 8, 20, tzinfo=tz),
            label="Watch Belker",
            event="summary",
            keep_alive=True,
        ),
    ]

    chart = build_day_blip_chart(
        records,
        target_date,
        tz,
        now_reference=datetime(2026, 4, 14, 18, 26, 30, tzinfo=tz),
    )
    panel = format_chart_panel(chart)
    lines = panel.renderable.splitlines()
    now_char_index = next_quarter_hour_bucket(datetime(2026, 4, 14, 18, 26, 30, tzinfo=tz)) // 2

    assert "time" in lines[0]
    assert BLOCK_FUTURE not in lines[0]
    assert BLOCK_FUTURE not in chart.all_activity_line[now_char_index]
    assert chart.future_fill_start == now_char_index + 1
    assert "now" not in panel.renderable
    assert any(BLOCK_FUTURE in line for line in lines[1:])
