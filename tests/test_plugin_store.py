from __future__ import annotations

from pathlib import Path

from mimolo.core.plugin_store import PluginStore
from tests.helpers.plugin_archives import create_plugin_zip


def test_install_and_list_plugins_filesystem_ground_truth(tmp_path: Path) -> None:
    store = PluginStore(tmp_path)
    archive = create_plugin_zip(tmp_path, "client_folder_activity", "0.1.0")

    ok, detail, payload = store.install_plugin_archive(
        archive,
        "agents",
        require_newer=False,
    )
    assert ok is True
    assert detail == "installed"
    assert payload["plugin_id"] == "client_folder_activity"
    assert payload["version"] == "0.1.0"

    listed = store.list_installed("agents")
    assert len(listed) == 1
    entry = listed[0]
    assert entry["plugin_class"] == "agents"
    assert entry["plugin_id"] == "client_folder_activity"
    assert entry["latest_version"] == "0.1.0"
    assert entry["latest_entry"] == "files/client_folder_activity.py"
    assert entry["versions"][0]["version"] == "0.1.0"


def test_upgrade_requires_newer_version(tmp_path: Path) -> None:
    store = PluginStore(tmp_path)
    v1_archive = create_plugin_zip(tmp_path, "screen_tracker", "0.1.0")
    v2_archive = create_plugin_zip(tmp_path, "screen_tracker", "0.1.1")

    ok, _, _ = store.install_plugin_archive(v1_archive, "agents", require_newer=False)
    assert ok is True

    ok_same, detail_same, payload_same = store.install_plugin_archive(
        v1_archive,
        "agents",
        require_newer=True,
    )
    assert ok_same is False
    assert detail_same == "version_already_installed"
    assert payload_same["version"] == "0.1.0"

    ok_newer, detail_newer, payload_newer = store.install_plugin_archive(
        v2_archive,
        "agents",
        require_newer=True,
    )
    assert ok_newer is True
    assert detail_newer == "installed"
    assert payload_newer["version"] == "0.1.1"


def test_invalid_plugin_class_rejected(tmp_path: Path) -> None:
    store = PluginStore(tmp_path)
    archive = create_plugin_zip(tmp_path, "agent_example", "0.3.1")

    ok, detail, payload = store.install_plugin_archive(
        archive,
        "invalid",
        require_newer=False,
    )
    assert ok is False
    assert detail.startswith("invalid_plugin_class:")
    assert payload == {}
