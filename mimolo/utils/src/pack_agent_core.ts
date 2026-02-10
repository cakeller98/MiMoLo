import archiver from "archiver";
import { createWriteStream, promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import toml from "toml";
import semver from "semver";

export type ParamSpec = {
  name: string;
  type: string;
  required: boolean;
};

export type BuildManifest = {
  plugin_id: string;
  name: string;
  version: string;
  entry: string;
  files: string[];
  params?: ParamSpec[];
};

export type SourceEntry = {
  id: string;
  path: string;
  ver: string;
};

export type SourcesFile = {
  sources: SourceEntry[];
};

export type ConflictReason = "repo-newer" | "repo-exists-bump" | "hash-mismatch";

export type RepoVersion = {
  version: string;
  path: string;
};

export async function readBuildManifest(agentDir: string): Promise<BuildManifest> {
  const manifestPath = path.join(agentDir, "build-manifest.toml");
  const raw = await fs.readFile(manifestPath, "utf8");
  const data = toml.parse(raw) as BuildManifest;
  if (!data.plugin_id || !data.name || !data.version || !data.entry || !data.files) {
    throw new Error("build-manifest.toml missing required fields");
  }
  return data;
}

export async function hashFile(absPath: string): Promise<string> {
  const buf = await fs.readFile(absPath);
  return createHash("sha256").update(buf).digest("hex");
}

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function normalizeSemver(raw: string, label: string): string {
  const trimmed = raw.trim();
  const valid = semver.valid(trimmed);
  if (!valid || semver.clean(trimmed) !== trimmed) {
    throw new Error(`${label} must be strict semver (e.g. 1.2.3), got: ${raw}`);
  }
  return trimmed;
}

export async function readSourcesFile(listPath: string): Promise<SourceEntry[]> {
  const raw = await fs.readFile(listPath, "utf8");
  const data = JSON.parse(raw) as SourcesFile;
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
  if (!stat.isDirectory()) {
    throw new Error(`repository path is not a directory: ${outDir}`);
  }
}

export function resolveOutDir(agentDir: string, out?: string): string {
  const outDirRaw = out ?? path.join(agentDir, "..", "repository");
  return path.isAbsolute(outDirRaw) ? outDirRaw : path.resolve(agentDir, outDirRaw);
}

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

export async function writePayloadHashes(
  agentDir: string,
  outDir: string,
  bm: BuildManifest,
): Promise<string> {
  const hashes: Record<string, string> = {};
  for (const rel of bm.files) {
    const abs = path.join(agentDir, rel);
    const key = path.posix.join("files", rel.replace(/\\/g, "/"));
    hashes[key] = await hashFile(abs);
  }

  const payload = {
    version: bm.version,
    hash_algo: "sha256",
    files: hashes,
  };

  const outPath = path.join(outDir, "payload_hashes.json");
  await fs.writeFile(outPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  return outPath;
}

export async function packZip(
  agentDir: string,
  bm: BuildManifest,
  outDir: string,
  manifestPath: string,
  hashesPath: string,
): Promise<void> {
  const zipName = `${bm.plugin_id}_v${bm.version}.zip`;
  const zipPath = path.join(outDir, zipName);
  const output = createWriteStream(zipPath);
  const archive = archiver("zip", { zlib: { level: 9 } });

  return new Promise((resolve, reject) => {
    output.on("close", resolve);
    output.on("error", reject);
    archive.on("error", reject);

    archive.pipe(output);

    const prefix = `${bm.plugin_id}/`;
    archive.file(manifestPath, { name: path.posix.join(prefix, "manifest.json") });
    archive.file(hashesPath, { name: path.posix.join(prefix, "payload_hashes.json") });

    for (const rel of bm.files) {
      const abs = path.join(agentDir, rel);
      const zipPathRel = path.posix.join(prefix, "files", rel.replace(/\\/g, "/"));
      archive.file(abs, { name: zipPathRel });
    }

    archive.finalize().catch(reject);
  });
}

export async function verifyExistingArchive(
  agentDir: string,
  bm: BuildManifest,
  repoZipPath: string,
): Promise<boolean> {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "mimolo-verify-"));
  try {
    const manifestPath = await writeManifest(tmpDir, bm);
    const hashesPath = await writePayloadHashes(agentDir, tmpDir, bm);
    await packZip(agentDir, bm, tmpDir, manifestPath, hashesPath);
    const tmpZip = path.join(tmpDir, `${bm.plugin_id}_v${bm.version}.zip`);
    const [repoHash, tmpHash] = await Promise.all([
      hashFile(repoZipPath),
      hashFile(tmpZip),
    ]);
    return repoHash === tmpHash;
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
}
