"""Widget-related helpers for Runtime."""

from __future__ import annotations

import base64
import html
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mimolo.common.paths import get_mimolo_data_dir

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


def _widget_unknown_instance_response(
    mode: str, request_id: str | None, *, reason: str = "unknown instance"
) -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "unknown_instance",
        "request_id": request_id,
        "render": {
            "mode": mode,
            "html": f'<div class="widget-muted">{html.escape(reason)}</div>',
            "ttl_ms": 1000,
            "state_token": None,
            "warnings": ["unknown_instance"],
        },
    }


def _widget_unknown_instance_manifest() -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "unknown_instance",
        "widget": {
            "supports_render": False,
            "default_aspect_ratio": "16:9",
            "min_refresh_ms": 1000,
            "supported_actions": [],
            "content_modes": ["html_fragment_v1"],
        },
    }


def _widget_ttl_ms(runtime: Runtime, instance_id: str) -> int:
    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None:
        return 1000
    return max(1000, int(round(runtime._effective_heartbeat_interval_s(plugin_cfg) * 1000)))


def _escape_text(value: object) -> str:
    return html.escape("-" if value is None else str(value))


def _safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _format_seconds(value: object) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:.1f}s"


def _find_cli_option(
    args: list[str], names: tuple[str, ...], default: float
) -> float:
    for idx, arg in enumerate(args):
        for name in names:
            if arg == name and idx + 1 < len(args):
                parsed = _safe_float(args[idx + 1])
                if parsed is not None:
                    return parsed
            if arg.startswith(name + "="):
                parsed = _safe_float(arg.split("=", 1)[1])
                if parsed is not None:
                    return parsed
    return default


def _extract_trail_tracker_intervals(runtime: Runtime, instance_id: str) -> tuple[float, float]:
    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None:
        return 30.0, 300.0
    args = list(plugin_cfg.args)
    poll_interval_s = _find_cli_option(
        args,
        ("--poll-interval-s", "--poll-interval"),
        30.0,
    )
    active_window_s = _find_cli_option(
        args,
        ("--active-window-s", "--active-window"),
        300.0,
    )
    return max(1.0, poll_interval_s), max(1.0, active_window_s)


def _render_status_badge(label: str, background: str, border: str, text_color: str) -> str:
    safe_label = html.escape(label)
    return (
        '<span style="display:inline-flex;align-items:center;gap:6px;'
        f'padding:2px 8px;border-radius:999px;background:{background};'
        f'border:1px solid {border};color:{text_color};font-size:10px;font-weight:700;">'
        f"{safe_label}</span>"
    )


def _render_key_value_row(label: str, value: object) -> str:
    safe_label = html.escape(label)
    safe_value = _escape_text(value)
    return (
        '<div style="display:grid;grid-template-columns:auto 1fr;gap:8px;align-items:center;">'
        f'<span style="font-size:10px;color:#8f9db2;">{safe_label}</span>'
        f'<span style="font-size:10px;color:#c6d0de;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{safe_value}</span>'
        "</div>"
    )


def _widget_agent_liveness(
    runtime: Runtime, instance_id: str
) -> tuple[bool, bool, datetime | None]:
    handle = runtime.agent_manager.agents.get(instance_id)
    if handle is None:
        return False, False, None
    last_heartbeat = handle.last_heartbeat
    if not handle.is_alive():
        return False, False, last_heartbeat
    if last_heartbeat is None:
        return True, False, None
    heartbeat_age_s = max(0.0, (datetime.now(UTC) - last_heartbeat).total_seconds())
    heartbeat_timeout_s = max(1.0, float(runtime.config.monitor.agent_heartbeat_timeout_s))
    return True, heartbeat_age_s <= heartbeat_timeout_s, last_heartbeat


