#!/usr/bin/env python3
"""Screen tracker agent.

Captures periodic screenshots to artifact storage and emits lightweight
artifact references on flush.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from mimolo.agents.base_agent import BaseAgent
from mimolo.common.paths import get_mimolo_data_dir

AGENT_LABEL = "screen_tracker"
AGENT_ID = "screen_tracker-001"
AGENT_VERSION = "0.1.0"
PROTOCOL_VERSION = "0.3"
MIN_APP_VERSION = "0.3.0"


class ScreenTrackerAgent(BaseAgent):
    """Periodic screenshot capture agent."""

    def __init__(
        self,
        agent_id: str,
        agent_label: str,
        capture_interval_s: float,
        heartbeat_interval: float,
        mode: str,
        image_format: str,
        jpeg_quality: int,
        scale: float,
        letterbox: bool,
        max_dimension_px: int,
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
        self.mode = mode
        self.image_format = image_format
        self.jpeg_quality = max(1, min(100, jpeg_quality))
        self.scale = max(0.01, min(1.0, scale))
        self.letterbox = letterbox
        self.max_dimension_px = max(320, max_dimension_px)
        self.max_summary_captures = max(1, max_summary_captures)

        data_root_raw = os.getenv("MIMOLO_DATA_DIR")
        data_root = Path(data_root_raw) if data_root_raw else get_mimolo_data_dir()
        self.instance_root = data_root / "agents" / "screen_tracker" / self.agent_label
        self.artifacts_root = self.instance_root / "artifacts"
        self.index_root = self.instance_root / "index"
        self.archives_root = self.instance_root / "archives"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.archives_root.mkdir(parents=True, exist_ok=True)

        self._segment_start: datetime | None = None
        self._captures_pending_flush: list[dict[str, Any]] = []
        self._captures_total = 0
        self._capture_failures_total = 0
        self._dropped_capture_count = 0
        self._last_capture_at: datetime | None = None
        self._artifact_store_bytes = 0
        self._degraded = False
        self._warned_active_window = False

    def _new_capture_path(self, now: datetime) -> tuple[str, Path]:
        artifact_id = f"{now.strftime('%Y%m%dT%H%M%S')}_{now.microsecond:06d}"
        subdir = self.artifacts_root / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
        subdir.mkdir(parents=True, exist_ok=True)
        filename = f"{artifact_id}.{self.image_format}"
        return artifact_id, subdir / filename

    def _capture_to_path(self, output_path: Path) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("capture_backend_unavailable")

        if self.mode == "active_window" and not self._warned_active_window:
            self.send_message(
                {
                    "type": "status",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": self.protocol_version,
                    "agent_version": self.agent_version,
                    "health": "degraded",
                    "message": "active_window mode is not yet distinct; using full_screen backend.",
                    "data": {"requested_mode": self.mode, "effective_mode": "full_screen"},
                }
            )
            self._warned_active_window = True

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

        if self.max_dimension_px > 0:
            resize_result = subprocess.run(
                ["sips", "-Z", str(self.max_dimension_px), str(output_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if resize_result.returncode != 0:
                detail = resize_result.stderr.strip() or resize_result.stdout.strip()
                raise RuntimeError(f"resize_failed:{detail or resize_result.returncode}")

    def _read_dimensions(self, image_path: Path) -> tuple[int | None, int | None]:
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

    def _accumulate(self, now: datetime) -> None:
        if self._segment_start is None:
            self._segment_start = now

        artifact_id, output_path = self._new_capture_path(now)
        try:
            self._capture_to_path(output_path)
            stat_result = output_path.stat()
            sha256 = self._sha256_file(output_path)
            width, height = self._read_dimensions(output_path)
        except (OSError, RuntimeError):
            # External capture backend/filesystem can fail; continue running and report error.
            self._capture_failures_total += 1
            self._degraded = True
            self._emit_capture_error(now, "capture_failed")
            return

        rel_path = output_path.relative_to(self.instance_root).as_posix()
        record: dict[str, Any] = {
            "artifact_id": artifact_id,
            "rel_path": rel_path,
            "sha256": sha256,
            "bytes": stat_result.st_size,
            "mime": "image/jpeg" if self.image_format == "jpg" else "image/png",
            "captured_at": now.isoformat(),
            "width": width,
            "height": height,
            "scale": self.scale,
            "quality": self.jpeg_quality if self.image_format == "jpg" else None,
            "retention_class": "manual",
        }
        self._captures_pending_flush.append(record)
        self._captures_total += 1
        self._artifact_store_bytes += stat_result.st_size
        self._last_capture_at = now
        self._degraded = False

    def _take_snapshot(self, now: datetime) -> tuple[datetime, datetime, list[dict[str, Any]]]:
        start = self._segment_start or now
        captures = list(self._captures_pending_flush)
        self._captures_pending_flush.clear()
        self._segment_start = now
        return start, now, captures

    def _format_summary(
        self, snapshot: list[dict[str, Any]], start: datetime, end: datetime
    ) -> dict[str, Any]:
        captures = snapshot
        if len(captures) > self.max_summary_captures:
            dropped = len(captures) - self.max_summary_captures
            captures = captures[: self.max_summary_captures]
        else:
            dropped = 0
        self._dropped_capture_count += dropped

        return {
            "schema": "screen_tracker.summary.v1",
            "capture_mode": self.mode,
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
        "active_window",
        help="Capture mode: active_window or full_screen.",
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
    max_dimension_px: int = typer.Option(
        1920,
        help="Maximum output dimension for captures.",
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
    requested_mode = mode.strip().lower()
    if requested_mode not in {"active_window", "full_screen"}:
        requested_mode = "active_window"

    requested_format = image_format.strip().lower()
    if requested_format not in {"jpg", "png"}:
        requested_format = "jpg"

    agent = ScreenTrackerAgent(
        agent_id=AGENT_ID,
        agent_label=AGENT_LABEL,
        capture_interval_s=max(1.0, capture_interval_s),
        heartbeat_interval=max(1.0, heartbeat_interval_s),
        mode=requested_mode,
        image_format=requested_format,
        jpeg_quality=jpeg_quality,
        scale=scale,
        letterbox=letterbox,
        max_dimension_px=max_dimension_px,
        max_summary_captures=max_summary_captures,
    )
    agent.run()


if __name__ == "__main__":
    typer.run(main)
