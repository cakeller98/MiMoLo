"""Monitor settings mutation helpers for Runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


def update_monitor_settings(
    runtime: Runtime, updates: dict[str, Any]
) -> tuple[bool, str, dict[str, Any]]:
    """Update monitor settings with strict key validation and persistence."""
    allowed_update_keys = {
        "cooldown_seconds",
        "poll_tick_s",
        "console_verbosity",
    }
    unknown_keys = sorted([k for k in updates.keys() if k not in allowed_update_keys])
    if unknown_keys:
        return (
            False,
            f"unknown_keys:{','.join(unknown_keys)}",
            {"unknown_keys": unknown_keys},
        )

    merged = runtime.config.monitor.model_dump()
    merged.update({k: v for k, v in updates.items() if k in allowed_update_keys})

    try:
        monitor_type = type(runtime.config.monitor)
        updated_monitor = monitor_type.model_validate(merged)
    except Exception as e:
        return False, f"invalid_updates:{e}", {}

    previous_monitor = runtime.config.monitor
    runtime.config.monitor = updated_monitor
    runtime.cooldown.cooldown_seconds = updated_monitor.cooldown_seconds

    saved, save_detail = runtime._persist_runtime_config()
    if not saved:
        runtime.config.monitor = previous_monitor
        runtime.cooldown.cooldown_seconds = previous_monitor.cooldown_seconds
        return False, save_detail, {}

    return True, "updated", runtime._snapshot_monitor_settings()