def resolve_screen_tracker_thumbnail(
    runtime: Runtime, instance_id: str
) -> tuple[Path | None, str | None]:
    """Return latest screen-tracker thumbnail path if available."""
    data_root_raw = os.getenv("MIMOLO_DATA_DIR")
    data_root = Path(data_root_raw) if data_root_raw else get_mimolo_data_dir()
    base_root = (data_root / "agents" / "screen_tracker" / instance_id).resolve()
    thumb_root = (base_root / "artifacts" / "thumb").resolve()

    try:
        thumb_root.relative_to(base_root)
    except ValueError:
        return None, "invalid_thumbnail_root"
    if not thumb_root.exists():
        return None, "thumbnail_root_missing"

    candidates = [
        p
        for p in thumb_root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".svg"}
    ]
    if not candidates:
        return None, "no_thumbnail_artifacts"
    latest = max(candidates, key=lambda p: p.stat().st_mtime_ns)
    return latest, None


def screen_tracker_thumbnail_data_uri(
    runtime: Runtime, thumbnail_path: Path
) -> tuple[str | None, str | None]:
    """Encode one thumbnail artifact as data URI for renderer-safe embedding."""
    _ = runtime
    suffix = thumbnail_path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif suffix == ".png":
        mime = "image/png"
    elif suffix == ".svg":
        mime = "image/svg+xml"
    else:
        return None, "unsupported_thumbnail_format"

    try:
        raw_bytes = thumbnail_path.read_bytes()
    except OSError:
        return None, "thumbnail_read_failed"
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}", None


def build_screen_tracker_widget_manifest(
    runtime: Runtime, instance_id: str
) -> dict[str, Any]:
    """Build widget manifest for screen_tracker."""
    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None:
        return _widget_unknown_instance_manifest()
    min_refresh_ms = _widget_ttl_ms(runtime, instance_id)
    return {
        "accepted": True,
        "status": "ok",
        "widget": {
            "supports_render": True,
            "default_aspect_ratio": "16:9",
            "min_refresh_ms": min_refresh_ms,
            "supported_actions": ["refresh"],
            "content_modes": ["html_fragment_v1"],
        },
    }


def build_screen_tracker_widget_render(
    runtime: Runtime, instance_id: str, request_id: str | None, mode: str
) -> dict[str, Any]:
    """Build widget render payload for screen_tracker."""
    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None:
        return _widget_unknown_instance_response(mode, request_id)

    latest_path, missing_reason = resolve_screen_tracker_thumbnail(runtime, instance_id)
    ttl_ms = _widget_ttl_ms(runtime, instance_id)

    if latest_path is None:
        reason_text = html.escape(missing_reason or "no_thumbnail_artifacts")
        return {
            "accepted": True,
            "status": "ok",
            "request_id": request_id,
            "render": {
                "mode": mode,
                "html": (
                    '<div class="widget-muted">'
                    f"screen tracker waiting for captures ({reason_text})"
                    "</div>"
                ),
                "ttl_ms": ttl_ms,
                "state_token": None,
                "warnings": [missing_reason or "no_thumbnail_artifacts"],
            },
        }

    stat_result = latest_path.stat()
    data_uri, uri_error = screen_tracker_thumbnail_data_uri(runtime, latest_path)
    if data_uri is None:
        reason_text = html.escape(uri_error or "thumbnail_read_failed")
        return {
            "accepted": True,
            "status": "ok",
            "request_id": request_id,
            "render": {
                "mode": mode,
                "html": (
                    '<div class="widget-muted">'
                    f"screen tracker thumbnail unavailable ({reason_text})"
                    "</div>"
                ),
                "ttl_ms": ttl_ms,
                "state_token": None,
                "warnings": [uri_error or "thumbnail_read_failed"],
            },
        }
    safe_uri = html.escape(data_uri, quote=True)
    safe_file = html.escape(latest_path.name)
    captured_at = datetime.fromtimestamp(stat_result.st_mtime, UTC).isoformat()
    safe_time = html.escape(captured_at)
    state_token = f"{latest_path.name}:{stat_result.st_mtime_ns}"

    html_fragment = (
        '<div class="screen-widget-root">'
        f'<img class="screen-widget-image" src="{safe_uri}" alt="Latest screen snapshot"/>'
        '<div class="screen-widget-meta">'
        f'<span class="screen-widget-file">{safe_file}</span>'
        f'<time class="screen-widget-time" datetime="{safe_time}">{safe_time}</time>'
        "</div>"
        "</div>"
    )

    return {
        "accepted": True,
        "status": "ok",
        "request_id": request_id,
        "render": {
            "mode": mode,
            "html": html_fragment,
            "ttl_ms": ttl_ms,
            "state_token": state_token,
            "warnings": [],
        },
    }


