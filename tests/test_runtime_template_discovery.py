from __future__ import annotations

from pathlib import Path

from mimolo.core.config import Config
from mimolo.core.plugin_store import PluginStore
from mimolo.core.runtime import Runtime
from tests.helpers.plugin_archives import create_plugin_zip


def test_discover_agent_templates_includes_installed_plugins(tmp_path: Path) -> None:
    plugin_id = "installed_probe_agent"
    store = PluginStore(tmp_path)
    archive = create_plugin_zip(tmp_path, plugin_id, "0.1.0")
    ok, detail, _payload = store.install_plugin_archive(
        archive,
        "agents",
        require_newer=False,
    )
    assert ok is True
    assert detail == "installed"

    runtime = Runtime(Config())
    runtime._plugin_store = store

    templates = runtime._discover_agent_templates()
    assert plugin_id in templates
    template = templates[plugin_id]
    assert template["template_id"] == plugin_id
    assert isinstance(template["script"], str)

    default_cfg = template["default_config"]
    args = default_cfg["args"]
    assert args[0:2] == ["run", "python"]
    assert isinstance(args[2], str)
    assert Path(args[2]).name == f"{plugin_id}.py"
