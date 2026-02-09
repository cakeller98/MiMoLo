#!/usr/bin/env python3
"""Screen tracker agent.

Captures periodic screenshots to artifact storage and emits lightweight artifact
references on flush.

Modes:
- full_screen: capture full display
- app_window: capture a specific app window via macOS window id

When app_window target is unavailable, emits a generated SVG placeholder
artifact so downstream UIs have a deterministic image to render.
"""

from __future__ import annotations

import hashlib
import html
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2
from typing import Any

import typer

from mimolo.agents.base_agent import BaseAgent
from mimolo.common.paths import get_mimolo_data_dir

AGENT_LABEL = "screen_tracker"
AGENT_ID = "screen_tracker-001"
AGENT_VERSION = "0.2.0"
PROTOCOL_VERSION = "0.3"
MIN_APP_VERSION = "0.3.0"


def normalize_capture_mode(mode: str) -> str:
    """Normalize capture mode while preserving compatibility aliases."""
    normalized = mode.strip().lower()
    if normalized == "active_window":
        return "app_window"
    if normalized in {"app_window", "full_screen"}:
        return normalized
    return "full_screen"


def normalize_image_format(image_format: str) -> str:
    """Normalize configured image format."""
    normalized = image_format.strip().lower()
    if normalized in {"jpeg", "jpg"}:
        return "jpg"
    if normalized == "png":
        return "png"
    return "jpg"


def compute_thumbnail_size(
    source_width: int, source_height: int, target_width: int, target_height: int
) -> tuple[int, int]:
    """Compute aspect-preserving thumbnail size within the configured bounds."""
    if source_width <= 0 or source_height <= 0:
        return target_width, target_height
    scale = min(target_width / source_width, target_height / source_height, 1.0)
    out_w = max(1, int(round(source_width * scale)))
    out_h = max(1, int(round(source_height * scale)))
    return out_w, out_h


@dataclass(frozen=True)
class WindowLookupResult:
    """Result of resolving a target app window id."""

    detail: str = ""
    reason: str = "window_not_found"
    window_id: int | None = None


def parse_window_lookup_output(stdout: str) -> WindowLookupResult:
    """Parse osascript window lookup stdout."""
    text = stdout.strip()
    if not text:
        return WindowLookupResult(reason="window_not_found", detail="empty_output")
    if text.startswith("WINDOW_ID:"):
        value = text.split(":", 1)[1].strip()
        if value.isdigit():
            return WindowLookupResult(window_id=int(value), reason="ok")
        return WindowLookupResult(reason="window_not_found", detail="invalid_window_id")
    if text in {"APP_NOT_OPEN", "WINDOW_NOT_OPEN", "WINDOW_NOT_FOUND", "MISSING_TARGET_APP"}:
        return WindowLookupResult(reason=text.lower())
    return WindowLookupResult(reason="window_not_found", detail=text)


def _mime_for_path(path: Path) -> str:
    """Infer mime type for image artifact by extension."""
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


