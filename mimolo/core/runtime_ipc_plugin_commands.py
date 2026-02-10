"""Plugin package IPC command handling for Runtime."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


def maybe_handle_plugin_store_command(
    runtime: Runtime,
    cmd: str,
    request: dict[str, Any],
    now: str,
) -> dict[str, Any] | None:
    """Handle plugin package filesystem/registry commands when matched."""
    if cmd == "list_installed_plugins":
        plugin_class_raw = request.get("plugin_class")
        plugin_class = (
            str(plugin_class_raw).strip().lower()
            if plugin_class_raw is not None and str(plugin_class_raw).strip()
            else "all"
        )
        try:
            installed = runtime._plugin_store.list_installed(plugin_class)
        except ValueError as e:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": str(e),
            }
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "plugin_class": plugin_class,
                "installed_plugins": installed,
                "source_of_truth": "filesystem",
                "registry_role": "cache_only",
            },
        }

    if cmd == "inspect_plugin_archive":
        zip_path_raw = request.get("zip_path")
        zip_path = (
            str(zip_path_raw).strip()
            if zip_path_raw is not None and str(zip_path_raw).strip()
            else ""
        )
        if not zip_path:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_zip_path",
            }

        ok, detail, payload = runtime._plugin_store.inspect_plugin_archive(
            Path(zip_path)
        )
        if not ok:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": detail,
                "data": payload,
            }
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "accepted": True,
                "inspection": payload,
                "source_of_truth": "filesystem",
                "registry_role": "cache_only",
            },
        }

    if cmd in {"install_plugin", "upgrade_plugin"}:
        zip_path_raw = request.get("zip_path")
        zip_path = (
            str(zip_path_raw).strip()
            if zip_path_raw is not None and str(zip_path_raw).strip()
            else ""
        )
        if not zip_path:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_zip_path",
            }

        plugin_class_raw = request.get("plugin_class")
        plugin_class = (
            str(plugin_class_raw).strip().lower()
            if plugin_class_raw is not None and str(plugin_class_raw).strip()
            else "agents"
        )

        ok, detail, payload = runtime._plugin_store.install_plugin_archive(
            Path(zip_path),
            plugin_class,
            require_newer=(cmd == "upgrade_plugin"),
        )
        if not ok:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": detail,
                "data": payload,
            }
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "accepted": True,
                "install_result": payload,
                "source_of_truth": "filesystem",
                "registry_role": "cache_only",
            },
        }

    return None