def build_client_folder_widget_manifest(
    runtime: Runtime, instance_id: str
) -> dict[str, Any]:
    """Build widget manifest for client_folder_activity."""
    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None:
        return _widget_unknown_instance_manifest()

    min_refresh_ms = _widget_ttl_ms(runtime, instance_id)
    return {
        "accepted": True,
        "status": "ok",
        "widget": {
            "supports_render": True,
            "default_aspect_ratio": "16:9",
            "min_refresh_ms": min_refresh_ms,
            "supported_actions": ["refresh"],
            "content_modes": ["html_fragment_v1"],
        },
    }


def _escape_or_dash(value: object) -> str:
    if value is None:
        return "-"
    return html.escape(str(value))


def _format_epoch_ns_as_iso(mtime_ns_raw: object) -> str:
    if not isinstance(mtime_ns_raw, int):
        return "-"
    if mtime_ns_raw <= 0:
        return "-"
    seconds = mtime_ns_raw / 1_000_000_000
    # Keep conversion deterministic and platform-independent.
    if seconds > 253402300799:
        return "-"
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return (epoch + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _folder_css_for_event(event_name_raw: object) -> str:
    event_name = str(event_name_raw).lower()
    if event_name == "deleted":
        return "folder-row folder-row-deleted"
    if event_name == "created":
        return "folder-row folder-row-created"
    return "folder-row folder-row-modified"


def _collect_folder_rows_from_recent(summary: dict[str, Any]) -> list[dict[str, str]]:
    recent_rows = summary.get("recent_widget_rows", [])
    if not isinstance(recent_rows, list):
        return []

    rows: list[dict[str, str]] = []
    for item in recent_rows:
        if not isinstance(item, dict):
            continue
        mtime_iso_raw = item.get("mtime_iso")
        if isinstance(mtime_iso_raw, str) and mtime_iso_raw:
            time_value = mtime_iso_raw
        else:
            time_value = _format_epoch_ns_as_iso(item.get("mtime_ns"))
        rows.append(
            {
                "css": _folder_css_for_event(item.get("event")),
                "path": _escape_or_dash(item.get("path")),
                "size": _escape_or_dash(item.get("size")),
                "time": _escape_or_dash(time_value),
            }
        )
    return rows


def _collect_folder_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
    recent_rows = _collect_folder_rows_from_recent(summary)
    if recent_rows:
        return recent_rows

    rows: list[dict[str, str]] = []
    for kind, css in (
        ("deleted_paths", "folder-row folder-row-deleted"),
        ("created_paths", "folder-row folder-row-created"),
        ("modified_paths", "folder-row folder-row-modified"),
    ):
        items = summary.get(kind, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "css": css,
                    "path": _escape_or_dash(item.get("path")),
                    "size": _escape_or_dash(item.get("size")),
                    "time": _format_epoch_ns_as_iso(item.get("mtime_ns")),
                }
            )
    return rows


