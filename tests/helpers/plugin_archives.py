from __future__ import annotations

import json
import zipfile
from pathlib import Path


def create_plugin_zip(
    base_dir: Path,
    plugin_id: str,
    version: str,
    *,
    plugin_class: str | None = None,
    entry: str | None = None,
    include_manifest: bool = True,
    include_payload_hashes: bool = True,
    top_level_dir: str | None = None,
) -> Path:
    """Create a minimal plugin archive for install/inspection tests."""
    zip_path = base_dir / f"{plugin_id}_v{version}.zip"
    archive_root = top_level_dir or plugin_id
    entry_path = entry or f"files/{plugin_id}.py"

    manifest = {
        "plugin_id": plugin_id,
        "name": plugin_id.replace("_", " ").title(),
        "version": version,
        "entry": entry_path,
        "params": [],
    }
    if plugin_class is not None:
        manifest["plugin_class"] = plugin_class

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if include_manifest:
            archive.writestr(f"{archive_root}/manifest.json", json.dumps(manifest))
        if include_payload_hashes:
            archive.writestr(f"{archive_root}/payload_hashes.json", "{}")
        archive.writestr(f"{archive_root}/{entry_path}", "print('ok')\n")
    return zip_path

