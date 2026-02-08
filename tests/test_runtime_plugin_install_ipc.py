from __future__ import annotations

from pathlib import Path

from mimolo.core.config import Config
from mimolo.core.plugin_store import PluginStore
from mimolo.core.runtime import Runtime
from tests.helpers.plugin_archives import create_plugin_zip


def _runtime_with_store(tmp_path: Path) -> Runtime:
    runtime = Runtime(Config())
    runtime._plugin_store = PluginStore(tmp_path)
    return runtime


def test_list_installed_plugins_empty(tmp_path: Path) -> None:
    runtime = _runtime_with_store(tmp_path)
    response = runtime._build_ipc_response({"cmd": "list_installed_plugins"})
    assert response["ok"] is True
    assert response["cmd"] == "list_installed_plugins"
    data = response["data"]
    assert data["source_of_truth"] == "filesystem"
    assert data["registry_role"] == "cache_only"
    assert data["installed_plugins"] == []


def test_install_and_upgrade_plugin_via_ipc(tmp_path: Path) -> None:
    runtime = _runtime_with_store(tmp_path)
    zip_v1 = create_plugin_zip(tmp_path, "agent_example", "0.3.1")
    zip_v2 = create_plugin_zip(tmp_path, "agent_example", "0.3.2")

    install_response = runtime._build_ipc_response(
        {
            "cmd": "install_plugin",
            "plugin_class": "agents",
            "zip_path": str(zip_v1),
        }
    )
    assert install_response["ok"] is True
    install_data = install_response["data"]["install_result"]
    assert install_data["plugin_id"] == "agent_example"
    assert install_data["version"] == "0.3.1"

    downgrade_response = runtime._build_ipc_response(
        {
            "cmd": "upgrade_plugin",
            "plugin_class": "agents",
            "zip_path": str(zip_v1),
        }
    )
    assert downgrade_response["ok"] is False
    assert downgrade_response["error"] == "version_already_installed"

    upgrade_response = runtime._build_ipc_response(
        {
            "cmd": "upgrade_plugin",
            "plugin_class": "agents",
            "zip_path": str(zip_v2),
        }
    )
    assert upgrade_response["ok"] is True
    upgrade_data = upgrade_response["data"]["install_result"]
    assert upgrade_data["version"] == "0.3.2"


def test_inspect_plugin_archive_via_ipc(tmp_path: Path) -> None:
    runtime = _runtime_with_store(tmp_path)
    zip_v1 = create_plugin_zip(tmp_path, "screen_tracker", "0.1.1")

    response = runtime._build_ipc_response(
        {
            "cmd": "inspect_plugin_archive",
            "zip_path": str(zip_v1),
        }
    )
    assert response["ok"] is True
    inspection = response["data"]["inspection"]
    assert inspection["plugin_id"] == "screen_tracker"
    assert inspection["version"] == "0.1.1"
    assert inspection["suggested_plugin_class"] == "agents"
    assert inspection["suggested_action"] == "install"


def test_list_installed_plugins_invalid_class_returns_error(tmp_path: Path) -> None:
    runtime = _runtime_with_store(tmp_path)

    response = runtime._build_ipc_response(
        {"cmd": "list_installed_plugins", "plugin_class": "not_a_class"}
    )
    assert response["ok"] is False
    assert str(response["error"]).startswith("invalid_plugin_class:")


def test_inspect_plugin_archive_missing_zip_path_returns_error(tmp_path: Path) -> None:
    runtime = _runtime_with_store(tmp_path)

    response = runtime._build_ipc_response({"cmd": "inspect_plugin_archive"})
    assert response["ok"] is False
    assert response["error"] == "missing_zip_path"


def test_install_plugin_missing_zip_path_returns_error(tmp_path: Path) -> None:
    runtime = _runtime_with_store(tmp_path)

    response = runtime._build_ipc_response({"cmd": "install_plugin"})
    assert response["ok"] is False
    assert response["error"] == "missing_zip_path"


def test_install_plugin_rejects_invalid_plugin_class(tmp_path: Path) -> None:
    runtime = _runtime_with_store(tmp_path)
    archive = create_plugin_zip(tmp_path, "screen_tracker", "0.1.0")

    response = runtime._build_ipc_response(
        {
            "cmd": "install_plugin",
            "plugin_class": "invalid",
            "zip_path": str(archive),
        }
    )
    assert response["ok"] is False
    assert str(response["error"]).startswith("invalid_plugin_class:")
    assert response["data"] == {}


def test_upgrade_plugin_rejects_not_newer_version(tmp_path: Path) -> None:
    runtime = _runtime_with_store(tmp_path)
    archive_v2 = create_plugin_zip(tmp_path, "screen_tracker", "0.2.0")
    archive_v1 = create_plugin_zip(tmp_path, "screen_tracker", "0.1.9")

    install_response = runtime._build_ipc_response(
        {
            "cmd": "install_plugin",
            "plugin_class": "agents",
            "zip_path": str(archive_v2),
        }
    )
    assert install_response["ok"] is True

    downgrade_response = runtime._build_ipc_response(
        {
            "cmd": "upgrade_plugin",
            "plugin_class": "agents",
            "zip_path": str(archive_v1),
        }
    )
    assert downgrade_response["ok"] is False
    assert downgrade_response["error"] == "not_newer_than_installed"
    data = downgrade_response["data"]
    assert data["requested_version"] == "0.1.9"
    assert data["latest_installed_version"] == "0.2.0"


def test_inspect_plugin_archive_rejects_invalid_archive(tmp_path: Path) -> None:
    runtime = _runtime_with_store(tmp_path)
    invalid_archive = create_plugin_zip(
        tmp_path,
        "broken_plugin",
        "0.0.1",
        include_manifest=False,
    )

    response = runtime._build_ipc_response(
        {
            "cmd": "inspect_plugin_archive",
            "zip_path": str(invalid_archive),
        }
    )
    assert response["ok"] is False
    assert str(response["error"]).startswith("invalid_archive:")