class ScreenTrackerAgent(BaseAgent):
    """Periodic screenshot capture agent (macOS backend)."""

    def __init__(
        self,
        agent_id: str,
        agent_label: str,
        capture_interval_s: float,
        heartbeat_interval: float,
        mode: str,
        target_app: str,
        target_window_title_contains: str,
        image_format: str,
        jpeg_quality: int,
        scale: float,
        letterbox: bool,
        capture_max_dimension_px: int,
        thumbnail_width_px: int,
        thumbnail_height_px: int,
        max_summary_captures: int,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_label=agent_label,
            sample_interval=capture_interval_s,
            heartbeat_interval=heartbeat_interval,
            protocol_version=PROTOCOL_VERSION,
            agent_version=AGENT_VERSION,
            min_app_version=MIN_APP_VERSION,
        )
        self.mode = normalize_capture_mode(mode)
        self.target_app = target_app.strip()
        self.target_window_title_contains = target_window_title_contains.strip()
        self.image_format = normalize_image_format(image_format)
        self.jpeg_quality = max(1, min(100, jpeg_quality))
        self.scale = max(0.01, min(1.0, scale))
        self.letterbox = letterbox
        self.capture_max_dimension_px = max(320, capture_max_dimension_px)
        self.thumbnail_width_px = max(64, thumbnail_width_px)
        self.thumbnail_height_px = max(64, thumbnail_height_px)
        self.max_summary_captures = max(1, max_summary_captures)

        data_root_raw = os.getenv("MIMOLO_DATA_DIR")
        data_root = Path(data_root_raw) if data_root_raw else get_mimolo_data_dir()
        self.instance_root = data_root / "agents" / "screen_tracker" / self.agent_label
        self.full_artifacts_root = self.instance_root / "artifacts" / "full"
        self.thumbnail_artifacts_root = self.instance_root / "artifacts" / "thumb"
        self.index_root = self.instance_root / "index"
        self.archives_root = self.instance_root / "archives"
        self.full_artifacts_root.mkdir(parents=True, exist_ok=True)
        self.thumbnail_artifacts_root.mkdir(parents=True, exist_ok=True)
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.archives_root.mkdir(parents=True, exist_ok=True)

        self._segment_start: datetime | None = None
        self._captures_pending_flush: list[dict[str, Any]] = []
        self._captures_total = 0
        self._capture_failures_total = 0
        self._placeholder_total = 0
        self._target_unavailable_total = 0
        self._dropped_capture_count = 0
        self._last_capture_at: datetime | None = None
        self._artifact_store_bytes = 0
        self._degraded = False

    def _new_capture_paths(self, now: datetime) -> tuple[str, Path, Path]:
        """Allocate full + thumbnail artifact paths."""
        artifact_id = f"{now.strftime('%Y%m%dT%H%M%S')}_{now.microsecond:06d}"
        full_subdir = (
            self.full_artifacts_root / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
        )
        thumb_subdir = (
            self.thumbnail_artifacts_root
            / now.strftime("%Y")
            / now.strftime("%m")
            / now.strftime("%d")
        )
        full_subdir.mkdir(parents=True, exist_ok=True)
        thumb_subdir.mkdir(parents=True, exist_ok=True)
        extension = self.image_format
        return (
            artifact_id,
            full_subdir / f"{artifact_id}.{extension}",
            thumb_subdir / f"{artifact_id}.{extension}",
        )

    def _capture_full_screen_to_path(self, output_path: Path) -> None:
        """Capture full screen into output path."""
        if sys.platform != "darwin":
            raise RuntimeError("capture_backend_unavailable")
        result = subprocess.run(
            ["screencapture", "-x", str(output_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or str(result.returncode)
            raise RuntimeError(f"screencapture_failed:{detail}")
        if not output_path.exists():
            raise RuntimeError("capture_file_missing")
        self._postprocess_capture(output_path)

    def _capture_window_to_path(self, output_path: Path, window_id: int) -> None:
        """Capture a specific macOS window id into output path."""
        if sys.platform != "darwin":
            raise RuntimeError("capture_backend_unavailable")
        result = subprocess.run(
            ["screencapture", "-x", "-l", str(window_id), str(output_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or str(result.returncode)
            raise RuntimeError(f"screencapture_failed:{detail}")
        if not output_path.exists():
            raise RuntimeError("capture_file_missing")
        self._postprocess_capture(output_path)

    def _postprocess_capture(self, output_path: Path) -> None:
        """Apply post-capture processing (size bound, jpeg quality)."""
        if self.capture_max_dimension_px > 0:
            resize_result = subprocess.run(
                ["sips", "-Z", str(self.capture_max_dimension_px), str(output_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if resize_result.returncode != 0:
                detail = resize_result.stderr.strip() or resize_result.stdout.strip()
                raise RuntimeError(f"resize_failed:{detail or resize_result.returncode}")

        if self.image_format == "jpg":
            quality_result = subprocess.run(
                [
                    "sips",
                    "-s",
                    "format",
                    "jpeg",
                    "-s",
                    "formatOptions",
                    str(self.jpeg_quality),
                    str(output_path),
                    "--out",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if quality_result.returncode != 0:
                detail = quality_result.stderr.strip() or quality_result.stdout.strip()
                raise RuntimeError(f"jpeg_optimize_failed:{detail or quality_result.returncode}")

    def _read_dimensions(self, image_path: Path) -> tuple[int | None, int | None]:
        """Read image width/height via sips."""
        if sys.platform != "darwin":
            return None, None
        result = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(image_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None, None
        width: int | None = None
        height: int | None = None
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if line.startswith("pixelWidth:"):
                value = line.split(":", 1)[1].strip()
                if value.isdigit():
                    width = int(value)
            elif line.startswith("pixelHeight:"):
                value = line.split(":", 1)[1].strip()
                if value.isdigit():
                    height = int(value)
        return width, height

    def _sha256_file(self, image_path: Path) -> str:
        """Hash one artifact for dedupe/traceability."""
        digest = hashlib.sha256()
        with image_path.open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _emit_capture_error(self, now: datetime, detail: str) -> None:
        self.send_message(
            {
                "type": "error",
                "timestamp": now.isoformat(),
                "agent_id": self.agent_id,
                "agent_label": self.agent_label,
                "protocol_version": self.protocol_version,
                "agent_version": self.agent_version,
                "health": "degraded",
                    "message": detail,
                    "data": {},
                }
            )

    def _apple_script_literal(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _build_window_lookup_script(self) -> str:
        target_literal = self._apple_script_literal(self.target_app)
        title_literal = self._apple_script_literal(self.target_window_title_contains)
        return (
            f"set targetApp to {target_literal}\n"
            f"set titleFilter to {title_literal}\n"
            "if targetApp is \"\" then return \"MISSING_TARGET_APP\"\n"
            "tell application \"System Events\"\n"
            "  set matchingProcesses to (every process whose name is targetApp)\n"
            "  if (count of matchingProcesses) is 0 then return \"APP_NOT_OPEN\"\n"
            "  set procRef to item 1 of matchingProcesses\n"
            "  set windowsList to (every window of procRef)\n"
            "  if (count of windowsList) is 0 then return \"WINDOW_NOT_OPEN\"\n"
            "  repeat with w in windowsList\n"
            "    set windowTitle to \"\"\n"
            "    try\n"
            "      set windowTitle to (name of w as string)\n"
            "    end try\n"
            "    if titleFilter is \"\" or windowTitle contains titleFilter then\n"
            "      try\n"
            "        set winNumber to value of attribute \"AXWindowNumber\" of w\n"
            "        if winNumber is not missing value then\n"
            "          return \"WINDOW_ID:\" & (winNumber as string)\n"
            "        end if\n"
            "      end try\n"
            "    end if\n"
            "  end repeat\n"
            "  return \"WINDOW_NOT_FOUND\"\n"
            "end tell\n"
        )

    def _resolve_window_target(self) -> WindowLookupResult:
        """Resolve configured app window id on macOS."""
        if sys.platform != "darwin":
            return WindowLookupResult(reason="capture_backend_unavailable")
        script = self._build_window_lookup_script()
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or str(result.returncode)
            return WindowLookupResult(reason="lookup_error", detail=detail)
        parsed = parse_window_lookup_output(result.stdout)
        return parsed

    def _write_placeholder_svg(self, output_path: Path, message: str) -> None:
        """Write deterministic SVG placeholder for unavailable window targets."""
        safe_message = html.escape(message)
        safe_sub = html.escape(datetime.now(UTC).isoformat(timespec="seconds"))
        svg_text = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.thumbnail_width_px}" '
            f'height="{self.thumbnail_height_px}" viewBox="0 0 {self.thumbnail_width_px} '
            f'{self.thumbnail_height_px}">'
            '<rect width="100%" height="100%" fill="#20252d"/>'
            '<rect x="8" y="8" width="calc(100% - 16)" height="calc(100% - 16)" '
            'fill="none" stroke="#4f5b6d" stroke-dasharray="6 4"/>'
            f'<text x="50%" y="46%" text-anchor="middle" fill="#d8dde6" '
            'font-family="Menlo, Monaco, Consolas, monospace" font-size="20">'
            f"{safe_message}</text>"
            f'<text x="50%" y="58%" text-anchor="middle" fill="#8f9db2" '
            'font-family="Menlo, Monaco, Consolas, monospace" font-size="12">'
            f"{safe_sub}</text>"
            "</svg>"
        )
        output_path.write_text(svg_text, encoding="utf-8")

    def _create_thumbnail(self, source_path: Path, thumbnail_path: Path) -> None:
        """Create aspect-preserving thumbnail from captured artifact."""
        copy2(source_path, thumbnail_path)
        source_w, source_h = self._read_dimensions(source_path)
        if source_w is None or source_h is None:
            return
        out_w, out_h = compute_thumbnail_size(
            source_w,
            source_h,
            self.thumbnail_width_px,
            self.thumbnail_height_px,
        )
        resize_result = subprocess.run(
            ["sips", "--resampleHeightWidth", str(out_h), str(out_w), str(thumbnail_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if resize_result.returncode != 0:
            detail = resize_result.stderr.strip() or resize_result.stdout.strip()
            raise RuntimeError(f"thumbnail_resize_failed:{detail or resize_result.returncode}")

    def _build_placeholder_message(self, reason: str) -> str:
        """Translate window lookup reason into user-facing placeholder text."""
        app_name = self.target_app if self.target_app else "Target app"
        if reason in {"app_not_open", "window_not_open", "window_not_found"}:
            return f"{app_name} not open"
        if reason == "missing_target_app":
            return "Target app not configured"
        if reason == "capture_backend_unavailable":
            return "Capture backend unavailable"
        if reason == "lookup_error":
            return f"{app_name} inaccessible"
        return f"{app_name} unavailable"

    def _make_artifact_ref(self, path: Path, captured_at: datetime) -> dict[str, Any]:
        stat_result = path.stat()
        width, height = self._read_dimensions(path)
        return {
            "rel_path": path.relative_to(self.instance_root).as_posix(),
            "bytes": stat_result.st_size,
            "sha256": self._sha256_file(path),
            "mime": _mime_for_path(path),
            "captured_at": captured_at.isoformat(),
            "width": width,
            "height": height,
        }

    def _accumulate(self, now: datetime) -> None:
        """Capture one frame and store artifact references for summary flush."""
        if self._segment_start is None:
            self._segment_start = now

        artifact_id, full_path, thumbnail_path = self._new_capture_paths(now)
        placeholder_reason: str | None = None
        capture_kind = "screenshot"
        full_artifact: dict[str, Any] | None = None
        thumbnail_artifact: dict[str, Any] | None = None

        try:
            if self.mode == "app_window":
                lookup = self._resolve_window_target()
                if lookup.window_id is None:
                    capture_kind = "placeholder"
                    placeholder_reason = lookup.reason
                    self._target_unavailable_total += 1
                    placeholder_path = thumbnail_path.with_suffix(".svg")
                    self._write_placeholder_svg(
                        placeholder_path,
                        self._build_placeholder_message(lookup.reason),
                    )
                    thumbnail_artifact = self._make_artifact_ref(placeholder_path, now)
                    if lookup.reason in {"lookup_error", "capture_backend_unavailable"}:
                        self._capture_failures_total += 1
                        self._degraded = True
                        detail = (
                            f"window_lookup_failed:{lookup.detail}"
                            if lookup.detail
                            else "window_lookup_failed"
                        )
                        self._emit_capture_error(now, detail)
                    else:
                        self._degraded = False
                        self._placeholder_total += 1
                else:
                    self._capture_window_to_path(full_path, lookup.window_id)
                    self._create_thumbnail(full_path, thumbnail_path)
                    full_artifact = self._make_artifact_ref(full_path, now)
                    thumbnail_artifact = self._make_artifact_ref(thumbnail_path, now)
                    self._degraded = False
            else:
                self._capture_full_screen_to_path(full_path)
                self._create_thumbnail(full_path, thumbnail_path)
                full_artifact = self._make_artifact_ref(full_path, now)
                thumbnail_artifact = self._make_artifact_ref(thumbnail_path, now)
                self._degraded = False
        except (OSError, RuntimeError) as error:
            # External capture backend/filesystem can fail; continue running and report error.
            self._capture_failures_total += 1
            self._degraded = True
            self._emit_capture_error(now, str(error))
            return

        record: dict[str, Any] = {
            "artifact_id": artifact_id,
            "capture_kind": capture_kind,
            "capture_mode": self.mode,
            "captured_at": now.isoformat(),
            "target_app": self.target_app or None,
            "target_window_title_contains": self.target_window_title_contains or None,
            "full": full_artifact,
            "thumbnail": thumbnail_artifact,
            "placeholder_reason": placeholder_reason,
            "scale": self.scale,
            "quality": self.jpeg_quality if self.image_format == "jpg" else None,
            "retention_class": "manual",
        }

        if full_artifact is not None:
            self._artifact_store_bytes += int(full_artifact["bytes"])
        if thumbnail_artifact is not None:
            self._artifact_store_bytes += int(thumbnail_artifact["bytes"])

        self._captures_pending_flush.append(record)
        self._captures_total += 1
        self._last_capture_at = now

    def _take_snapshot(self, now: datetime) -> tuple[datetime, datetime, list[dict[str, Any]]]:
        """Return pending captures and reset segment accumulator."""
        start = self._segment_start or now
        captures = list(self._captures_pending_flush)
        self._captures_pending_flush.clear()
        self._segment_start = now
        return start, now, captures

    def _format_summary(
        self, snapshot: list[dict[str, Any]], start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Format summary payload with artifact references only."""
        captures = snapshot
        if len(captures) > self.max_summary_captures:
            dropped = len(captures) - self.max_summary_captures
            captures = captures[: self.max_summary_captures]
        else:
            dropped = 0
        self._dropped_capture_count += dropped

        return {
            "schema": "screen_tracker.summary.v2",
            "capture_mode": self.mode,
            "target_app": self.target_app or None,
            "target_window_title_contains": self.target_window_title_contains or None,
            "thumbnail_bounds": {
                "width_px": self.thumbnail_width_px,
                "height_px": self.thumbnail_height_px,
            },
            "window": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration_s": (end - start).total_seconds(),
            },
            "capture_count": len(captures),
            "captures": captures,
            "active_app_samples": [],
            "dropped_capture_count": dropped,
        }

    def _accumulated_count(self) -> int:
        return len(self._captures_pending_flush)

    def _heartbeat_metrics(self) -> dict[str, Any]:
        metrics = super()._heartbeat_metrics()
        metrics["captures_total"] = self._captures_total
        metrics["captures_pending_flush"] = len(self._captures_pending_flush)
        metrics["placeholder_total"] = self._placeholder_total
        metrics["target_unavailable_total"] = self._target_unavailable_total
        if self._last_capture_at is None:
            metrics["last_capture_age_s"] = None
        else:
            metrics["last_capture_age_s"] = max(
                0.0, (datetime.now(UTC) - self._last_capture_at).total_seconds()
            )
        metrics["capture_failures_total"] = self._capture_failures_total
        metrics["artifact_store_bytes"] = self._artifact_store_bytes
        if self._degraded:
            metrics["health"] = "degraded"
        return metrics


def main(
    capture_interval_s: float = typer.Option(
        60.0,
        help="Seconds between captures.",
    ),
    mode: str = typer.Option(
        "full_screen",
        help="Capture mode: app_window or full_screen (active_window alias supported).",
    ),
    target_app: str = typer.Option(
        "",
        help="Target app name for app_window mode (e.g. 'Plasticity').",
    ),
    target_window_title_contains: str = typer.Option(
        "",
        help="Optional window title substring filter for app_window mode.",
    ),
    image_format: str = typer.Option(
        "jpg",
        help="Image format: jpg or png.",
    ),
    jpeg_quality: int = typer.Option(
        35,
        help="JPEG quality (1-100). Used only when image_format=jpg.",
    ),
    scale: float = typer.Option(
        0.10,
        help="Requested scale factor metadata for captures.",
    ),
    letterbox: bool = typer.Option(
        False,
        "--letterbox/--no-letterbox",
        help="Reserved for future resize behavior.",
    ),
    capture_max_dimension_px: int = typer.Option(
        1920,
        help="Maximum output dimension for captured full-resolution artifacts.",
    ),
    thumbnail_width_px: int = typer.Option(
        640,
        help="Thumbnail bounding width in pixels.",
    ),
    thumbnail_height_px: int = typer.Option(
        360,
        help="Thumbnail bounding height in pixels.",
    ),
    heartbeat_interval_s: float = typer.Option(
        15.0,
        help="Heartbeat interval in seconds.",
    ),
    max_summary_captures: int = typer.Option(
        50,
        help="Maximum capture references emitted in each summary.",
    ),
) -> None:
    """Run the screen tracker agent."""
    agent = ScreenTrackerAgent(
        agent_id=AGENT_ID,
        agent_label=AGENT_LABEL,
        capture_interval_s=max(1.0, capture_interval_s),
        heartbeat_interval=max(1.0, heartbeat_interval_s),
        mode=mode,
        target_app=target_app,
        target_window_title_contains=target_window_title_contains,
        image_format=image_format,
        jpeg_quality=jpeg_quality,
        scale=scale,
        letterbox=letterbox,
        capture_max_dimension_px=capture_max_dimension_px,
        thumbnail_width_px=thumbnail_width_px,
        thumbnail_height_px=thumbnail_height_px,
        max_summary_captures=max_summary_captures,
    )
    agent.run()


if __name__ == "__main__":
    typer.run(main)
