import { promises as fs } from "node:fs";
import path from "node:path";
import type { BuildManifest } from "./pack_agent_types.js";

export async function writeManifest(
  outDir: string,
  bm: BuildManifest,
): Promise<string> {
  const manifest = {
    plugin_id: bm.plugin_id,
    name: bm.name,
    version: bm.version,
    entry: bm.entry,
    params: bm.params ?? [],
  };
  const outPath = path.join(outDir, "manifest.json");
  await fs.writeFile(outPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  return outPath;
}

export function formatTomlString(value: string): string {
  const escaped = value.replace(/\\/g, "\\\\").replace(/\"/g, '\\"');
  return `"${escaped}"`;
}

export function formatTomlStringArray(values: string[]): string {
  return `[${values.map((v) => formatTomlString(v)).join(", ")}]`;
}

export function replaceTomlKey(raw: string, key: string, value: string): string {
  const pattern = new RegExp(`^\\s*${key}\\s*=.*$`, "m");
  const line = `${key} = ${value}`;
  if (pattern.test(raw)) {
    return raw.replace(pattern, line);
  }
  const trimmed = raw.trimEnd();
  return `${trimmed}\n${line}\n`;
}

export async function updateBuildManifest(
  agentDir: string,
  bm: BuildManifest,
): Promise<void> {
  const manifestPath = path.join(agentDir, "build-manifest.toml");
  const raw = await fs.readFile(manifestPath, "utf8");
  let updated = raw;
  updated = replaceTomlKey(updated, "plugin_id", formatTomlString(bm.plugin_id));
  updated = replaceTomlKey(updated, "name", formatTomlString(bm.name));
  updated = replaceTomlKey(updated, "version", formatTomlString(bm.version));
  updated = replaceTomlKey(updated, "entry", formatTomlString(bm.entry));
  updated = replaceTomlKey(updated, "files", formatTomlStringArray(bm.files));
  await fs.writeFile(manifestPath, updated, "utf8");
}
