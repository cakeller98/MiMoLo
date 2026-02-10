"""Widget-related helpers for Runtime."""

from __future__ import annotations

import base64
import html
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mimolo.common.paths import get_mimolo_data_dir

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


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
    min_refresh_ms = max(
        1000, int(round(runtime._effective_heartbeat_interval_s(plugin_cfg) * 1000))
    )
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
        return {
            "accepted": False,
            "status": "unknown_instance",
            "request_id": request_id,
            "render": {
                "mode": mode,
                "html": '<div class="widget-muted">unknown instance</div>',
                "ttl_ms": 1000,
                "state_token": None,
                "warnings": ["unknown_instance"],
            },
        }

    latest_path, missing_reason = resolve_screen_tracker_thumbnail(runtime, instance_id)
    ttl_ms = max(1000, int(round(runtime._effective_heartbeat_interval_s(plugin_cfg) * 1000)))

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
