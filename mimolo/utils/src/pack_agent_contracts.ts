import { promises as fs } from "node:fs";
import path from "node:path";
import semver from "semver";
import toml from "toml";
import type { BuildManifest, SourceEntry, SourcesFile } from "./pack_agent_types.js";

export function normalizeSemver(raw: string, label: string): string {
  const trimmed = raw.trim();
  const valid = semver.valid(trimmed);
  // Version normalization is contract validation, not optional coercion.
  if (!valid || semver.clean(trimmed) !== trimmed) {
    throw new Error(`${label} must be strict semver (e.g. 1.2.3), got: ${raw}`);
  }
  return trimmed;
}

export async function readBuildManifest(agentDir: string): Promise<BuildManifest> {
  const manifestPath = path.join(agentDir, "build-manifest.toml");
  const raw = await fs.readFile(manifestPath, "utf8");
  const data = toml.parse(raw) as BuildManifest;
  // Manifest schema validity is a hard contract; invalid input must fail fast.
  if (!data.plugin_id || !data.name || !data.version || !data.entry || !data.files) {
    throw new Error("build-manifest.toml missing required fields");
  }
  return data;
}

export async function readSourcesFile(listPath: string): Promise<SourceEntry[]> {
  const raw = await fs.readFile(listPath, "utf8");
  const data = JSON.parse(raw) as SourcesFile;
  // Sources schema is ground-truth input for build mode and must be explicit.
  if (!data || !Array.isArray(data.sources)) {
    throw new Error("sources.json must be an object with a 'sources' array");
  }
  return data.sources.map((entry, index) => {
    if (!entry || typeof entry !== "object") {
      throw new Error(`sources[${index}] must be an object`);
    }
    if (typeof entry.id !== "string" || !entry.id.trim()) {
      throw new Error(`sources[${index}].id must be a non-empty string`);
    }
    if (typeof entry.path !== "string" || !entry.path.trim()) {
      throw new Error(`sources[${index}].path must be a non-empty string`);
    }
    if (typeof entry.ver !== "string" || !entry.ver.trim()) {
      throw new Error(`sources[${index}].ver must be a non-empty string`);
    }
    return {
      id: entry.id.trim(),
      path: entry.path.trim(),
      ver: entry.ver.trim(),
    };
  });
}