def build_client_folder_widget_render(
    runtime: Runtime, instance_id: str, request_id: str | None, mode: str
) -> dict[str, Any]:
    """Build widget render payload for client_folder_activity."""
    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None:
        return _widget_unknown_instance_response(mode, request_id)

    ttl_ms = _widget_ttl_ms(runtime, instance_id)
    live_status = runtime.agent_last_status.get(instance_id)
    summary = live_status if isinstance(live_status, dict) else runtime.agent_last_summary.get(instance_id)
    if not isinstance(summary, dict):
        return {
            "accepted": True,
            "status": "ok",
            "request_id": request_id,
            "render": {
                "mode": mode,
                "html": (
                    '<div class="widget-muted">'
                    "folder watcher waiting for summary data"
                    "</div>"
                ),
                "ttl_ms": ttl_ms,
                "state_token": None,
                "warnings": ["no_summary_yet"],
            },
        }

    rows = _collect_folder_rows(summary)

    counts = summary.get("counts", {})
    created_count = 0
    modified_count = 0
    deleted_count = 0
    total_count = 0
    if isinstance(counts, dict):
        created_count = int(counts.get("created", 0) or 0)
        modified_count = int(counts.get("modified", 0) or 0)
        deleted_count = int(counts.get("deleted", 0) or 0)
        total_count = int(counts.get("total", 0) or 0)

    if rows:
        row_html = "".join(
            (
                f'<li class="{row["css"]}">'
                f'<span class="folder-col folder-path">{row["path"]}</span>'
                f'<span class="folder-col folder-size">{row["size"]}</span>'
                f'<time class="folder-col folder-time">{row["time"]}</time>'
                "</li>"
            )
            for row in rows
        )
    else:
        row_html = (
            '<li class="folder-row folder-row-empty">'
            '<span class="folder-col folder-path">No file deltas in current window</span>'
            '<span class="folder-col folder-size">-</span>'
            '<span class="folder-col folder-time">-</span>'
            "</li>"
        )

    state_token = summary.get("window", {})
    if isinstance(state_token, dict):
        token_value = str(state_token.get("end", ""))
    else:
        token_value = ""
    if not token_value:
        token_value = datetime.now(UTC).isoformat(timespec="seconds")

    html_fragment = (
        '<div class="folder-widget-root">'
        '<div class="folder-widget-summary">'
        f'<span class="folder-count">created {created_count}</span>'
        f'<span class="folder-count">modified {modified_count}</span>'
        f'<span class="folder-count">deleted {deleted_count}</span>'
        f'<span class="folder-count">total {total_count}</span>'
        "</div>"
        '<ul class="folder-widget-list">'
        f"{row_html}"
        "</ul>"
        "</div>"
    )
    return {
        "accepted": True,
        "status": "ok",
        "request_id": request_id,
        "render": {
            "mode": mode,
            "html": html_fragment,
            "ttl_ms": ttl_ms,
            "state_token": token_value,
            "warnings": [],
        },
    }


def build_generic_agent_widget_manifest(
    runtime: Runtime, instance_id: str
) -> dict[str, Any]:
    """Build a minimal supported widget manifest for generic agents."""
    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None:
        return _widget_unknown_instance_manifest()

    return {
        "accepted": True,
        "status": "ok",
        "widget": {
            "supports_render": True,
            "default_aspect_ratio": "16:9",
            "min_refresh_ms": _widget_ttl_ms(runtime, instance_id),
            "supported_actions": ["refresh"],
            "content_modes": ["html_fragment_v1"],
        },
    }


