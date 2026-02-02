import archiver from "archiver";
import { createWriteStream, promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { createInterface } from "node:readline/promises";
import { fileURLToPath } from "node:url";
import toml from "toml";
import semver from "semver";

type ParamSpec = {
  name: string;
  type: string;
  required: boolean;
};

type BuildManifest = {
  plugin_id: string;
  name: string;
  version: string;
  entry: string;
  files: string[];
  params?: ParamSpec[];
};

type SourceEntry = {
  id: string;
  path: string;
  ver: string;
};

type SourcesFile = {
  sources: SourceEntry[];
};

async function readBuildManifest(agentDir: string): Promise<BuildManifest> {
  const manifestPath = path.join(agentDir, "build-manifest.toml");
  const raw = await fs.readFile(manifestPath, "utf8");
  const data = toml.parse(raw) as BuildManifest;
  if (!data.plugin_id || !data.name || !data.version || !data.entry || !data.files) {
    throw new Error("build-manifest.toml missing required fields");
  }
  return data;
}

async function hashFile(absPath: string): Promise<string> {
  const buf = await fs.readFile(absPath);
  return createHash("sha256").update(buf).digest("hex");
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeSemver(raw: string, label: string): string {
  const trimmed = raw.trim();
  const valid = semver.valid(trimmed);
  if (!valid || semver.clean(trimmed) !== trimmed) {
    throw new Error(`${label} must be strict semver (e.g. 1.2.3), got: ${raw}`);
  }
  return trimmed;
}

async function readSourcesFile(listPath: string): Promise<SourceEntry[]> {
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
      ver: entry.ver.trim()
    };
  });
}

type RepoVersion = {
  version: string;
  path: string;
};

async function findHighestRepoVersion(
  outDir: string,
  pluginId: string
): Promise<RepoVersion | null> {
  try {
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
  } catch (err) {
    const error = err as NodeJS.ErrnoException;
    if (error.code === "ENOENT") {
      return null;
    }
    throw err;
  }
}

function resolveOutDir(agentDir: string, out?: string): string {
  const outDirRaw = out ?? path.join(agentDir, "..", "repository");
  return path.isAbsolute(outDirRaw) ? outDirRaw : path.resolve(agentDir, outDirRaw);
}

