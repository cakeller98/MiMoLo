"""Installed plugin storage and archive install helpers.

Filesystem contents are treated as ground truth. Any registry file is a
rebuildable convenience cache only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import tomlkit

from mimolo.common.paths import get_mimolo_data_dir

PluginClass = Literal["agents", "reporters", "widgets"]
PLUGIN_CLASSES: tuple[PluginClass, PluginClass, PluginClass] = (
    "agents",
    "reporters",
    "widgets",
)
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


@dataclass(frozen=True)
class ArchiveDescriptor:
    """Validated metadata loaded from a plugin archive."""

    entry: str
    plugin_class: PluginClass | None
    plugin_id: str
    top_level_dir: str
    version: str


class PluginStore:
    """Manage plugin install folders under the MiMoLo data root."""

    def __init__(self, data_root: Path | None = None) -> None:
        root = data_root if data_root is not None else get_mimolo_data_dir()
        self.data_root = root
        self.operations_root = root / "operations"
        self.plugins_root = self.operations_root / "plugins"
        self.staging_root = self.plugins_root / ".staging"
        self.registry_cache_path = self.plugins_root / "plugins_registry.toml"

    def list_installed(self, plugin_class: str | None = None) -> list[dict[str, Any]]:
        """List installed plugins by scanning the filesystem."""
        classes: list[PluginClass]
        if plugin_class is None or plugin_class == "all":
            classes = list(PLUGIN_CLASSES)
        else:
            classes = [self._coerce_plugin_class(plugin_class)]

        discovered: list[dict[str, Any]] = []
        for cls in classes:
            class_root = self.plugins_root / cls
            if not class_root.exists():
                continue
            for plugin_dir in sorted(class_root.iterdir(), key=lambda p: p.name):
                if not plugin_dir.is_dir():
                    continue
                versions: list[dict[str, Any]] = []
                for version_dir in sorted(plugin_dir.iterdir(), key=lambda p: p.name):
                    if not version_dir.is_dir():
                        continue
                    version = version_dir.name
                    manifest = self._read_installed_manifest(version_dir)
                    version_info: dict[str, Any] = {
                        "version": version,
                        "path": str(version_dir),
                    }
                    if manifest is not None:
                        version_info["entry"] = manifest.get("entry", "")
                    versions.append(version_info)

                if not versions:
                    continue
                versions.sort(key=lambda item: self._version_sort_key(str(item["version"])))
                latest = versions[-1]
                discovered.append(
                    {
                        "plugin_class": cls,
                        "plugin_id": plugin_dir.name,
                        "versions": versions,
                        "latest_version": str(latest["version"]),
                        "latest_path": str(latest["path"]),
                        "latest_entry": str(latest.get("entry", "")),
                    }
                )

        discovered.sort(key=lambda item: (str(item["plugin_class"]), str(item["plugin_id"])))
        return discovered

    def install_plugin_archive(
        self,
        zip_path: Path,
        plugin_class: str,
        *,
        require_newer: bool,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Install a plugin archive into versioned plugin storage."""
        try:
            cls = self._coerce_plugin_class(plugin_class)
        except ValueError as e:
            return False, str(e), {}

        if not zip_path.exists() or not zip_path.is_file():
            return False, "zip_not_found", {}

        try:
            descriptor = self._read_archive_descriptor(zip_path)
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            return False, f"invalid_archive:{e}", {}

        plugin_id = descriptor.plugin_id
        version = descriptor.version
        class_plugin_root = self.plugins_root / cls / plugin_id
        install_dir = class_plugin_root / version

        if install_dir.exists():
            return False, "version_already_installed", {
                "plugin_class": cls,
                "plugin_id": plugin_id,
                "version": version,
                "path": str(install_dir),
            }

        if require_newer:
            existing_versions = self._installed_versions_for_plugin(cls, plugin_id)
            if existing_versions:
                latest = max(existing_versions, key=self._version_sort_key)
                if self._compare_versions(version, latest) <= 0:
                    return False, "not_newer_than_installed", {
                        "plugin_class": cls,
                        "plugin_id": plugin_id,
                        "requested_version": version,
                        "latest_installed_version": latest,
                    }

        self.staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging_dir = self.staging_root / f"install_{uuid.uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False, mode=0o700)

        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                self._extract_archive_safely(archive, staging_dir)

            extracted_root = staging_dir / descriptor.top_level_dir
            if not extracted_root.exists() or not extracted_root.is_dir():
                return False, "archive_missing_root_folder", {
                    "expected_root": descriptor.top_level_dir,
                }

            class_plugin_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.replace(extracted_root, install_dir)
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            return False, f"install_failed:{e}", {}
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

        try:
            self.write_registry_cache()
        except OSError:
            # Registry is a rebuildable cache; install success is determined by filesystem state.
            pass

        return True, "installed", {
            "plugin_class": cls,
            "plugin_id": plugin_id,
            "version": version,
            "entry": descriptor.entry,
            "path": str(install_dir),
            "source_of_truth": "filesystem",
        }

    def inspect_plugin_archive(self, zip_path: Path) -> tuple[bool, str, dict[str, Any]]:
        """Inspect and validate a plugin archive without installing it."""
        if not zip_path.exists() or not zip_path.is_file():
            return False, "zip_not_found", {}

        try:
            descriptor = self._read_archive_descriptor(zip_path)
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            return False, f"invalid_archive:{e}", {}

        if descriptor.plugin_class is None:
            suggested_class: PluginClass = "agents"
            classification_source = "default_agents"
        else:
            suggested_class = descriptor.plugin_class
            classification_source = "manifest"

        installed_versions = self._installed_versions_for_plugin(
            suggested_class, descriptor.plugin_id
        )
        latest_installed_version = (
            installed_versions[-1] if installed_versions else None
        )
        suggested_action = "upgrade" if installed_versions else "install"

        return True, "validated", {
            "zip_path": str(zip_path),
            "plugin_id": descriptor.plugin_id,
            "version": descriptor.version,
            "entry": descriptor.entry,
            "top_level_dir": descriptor.top_level_dir,
            "manifest_plugin_class": descriptor.plugin_class,
            "suggested_plugin_class": suggested_class,
            "classification_source": classification_source,
            "allowed_plugin_classes": list(PLUGIN_CLASSES),
            "installed_versions_for_suggested_class": installed_versions,
            "latest_installed_version_for_suggested_class": latest_installed_version,
            "suggested_action": suggested_action,
            "source_of_truth": "filesystem",
            "registry_role": "cache_only",
        }

    def write_registry_cache(self) -> None:
        """Write convenience registry cache from current filesystem scan."""
        installed = self.list_installed()

        doc = tomlkit.document()
        doc["generated_at"] = datetime.now(UTC).isoformat()
        plugins_table = tomlkit.table()
        doc["plugins"] = plugins_table

        for cls in PLUGIN_CLASSES:
            class_table = tomlkit.table()
            class_entries = [
                entry for entry in installed if entry.get("plugin_class") == cls
            ]
            for entry in class_entries:
                plugin_table = tomlkit.table()
                versions = entry.get("versions", [])
                plugin_table["versions"] = [str(v.get("version", "")) for v in versions]
                plugin_table["latest_version"] = str(entry.get("latest_version", ""))
                plugin_table["latest_path"] = str(entry.get("latest_path", ""))
                class_table[str(entry.get("plugin_id", ""))] = plugin_table
            plugins_table[cls] = class_table

        self.registry_cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.registry_cache_path, "w", encoding="utf-8") as handle:
            handle.write(tomlkit.dumps(doc))

    def _coerce_plugin_class(self, raw: str) -> PluginClass:
        value = raw.strip().lower()
        if value not in PLUGIN_CLASSES:
            allowed = ", ".join(PLUGIN_CLASSES)
            raise ValueError(f"invalid_plugin_class:{value} (allowed: {allowed})")
        return cast(PluginClass, value)

    def _installed_versions_for_plugin(
        self, plugin_class: PluginClass, plugin_id: str
    ) -> list[str]:
        plugin_root = self.plugins_root / plugin_class / plugin_id
        if not plugin_root.exists() or not plugin_root.is_dir():
            return []
        versions = [
            entry.name for entry in plugin_root.iterdir() if entry.is_dir()
        ]
        versions.sort(key=self._version_sort_key)
        return versions

    def _read_installed_manifest(self, version_dir: Path) -> dict[str, Any] | None:
        manifest_path = version_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            with open(manifest_path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return raw if isinstance(raw, dict) else None

    def _read_archive_descriptor(self, zip_path: Path) -> ArchiveDescriptor:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive_entries = [name for name in archive.namelist() if name and not name.endswith("/")]
            if not archive_entries:
                raise ValueError("archive_empty")

            roots = {name.split("/", 1)[0] for name in archive_entries if "/" in name}
            if len(roots) != 1:
                raise ValueError("archive_must_have_single_top_level_folder")
            top_level = next(iter(roots))

            manifest_member = f"{top_level}/manifest.json"
            if manifest_member not in archive.namelist():
                raise ValueError("archive_missing_manifest")
            try:
                raw_manifest = json.loads(archive.read(manifest_member))
            except json.JSONDecodeError as e:
                raise ValueError(f"invalid_manifest_json:{e}") from e

        if not isinstance(raw_manifest, dict):
            raise ValueError("manifest_must_be_object")
        plugin_id_raw = raw_manifest.get("plugin_id")
        version_raw = raw_manifest.get("version")
        entry_raw = raw_manifest.get("entry")
        plugin_id = (
            str(plugin_id_raw).strip()
            if plugin_id_raw is not None and str(plugin_id_raw).strip()
            else ""
        )
        version = (
            str(version_raw).strip()
            if version_raw is not None and str(version_raw).strip()
            else ""
        )
        entry = (
            str(entry_raw).strip()
            if entry_raw is not None and str(entry_raw).strip()
            else ""
        )
        plugin_class_raw = raw_manifest.get("plugin_class")
        plugin_class_text = (
            str(plugin_class_raw).strip().lower()
            if plugin_class_raw is not None and str(plugin_class_raw).strip()
            else ""
        )
        plugin_class: PluginClass | None
        if not plugin_class_text:
            plugin_class = None
        elif plugin_class_text in PLUGIN_CLASSES:
            plugin_class = cast(PluginClass, plugin_class_text)
        else:
            raise ValueError(
                f"manifest_invalid_plugin_class:{plugin_class_text}"
            )

        if not plugin_id:
            raise ValueError("manifest_missing_plugin_id")
        if not version:
            raise ValueError("manifest_missing_version")
        if not entry:
            raise ValueError("manifest_missing_entry")
        if plugin_id != top_level:
            raise ValueError("manifest_plugin_id_must_match_zip_root")

        return ArchiveDescriptor(
            entry=entry,
            plugin_class=plugin_class,
            plugin_id=plugin_id,
            top_level_dir=top_level,
            version=version,
        )

    def _extract_archive_safely(
        self, archive: zipfile.ZipFile, destination: Path
    ) -> None:
        destination_abs = destination.resolve()
        for member in archive.infolist():
            member_path = member.filename
            if not member_path:
                continue
            member_parts = Path(member_path).parts
            if Path(member_path).is_absolute() or ".." in member_parts:
                raise ValueError(f"unsafe_archive_path:{member_path}")

            target_path = (destination / member_path).resolve()
            if not str(target_path).startswith(f"{destination_abs}{os.sep}") and target_path != destination_abs:
                raise ValueError(f"unsafe_archive_path:{member_path}")

            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.open(member, "r") as source, open(target_path, "wb") as sink:
                shutil.copyfileobj(source, sink)

    def _version_sort_key(self, version: str) -> tuple[int, int, int, int, str]:
        match = SEMVER_RE.match(version.strip())
        if not match:
            return (0, 0, 0, 0, version)
        return (1, int(match.group(1)), int(match.group(2)), int(match.group(3)), version)

    def _compare_versions(self, left: str, right: str) -> int:
        left_key = self._version_sort_key(left)
        right_key = self._version_sort_key(right)
        if left_key < right_key:
            return -1
        if left_key > right_key:
            return 1
        return 0