def build_generic_agent_widget_render(
    runtime: Runtime, instance_id: str, request_id: str | None, mode: str
) -> dict[str, Any]:
    """Build a lightweight fallback widget for any agent instance."""
    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None:
        return _widget_unknown_instance_response(mode, request_id)

    process_alive, heartbeat_fresh, last_heartbeat = _widget_agent_liveness(runtime, instance_id)
    heartbeat_at = last_heartbeat.isoformat() if last_heartbeat else "-"
    summary = runtime.agent_last_summary.get(instance_id)
    state = runtime._agent_states.get(instance_id, "inactive")
    detail = runtime._agent_state_details.get(instance_id, "configured")
    summary_event = "-"
    summary_keys = 0
    warnings: list[str] = []
    if isinstance(summary, dict):
        summary_event = str(summary.get("event") or summary.get("summary_event") or "summary")
        summary_keys = len(summary)
    else:
        warnings.append("no_summary_yet")

    if process_alive and heartbeat_fresh:
        badge = _render_status_badge("reporting", "#17351f", "#2d6a3f", "#98f0b2")
        status_reason = "Process is alive and heartbeats are current."
    elif process_alive:
        badge = _render_status_badge("heartbeat stale", "#3a3214", "#8c7531", "#f5d98a")
        status_reason = "Process is alive, but heartbeat freshness is not current."
        warnings.append("heartbeat_stale")
    elif state == "shutting-down":
        badge = _render_status_badge("shutting down", "#3a3214", "#8c7531", "#f5d98a")
        status_reason = "Shutdown is in progress."
    elif state == "error":
        badge = _render_status_badge("error", "#3a181b", "#8c4549", "#ffb0b7")
        status_reason = "Runtime recorded an agent error state."
    else:
        badge = _render_status_badge("not running", "#24181a", "#5e3c40", "#d8a7ad")
        status_reason = "No live managed process is currently attached."

    html_fragment = (
        '<div style="display:grid;gap:8px;">'
        f"{badge}"
        f'<div style="font-size:10px;color:#8f9db2;">{html.escape(status_reason)}</div>'
        '<div style="display:grid;gap:4px;">'
        f"{_render_key_value_row('state detail', detail)}"
        f"{_render_key_value_row('process alive', 'yes' if process_alive else 'no')}"
        f"{_render_key_value_row('last heartbeat', heartbeat_at)}"
        f"{_render_key_value_row('last summary event', summary_event)}"
        f"{_render_key_value_row('summary fields', summary_keys)}"
        "</div>"
        "</div>"
    )

    state_token = (
        f"{state}:{detail}:{process_alive}:{heartbeat_fresh}:{heartbeat_at}:"
        f"{summary_event}:{summary_keys}"
    )
    return {
        "accepted": True,
        "status": "ok",
        "request_id": request_id,
        "render": {
            "mode": mode,
            "html": html_fragment,
            "ttl_ms": _widget_ttl_ms(runtime, instance_id),
            "state_token": state_token,
            "warnings": warnings,
        },
    }


def build_trail_tracker_widget_manifest(
    runtime: Runtime, instance_id: str
) -> dict[str, Any]:
    """Build widget manifest for trail_tracker."""
    return build_generic_agent_widget_manifest(runtime, instance_id)