async function writeManifest(outDir: string, bm: BuildManifest): Promise<string> {
  const manifest = {
    plugin_id: bm.plugin_id,
    name: bm.name,
    version: bm.version,
    entry: bm.entry,
    params: bm.params ?? []
  };
  const outPath = path.join(outDir, "manifest.json");
  await fs.writeFile(outPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  return outPath;
}

function formatTomlString(value: string): string {
  const escaped = value.replace(/\\/g, "\\\\").replace(/\"/g, '\\"');
  return `"${escaped}"`;
}

function formatTomlStringArray(values: string[]): string {
  return `[${values.map((v) => formatTomlString(v)).join(", ")}]`;
}

function replaceTomlKey(raw: string, key: string, value: string): string {
  const pattern = new RegExp(`^\\s*${key}\\s*=.*$`, "m");
  const line = `${key} = ${value}`;
  if (pattern.test(raw)) {
    return raw.replace(pattern, line);
  }
  const trimmed = raw.trimEnd();
  return `${trimmed}\n${line}\n`;
}

async function updateBuildManifest(agentDir: string, bm: BuildManifest): Promise<void> {
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

async function writePayloadHashes(
  agentDir: string,
  outDir: string,
  bm: BuildManifest
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
    files: hashes
  };

  const outPath = path.join(outDir, "payload_hashes.json");
  await fs.writeFile(outPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  return outPath;
}

async function packZip(
  agentDir: string,
  bm: BuildManifest,
  outDir: string,
  manifestPath: string,
  hashesPath: string
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

type ArgMap = {
  source?: string;
  sourceList?: string;
  createSourceList?: boolean;
  force?: boolean;
  silent?: boolean;
  sourcesCreated?: boolean;
  out?: string;
  release?: "major" | "minor" | "patch";
  prerelease?: "alpha" | "beta" | "rc";
};

function parseArgs(argv: string[]): ArgMap {
  const args: ArgMap = {};
  const releaseFlags: string[] = [];
  const prereleaseFlags: string[] = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--source") {
      args.source = argv[i + 1];
      i += 1;
    } else if (arg === "--source-list") {
      args.sourceList = argv[i + 1];
      i += 1;
    } else if (arg === "--create-source-list") {
      args.createSourceList = true;
    } else if (arg === "--force") {
      args.force = true;
    } else if (arg === "--silent") {
      args.silent = true;
    } else if (arg === "--out") {
      args.out = argv[i + 1];
      i += 1;
    } else if (arg === "--major") {
      args.release = "major";
      releaseFlags.push(arg);
    } else if (arg === "--minor") {
      args.release = "minor";
      releaseFlags.push(arg);
    } else if (arg === "--patch") {
      args.release = "patch";
      releaseFlags.push(arg);
    } else if (arg === "--alpha") {
      args.prerelease = "alpha";
      prereleaseFlags.push(arg);
    } else if (arg === "--beta") {
      args.prerelease = "beta";
      prereleaseFlags.push(arg);
    } else if (arg === "--rc") {
      args.prerelease = "rc";
      prereleaseFlags.push(arg);
    }
  }
  if (releaseFlags.length > 1) {
    throw new Error(`release flags are mutually exclusive: ${releaseFlags.join(", ")}`);
  }
  if (prereleaseFlags.length > 1) {
    throw new Error(`prerelease flags are mutually exclusive: ${prereleaseFlags.join(", ")}`);
  }
  return args;
}

function bumpVersion(
  current: string,
  release: ArgMap["release"],
  prerelease: ArgMap["prerelease"]
): string {
  if (release && prerelease) {
    const preKey =
      release === "major" ? "premajor" : release === "minor" ? "preminor" : "prepatch";
    return semver.inc(current, preKey, prerelease) ?? current;
  }
  if (release) {
    return semver.inc(current, release) ?? current;
  }
  if (prerelease) {
    return semver.inc(current, "prerelease", prerelease) ?? current;
  }
  return current;
}

function formatDisplayPath(targetPath: string): string {
  const rel = path.relative(process.cwd(), targetPath);
  if (!rel) {
    return ".";
  }
  if (!rel.startsWith(".") && !rel.startsWith("..")) {
    return `./${rel}`;
  }
  return rel;
}

function formatTimestamp(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

async function readPackageVersion(): Promise<string> {
  try {
    const moduleDir = path.dirname(fileURLToPath(import.meta.url));
    const pkgPath = path.resolve(moduleDir, "..", "package.json");
    const raw = await fs.readFile(pkgPath, "utf8");
    const data = JSON.parse(raw) as { version?: string };
    return typeof data.version === "string" ? data.version : "unknown";
  } catch {
    return "unknown";
  }
}

async function resolveDefaultSourcesCandidates(): Promise<string[]> {
  const candidates: string[] = [];
  const localList = path.resolve(process.cwd(), "sources.json");
  try {
    await fs.access(localList);
    candidates.push(localList);
  } catch {
    // try agents/sources.json relative to cwd
  }
  const agentsList = path.resolve(process.cwd(), "..", "agents", "sources.json");
  try {
    await fs.access(agentsList);
    candidates.push(agentsList);
  } catch {
    return candidates;
  }
  return candidates;
}

async function resolveDefaultAgentsDir(): Promise<string | null> {
  const agentsDir = path.resolve(process.cwd(), "..", "agents");
  try {
    const stat = await fs.stat(agentsDir);
    return stat.isDirectory() ? agentsDir : null;
  } catch {
    return null;
  }
}

async function confirmAutoCreate(agentsDir: string, silent?: boolean): Promise<boolean> {
  if (silent) {
    console.log("");
    console.log("auto-creating sources.json");
    console.log("");
    console.log("from:");
    console.log(`    ${formatDisplayPath(agentsDir)} (--silent)`);
    return true;
  }
  const rl = createInterface({
    input: process.stdin,
    output: process.stdout
  });
  try {
    const answer = await rl.question(
      `sources.json not found. Create one from ${formatDisplayPath(agentsDir)}? (y/N) `
    );
    const normalized = answer.trim().toLowerCase();
    const ok = normalized === "y" || normalized === "yes";
    if (ok) {
      console.log("");
      console.log("auto-creating sources.json");
      console.log("");
      console.log("from:");
      console.log(`    ${formatDisplayPath(agentsDir)}`);
    } else {
      console.log("aborting (no sources.json created)");
    }
    return ok;
  } finally {
    rl.close();
  }
}

function logSourcesSelection(selected: string, candidates?: string[]): void {
  if (candidates && candidates.length > 1) {
    console.log("");
    console.log("found sources:");
    for (const candidate of candidates) {
      const marker = candidate === selected ? "* " : "  ";
      console.log(`    ${marker}${formatDisplayPath(candidate)}`);
    }
  }
  console.log("");
  console.log("using sources:");
  console.log(`    ${formatDisplayPath(selected)}`);
}

function nextSourcesVersionLabel(existing: string[]): string {
  let max = 0;
  for (const name of existing) {
    const match = name.match(/^sources-v(\d{4})\.json$/);
    if (!match) {
      continue;
    }
    const value = Number.parseInt(match[1], 10);
    if (value > max) {
      max = value;
    }
  }
  const next = max + 1;
  return `sources-v${String(next).padStart(4, "0")}.json`;
}

async function writeSourcesVersioned(
  listPath: string,
  sources: SourceEntry[]
): Promise<string> {
  const dir = path.dirname(listPath);
  const files = await fs.readdir(dir);
  const name = nextSourcesVersionLabel(files);
  const outPath = path.join(dir, name);
  const payload: SourcesFile = { sources };
  await fs.writeFile(outPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  return outPath;
}

async function writeSourcesBackup(listPath: string, raw: string): Promise<string> {
  const dir = path.dirname(listPath);
  const files = await fs.readdir(dir);
  const name = nextSourcesVersionLabel(files);
  const outPath = path.join(dir, name);
  await fs.writeFile(outPath, raw, "utf8");
  return outPath;
}

async function processSourceList(args: ArgMap): Promise<void> {
  const listPath = args.sourceList ? path.resolve(args.sourceList) : "";
  const rawList = await fs.readFile(listPath, "utf8");
  const entries = await readSourcesFile(listPath);
  const updated: SourceEntry[] = entries.map((entry) => ({ ...entry }));
  const listDir = path.dirname(listPath);
  let updatedSources = false;
  let hadErrors = false;
  let errorCount = 0;
  let packedCount = 0;
  let skippedCount = 0;
  let backupWritten = false;
  const conflicts: Array<{
    id: string;
    path: string;
    buildManifest: string;
    sourceList: string;
    repo: RepoVersion;
  }> = [];
  const hasBump = Boolean(args.release || args.prerelease);
  const sourcesCreated = args.sourcesCreated ?? false;
  console.log("building agent packs:");

  for (let i = 0; i < updated.length; i += 1) {
    const entry = updated[i];
    const agentDir = path.resolve(listDir, entry.path);
    try {
      const stat = await fs.stat(agentDir);
      if (!stat.isDirectory()) {
        throw new Error("path is not a directory");
      }
    } catch (err) {
      console.error(`    [${entry.id}] missing path: ${formatDisplayPath(agentDir)}`);
      hadErrors = true;
      errorCount += 1;
      continue;
    }

    let bm: BuildManifest;
    try {
      bm = await readBuildManifest(agentDir);
    } catch (err) {
      console.error(
        `    [${entry.id}] failed to read build-manifest.toml: ${(err as Error).message}`
      );
      hadErrors = true;
      errorCount += 1;
      continue;
    }

    let sourceVer: string;
    let bmVer: string;
    try {
      sourceVer = normalizeSemver(entry.ver, `${entry.id} sources.ver`);
      bmVer = normalizeSemver(bm.version, `${entry.id} build-manifest.toml version`);
    } catch (err) {
      console.error(`    [${entry.id}] ${(err as Error).message}`);
      hadErrors = true;
      errorCount += 1;
      continue;
    }

    const baseVersion = semver.gte(bmVer, sourceVer) ? bmVer : sourceVer;
    const buildVersion = bumpVersion(baseVersion, args.release, args.prerelease);
    const outDir = resolveOutDir(agentDir, args.out);
    let repoVer: RepoVersion | null = null;

    try {
      repoVer = await findHighestRepoVersion(outDir, bm.plugin_id);
    } catch (err) {
      console.error(
        `    [${entry.id}] failed to read repository: ${(err as Error).message}`
      );
      hadErrors = true;
      errorCount += 1;
      continue;
    }

    if (
      repoVer
      && (semver.gt(repoVer.version, buildVersion)
        || (hasBump && semver.gte(repoVer.version, buildVersion)))
    ) {
      conflicts.push({
        id: entry.id,
        path: entry.path,
        buildManifest: bm.version,
        sourceList: sourceVer,
        repo: repoVer
      });
      hadErrors = true;
      errorCount += 1;
      continue;
    }

    if (repoVer && semver.gte(repoVer.version, buildVersion)) {
      console.log(`    [${entry.id}] ${repoVer.version} already exists in repository (skipped)`);
      skippedCount += 1;
      continue;
    }

    if (entry.ver !== buildVersion) {
      entry.ver = buildVersion;
      updatedSources = true;
    }

    if (bm.version !== buildVersion) {
      await updateBuildManifest(agentDir, { ...bm, version: buildVersion });
    }

    await fs.mkdir(outDir, { recursive: true });

    const bmForBuild: BuildManifest = { ...bm, version: buildVersion };

    const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "mimolo-pack-"));
    try {
      const manifestPath = await writeManifest(tmpDir, bmForBuild);
      const hashesPath = await writePayloadHashes(agentDir, tmpDir, bmForBuild);
      await packZip(agentDir, bmForBuild, outDir, manifestPath, hashesPath);
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }

    console.log(
      `    [${entry.id}] packed ${bmForBuild.plugin_id} v${bmForBuild.version} (packed)`
    );
    packedCount += 1;
    if (entry.ver !== bmForBuild.version) {
      entry.ver = bmForBuild.version;
      updatedSources = true;
    }
  }

  if (updatedSources) {
    const backupPath = await writeSourcesBackup(listPath, rawList);
    await fs.writeFile(listPath, JSON.stringify({ sources: updated }, null, 2) + "\n", "utf8");
    backupWritten = true;
    console.log("");
    console.log("source list:");
    console.log(`    updated sources list -> ${formatDisplayPath(listPath)}`);
    console.log(`    backup sources list -> ${formatDisplayPath(backupPath)}`);
  }

  if (conflicts.length > 0) {
    console.log("");
    console.log("conflicts:");
    for (const conflict of conflicts) {
      const agentDir = path.resolve(listDir, conflict.path);
      const manifestPath = path.join(agentDir, "build-manifest.toml");
      console.log(`    [${conflict.id}]`);
      console.log(`        build-manifest.toml: v${conflict.buildManifest} (${formatDisplayPath(manifestPath)})`);
      console.log(`        sources.json: v${conflict.sourceList} (${formatDisplayPath(listPath)})`);
      console.log(
        `        repository: v${conflict.repo.version} (${formatDisplayPath(conflict.repo.path)})`
      );
      console.log(
        `        message: something's not write, you have output (v${conflict.repo.version}) that supersedes the build-manifest.toml (v${conflict.buildManifest}) and the sources.json (v${conflict.sourceList}). Resolve this manually before packing can continue.`
      );
      console.log("");
    }
  }

  console.log("");
  const sourceListStatus = sourcesCreated
    ? "created"
    : updatedSources
      ? "updated"
      : "unchanged";
  console.log(
    `summary: packed ${packedCount}, skipped ${skippedCount}, errors ${errorCount}, source list ${sourceListStatus}`
  );
  console.log("");
  console.log(`completed: ${formatTimestamp()}`);
  console.log("");
  
  if (hadErrors) {
    process.exitCode = 1;
  }
}

async function createSourceListFromDir(agentRoot: string, force?: boolean): Promise<void> {
  const sourcesPath = path.join(agentRoot, "sources.json");
  try {
    await fs.access(sourcesPath);
    if (!force) {
      console.error(
        `sources.json already exists at ${formatDisplayPath(
          sourcesPath
        )} (use --force to overwrite)`
      );
      process.exitCode = 1;
      return;
    }
  } catch {
    // OK - file does not exist.
  }

  const items = await fs.readdir(agentRoot, { withFileTypes: true });
  const sources: SourceEntry[] = [];

  for (const item of items) {
    if (!item.isDirectory()) {
      continue;
    }
    const agentDir = path.join(agentRoot, item.name);
    const manifestPath = path.join(agentDir, "build-manifest.toml");
    try {
      await fs.access(manifestPath);
    } catch {
      continue;
    }

    try {
      const bm = await readBuildManifest(agentDir);
      const ver = normalizeSemver(bm.version, `${item.name} build-manifest.toml version`);
      sources.push({
        id: item.name,
        path: item.name,
        ver
      });
    } catch (err) {
      console.error(`[${item.name}] ${(err as Error).message}`);
      process.exitCode = 1;
    }
  }

  const payload: SourcesFile = { sources };
  await fs.writeFile(sourcesPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  console.log("");
  console.log("created:");
  console.log(`    ${formatDisplayPath(sourcesPath)}`);
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  let defaultCandidates: string[] | undefined;
  if (args.sourceList && args.createSourceList) {
    console.error("use either --source-list or --create-source-list, not both");
    process.exit(1);
  }
  if (args.source && args.sourceList) {
    console.error("use either --source or --source-list, not both");
    process.exit(1);
  }
  const version = await readPackageVersion();
  console.log("");
  console.log(`Pack Agent v${version}`);
  console.log(`started: ${formatTimestamp()}`);
  console.log("");
  if (!args.source && !args.sourceList && !args.createSourceList) {
    defaultCandidates = await resolveDefaultSourcesCandidates();
    if (defaultCandidates.length > 0) {
      args.sourceList = defaultCandidates[0];
    } else {
      const agentsDir = await resolveDefaultAgentsDir();
      if (agentsDir) {
        const confirmed = await confirmAutoCreate(agentsDir, args.silent);
        if (confirmed) {
          await createSourceListFromDir(agentsDir, false);
          const createdList = path.join(agentsDir, "sources.json");
          args.sourceList = createdList;
          args.sourcesCreated = true;
        }
      }
    }
  }
  if (args.createSourceList) {
    if (!args.source) {
      console.error("usage: pack-agent --source <agents_dir> --create-source-list");
      process.exit(1);
    }
    const agentRoot = path.resolve(args.source);
    await createSourceListFromDir(agentRoot, args.force);
    return;
  }
  if (args.sourceList) {
    logSourcesSelection(args.sourceList, defaultCandidates);
    await processSourceList(args);
    return;
  }

  if (!args.source) {
    console.error(
      "usage: pack-agent --source <agent_dir> | --source-list <sources.json> [--out <out_dir>] [--major|--minor|--patch] [--alpha|--beta|--rc]"
    );
    process.exit(1);
  }

  const agentDir = path.resolve(args.source);
  // Default output is ../repository relative to the source agent folder.
  const outDir = resolveOutDir(agentDir, args.out);

  const bm = await readBuildManifest(agentDir);
  if (args.release || args.prerelease) {
    bm.version = bumpVersion(bm.version, args.release, args.prerelease);
    await updateBuildManifest(agentDir, bm);
  }
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "mimolo-pack-"));
  try {
    const manifestPath = await writeManifest(tmpDir, bm);
    const hashesPath = await writePayloadHashes(agentDir, tmpDir, bm);
    await packZip(agentDir, bm, outDir, manifestPath, hashesPath);
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }

  console.log(`packed ${bm.plugin_id} v${bm.version}`);
}

void main();
