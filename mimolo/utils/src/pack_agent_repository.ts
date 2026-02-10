import { promises as fs } from "node:fs";
import path from "node:path";
import semver from "semver";
import type { RepoVersion } from "./pack_agent_types.js";

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export async function findHighestRepoVersion(
  outDir: string,
  pluginId: string,
): Promise<RepoVersion | null> {
  const items = await fs.readdir(outDir, { withFileTypes: true });
  const pattern = new RegExp(`^${escapeRegExp(pluginId)}_v(.+)\\.zip$`);
  const versions: RepoVersion[] = [];
  for (const item of items) {
    if (!item.isFile()) {
      continue;
    }
    const match = item.name.match(pattern);
    if (!match) {
      continue;
    }
    const ver = match[1];
    if (semver.valid(ver) && semver.clean(ver) === ver) {
      versions.push({ version: ver, path: path.join(outDir, item.name) });
    }
  }
  if (versions.length === 0) {
    return null;
  }
  versions.sort((a, b) => semver.rcompare(a.version, b.version));
  return versions[0];
}

export async function ensureRepoDir(outDir: string): Promise<void> {
  await fs.mkdir(outDir, { recursive: true });
  const stat = await fs.stat(outDir);
  // Directory type mismatch is an environment/setup fault and should stop execution.
  if (!stat.isDirectory()) {
    throw new Error(`repository path is not a directory: ${outDir}`);
  }
}

export function resolveOutDir(agentDir: string, out?: string): string {
  const outDirRaw = out ?? path.join(agentDir, "..", "repository");
  return path.isAbsolute(outDirRaw) ? outDirRaw : path.resolve(agentDir, outDirRaw);
}