def build_trail_tracker_widget_render(
    runtime: Runtime, instance_id: str, request_id: str | None, mode: str
) -> dict[str, Any]:
    """Build trail tracker widget payload with active/cooling/inactive state."""
    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None:
        return _widget_unknown_instance_response(mode, request_id)

    ttl_ms = _widget_ttl_ms(runtime, instance_id)
    poll_interval_s, active_window_s = _extract_trail_tracker_intervals(runtime, instance_id)
    summary = runtime.agent_last_summary.get(instance_id)
    status_data = runtime.agent_last_status.get(instance_id)
    heartbeat_metrics = runtime.agent_last_heartbeat_metrics.get(instance_id, {})
    process_alive, heartbeat_fresh, last_heartbeat = _widget_agent_liveness(runtime, instance_id)
    warnings: list[str] = []

    if not isinstance(summary, dict):
        summary = {}
        warnings.append("no_summary_yet")
    if not isinstance(status_data, dict):
        status_data = {}
        warnings.append("no_status_yet")

    if not isinstance(heartbeat_metrics, dict):
        heartbeat_metrics = {}
        warnings.append("no_heartbeat_metrics")

    folder_available = status_data.get(
        "trail_folder_available", heartbeat_metrics.get("trail_folder_available")
    )
    active_session = bool(
        status_data.get("session_id") or heartbeat_metrics.get("active_session")
    )
    last_activity_age_s = _safe_float(
        status_data.get("last_activity_age_s", heartbeat_metrics.get("last_activity_age_s"))
    )
    pending_change_count = int(
        status_data.get("pending_change_count", heartbeat_metrics.get("pending_change_count", 0))
        or 0
    )
    changes_seen_total = int(
        status_data.get("changes_seen_total", heartbeat_metrics.get("changes_seen_total", 0))
        or 0
    )

    poll_interval_s = _safe_float(status_data.get("poll_interval_s")) or poll_interval_s
    active_window_s = _safe_float(status_data.get("active_window_s")) or active_window_s

    file_info = summary.get("file")
    if not isinstance(file_info, dict):
        changed_files = summary.get("changed_files", [])
        if isinstance(changed_files, list) and changed_files and isinstance(changed_files[0], dict):
            file_info = changed_files[0]
        else:
            file_info = {}
    status_latest_file = status_data.get("latest_file")
    if isinstance(status_latest_file, dict):
        file_info = status_latest_file

    file_name = file_info.get("name") if isinstance(file_info, dict) else None
    modified_at = file_info.get("modified_at") if isinstance(file_info, dict) else None
    if file_name is None:
        file_name = heartbeat_metrics.get("latest_file_name")
    if modified_at is None:
        modified_at = heartbeat_metrics.get("latest_file_modified_at")
    last_activity_at = (
        status_data.get("last_activity_at")
        or summary.get("last_activity_at")
        or modified_at
    )
    session_id = status_data.get("session_id") or summary.get("session_id")
    event_name = summary.get("event") or status_data.get("state") or "-"

    status_state = status_data.get("state")
    status_reason = status_data.get("state_reason")

    if not process_alive:
        state_name = "unknown"
        state_badge = _render_status_badge("not running", "#24181a", "#5e3c40", "#d8a7ad")
        state_reason = "No live managed trail-tracker process is attached."
        warnings.append("agent_not_running")
    elif not heartbeat_fresh:
        state_name = "unknown"
        state_badge = _render_status_badge("heartbeat stale", "#3a3214", "#8c7531", "#f5d98a")
        state_reason = "Trail-tracker process is alive, but heartbeat freshness is stale."
        warnings.append("heartbeat_stale")
    elif isinstance(status_state, str) and status_state.strip():
        normalized_status_state = status_state.strip().lower().replace("_", " ")
        if normalized_status_state == "path unavailable":
            state_name = "path unavailable"
            state_badge = _render_status_badge(
                "path unavailable", "#3a181b", "#8c4549", "#ffb0b7"
            )
        elif normalized_status_state == "active":
            state_name = "active"
            state_badge = _render_status_badge("active", "#17351f", "#2d6a3f", "#98f0b2")
        elif normalized_status_state == "cooling":
            state_name = "cooling"
            state_badge = _render_status_badge("cooling", "#3a3214", "#8c7531", "#f5d98a")
        elif normalized_status_state == "inactive":
            state_name = "inactive"
            state_badge = _render_status_badge("inactive", "#24181a", "#5e3c40", "#d8a7ad")
        else:
            state_name = "unknown"
            state_badge = _render_status_badge("unknown", "#2a2d34", "#4e5665", "#c6d0de")
        state_reason = str(status_reason or "Trail tracker reported current internal state.")
    elif folder_available is False:
        state_name = "path unavailable"
        state_badge = _render_status_badge(
            "path unavailable", "#3a181b", "#8c4549", "#ffb0b7"
        )
        state_reason = "Trail folder is unavailable to the agent."
    elif last_activity_age_s is not None and last_activity_age_s <= poll_interval_s:
        state_name = "active"
        state_badge = _render_status_badge("active", "#17351f", "#2d6a3f", "#98f0b2")
        state_reason = "Trail activity was seen in the current polling window."
    elif last_activity_age_s is not None and last_activity_age_s <= active_window_s:
        state_name = "cooling"
        state_badge = _render_status_badge("cooling", "#3a3214", "#8c7531", "#f5d98a")
        state_reason = "No fresh trail change this poll cycle, but the session is still inside the active window."
    elif active_session:
        state_name = "cooling"
        state_badge = _render_status_badge("cooling", "#3a3214", "#8c7531", "#f5d98a")
        state_reason = "Session is still open, but the last activity age is not yet available."
    else:
        state_name = "inactive"
        state_badge = _render_status_badge("inactive", "#24181a", "#5e3c40", "#d8a7ad")
        state_reason = "No trail activity was observed inside the configured active window."

    if folder_available is None:
        warnings.append("trail_folder_state_unknown")
    row_css = {
        "active": "folder-row folder-row-created",
        "cooling": "folder-row folder-row-modified",
        "inactive": "folder-row folder-row-deleted",
        "path unavailable": "folder-row folder-row-deleted",
        "unknown": "folder-row folder-row-empty",
    }.get(state_name, "folder-row folder-row-empty")

    changed_files_raw = summary.get("changed_files", [])
    trail_rows: list[dict[str, str]] = []
    if isinstance(changed_files_raw, list):
        for item in changed_files_raw[:3]:
            if not isinstance(item, dict):
                continue
            trail_rows.append(
                {
                    "css": row_css,
                    "path": _escape_or_dash(item.get("name")),
                    "status": html.escape(state_name),
                    "time": _escape_or_dash(item.get("modified_at")),
                }
            )
    if not trail_rows and file_name is not None:
        trail_rows.append(
            {
                "css": row_css,
                "path": _escape_or_dash(file_name),
                "status": html.escape(state_name),
                "time": _escape_or_dash(modified_at or last_activity_at),
            }
        )

    if trail_rows:
        row_html = "".join(
            (
                f'<li class="{row["css"]}">'
                f'<span class="folder-col folder-path">{row["path"]}</span>'
                f'<span class="folder-col folder-size">{row["status"]}</span>'
                f'<time class="folder-col folder-time">{row["time"]}</time>'
                "</li>"
            )
            for row in trail_rows
        )
    else:
        row_html = (
            f'<li class="{row_css}">'
            '<span class="folder-col folder-path">No trail files active in current window</span>'
            '<span class="folder-col folder-size">-</span>'
            '<span class="folder-col folder-time">-</span>'
            "</li>"
        )

    status_label = {
        "active": "active",
        "cooling": "cooling",
        "inactive": "inactive",
        "path unavailable": "path unavailable",
        "unknown": "unknown",
    }.get(state_name, state_name)

    html_fragment = (
        '<div class="folder-widget-root">'
        '<div class="folder-widget-summary">'
        f'<span class="folder-count">{html.escape(status_label)}</span>'
        f'<span class="folder-count">poll {_format_seconds(poll_interval_s)}</span>'
        f'<span class="folder-count">window {_format_seconds(active_window_s)}</span>'
        f'<span class="folder-count">age {_format_seconds(last_activity_age_s)}</span>'
        "</div>"
        '<ul class="folder-widget-list">'
        f"{row_html}"
        "</ul>"
        "</div>"
    )

    state_token = (
        f"{state_name}:{file_name}:{last_activity_at}:"
        f"{last_activity_age_s}:{active_session}:{changes_seen_total}:"
        f"{pending_change_count}:{process_alive}:{heartbeat_fresh}"
    )
    return {
        "accepted": True,
        "status": "ok",
        "request_id": request_id,
        "render": {
            "mode": mode,
            "html": html_fragment,
            "ttl_ms": ttl_ms,
            "state_token": state_token,
            "warnings": warnings,
        },
    }
