import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { createInterface } from "node:readline/promises";
import semver from "semver";
import type {
  BuildManifest,
  ConflictReason,
  RepoVersion,
  SourceEntry,
  SourcesFile,
} from "./pack_agent_core.js";
import {
  formatDisplayPath,
  formatTimestamp,
  logSourcesSelection,
  readPackageVersion,
  resolveDefaultAgentsDir,
  resolveDefaultSourcesCandidates,
  writeSourcesBackup,
  writeSourcesVersioned,
} from "./pack_agent_cli_helpers.js";
import {
  findHighestRepoVersion,
  normalizeSemver,
  packZip,
  readBuildManifest,
  readSourcesFile,
  resolveOutDir,
  updateBuildManifest,
  verifyExistingArchive,
  writeManifest,
  writePayloadHashes,
} from "./pack_agent_core.js";

type ArgMap = {
  source?: string;
  sourceList?: string;
  createSourceList?: boolean;
  force?: boolean;
  forcePack?: boolean;
  verifyExisting?: boolean;
  help?: boolean;
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
    if (arg === "--help" || arg === "-h") {
      args.help = true;
      continue;
    }
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
    } else if (arg === "--force-pack") {
      args.forcePack = true;
    } else if (arg === "--verify-existing") {
      args.verifyExisting = true;
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

function printHelp(): void {
  console.log("");
  console.log("pack-agent");
  console.log("");
  console.log("usage:");
  console.log(
    "  pack-agent --source <agent_dir> | --source-list <sources.json> [--out <out_dir>]"
  );
  console.log(
    "           [--major|--minor|--patch] [--alpha|--beta|--rc] [--verify-existing] [--force-pack]"
  );
  console.log("  pack-agent --source <agents_dir> --create-source-list [--force]");
  console.log("");
  console.log("options:");
  console.log("  --source <agent_dir>         Pack a single agent directory");
  console.log("  --source-list <sources.json> Pack multiple agents from a sources list");
  console.log("  --create-source-list         Generate sources.json from an agents directory");
  console.log("  --out <out_dir>              Output directory for packed zips");
  console.log("  --major|--minor|--patch       Bump version (mutually exclusive)");
  console.log("  --alpha|--beta|--rc           Prerelease bump (mutually exclusive)");
  console.log("  --verify-existing             Hash-verify if desired version already exists");
  console.log("  --force-pack                  Overwrite existing artifact for same version");
  console.log("  --force                       Overwrite existing sources.json when creating");
  console.log("  --silent                      Auto-accept prompts when creating sources.json");
  console.log("  --help, -h                    Show this help");
  console.log("");
  console.log("notes:");
  console.log("  - If a version bump is requested and the desired version already exists,");
  console.log("    pack-agent will fail that agent unless --force-pack is used.");
  console.log("  - If no bump is requested and the desired version exists, pack-agent will");
  console.log("    skip by default, or verify hashes with --verify-existing.");
  console.log("");
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
    reason: ConflictReason;
  }> = [];
  const hasBump = Boolean(args.release || args.prerelease);
  const verifyExisting = Boolean(args.verifyExisting);
  const forcePack = Boolean(args.forcePack);
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

    if (repoVer) {
      if (semver.gt(repoVer.version, buildVersion)) {
        conflicts.push({
          id: entry.id,
          path: entry.path,
          buildManifest: bm.version,
          sourceList: sourceVer,
          repo: repoVer,
          reason: "repo-newer"
        });
        hadErrors = true;
        errorCount += 1;
        continue;
      }

      if (semver.eq(repoVer.version, buildVersion)) {
        if (hasBump && !forcePack) {
          conflicts.push({
            id: entry.id,
            path: entry.path,
            buildManifest: bm.version,
            sourceList: sourceVer,
            repo: repoVer,
            reason: "repo-exists-bump"
          });
          hadErrors = true;
          errorCount += 1;
          continue;
        }

        if (!hasBump && !forcePack) {
          if (verifyExisting) {
            const bmForBuild: BuildManifest = { ...bm, version: buildVersion };
            const matches = await verifyExistingArchive(agentDir, bmForBuild, repoVer.path);
            if (!matches) {
              conflicts.push({
                id: entry.id,
                path: entry.path,
                buildManifest: bm.version,
                sourceList: sourceVer,
                repo: repoVer,
                reason: "hash-mismatch"
              });
              hadErrors = true;
              errorCount += 1;
              continue;
            }
            console.log(
              `    [${entry.id}] ${repoVer.version} already exists in repository (verified, skipped)`
            );
            skippedCount += 1;
            continue;
          }
          console.log(
            `    [${entry.id}] ${repoVer.version} already exists in repository (skipped, assumed current revision)`
          );
          skippedCount += 1;
          continue;
        }

        if (forcePack) {
          console.log(
            `    [${entry.id}] ${repoVer.version} exists in repository (force-pack overwriting)`
          );
        }
      }
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
      let message: string;
      if (conflict.reason === "repo-exists-bump") {
        message =
          `something's not write, you requested a version bump but output ` +
          `(v${conflict.repo.version}) already exists. Resolve this manually before packing can continue.`;
      } else if (conflict.reason === "hash-mismatch") {
        message =
          `something's not write, repository output (v${conflict.repo.version}) does not ` +
          `match current sources for the same version. Resolve this manually before packing can continue.`;
      } else {
        message =
          `something's not write, you have output (v${conflict.repo.version}) that supersedes ` +
          `the build-manifest.toml (v${conflict.buildManifest}) and the sources.json ` +
          `(v${conflict.sourceList}). Resolve this manually before packing can continue.`;
      }
      console.log(`        message: ${message}`);
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
  if (skippedCount > 0) {
    console.log(
      "note: if you did not expect repo to be skipped, it is a good idea to periodically run the " +
      "--verify-existing flag to confirm the hashes of all current agents before public release to ensure " +
      "that the released artifact is the version that was expected. --force-pack can also be used but this " +
      "will overwrite artifacts and if you are not careful it is possible that a version mismatch could occur. " +
      "best to use --verify-existing unless you know what you're doing."
    );
    console.log("");
  }
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
  if (args.help) {
    printHelp();
    return;
  }
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
      "usage: pack-agent --source <agent_dir> | --source-list <sources.json> [--out <out_dir>] [--major|--minor|--patch] [--alpha|--beta|--rc] [--verify-existing] [--force-pack]"
    );
    process.exit(1);
  }

  const agentDir = path.resolve(args.source);
  // Default output is ../repository relative to the source agent folder.
  const outDir = resolveOutDir(agentDir, args.out);

  const bm = await readBuildManifest(agentDir);
  const hasBump = Boolean(args.release || args.prerelease);
  const verifyExisting = Boolean(args.verifyExisting);
  const forcePack = Boolean(args.forcePack);
  const desiredVersion = bumpVersion(bm.version, args.release, args.prerelease);
  let skipped = false;

  let repoVer: RepoVersion | null = null;
  try {
    repoVer = await findHighestRepoVersion(outDir, bm.plugin_id);
  } catch (err) {
    console.error(`failed to read repository: ${(err as Error).message}`);
    process.exit(1);
  }

  if (repoVer) {
    if (semver.gt(repoVer.version, desiredVersion)) {
      console.log("");
      console.log("conflicts:");
      console.log(`    [${bm.plugin_id}]`);
      console.log(
        `        build-manifest.toml: v${bm.version} (${formatDisplayPath(
          path.join(agentDir, "build-manifest.toml")
        )})`
      );
      console.log(
        `        repository: v${repoVer.version} (${formatDisplayPath(repoVer.path)})`
      );
      console.log(
        `        message: something's not write, you have output (v${repoVer.version}) that supersedes the build-manifest.toml (v${bm.version}). Resolve this manually before packing can continue.`
      );
      console.log("");
      process.exitCode = 1;
      return;
    }

    if (semver.eq(repoVer.version, desiredVersion)) {
      if (hasBump && !forcePack) {
        console.log("");
        console.log("conflicts:");
        console.log(`    [${bm.plugin_id}]`);
        console.log(
          `        build-manifest.toml: v${bm.version} (${formatDisplayPath(
            path.join(agentDir, "build-manifest.toml")
          )})`
        );
        console.log(
          `        repository: v${repoVer.version} (${formatDisplayPath(repoVer.path)})`
        );
        console.log(
          `        message: something's not write, you requested a version bump but output (v${repoVer.version}) already exists. Resolve this manually before packing can continue.`
        );
        console.log("");
        process.exitCode = 1;
        return;
      }

      if (!hasBump && !forcePack) {
        if (verifyExisting) {
          const bmForBuild: BuildManifest = { ...bm, version: desiredVersion };
          const matches = await verifyExistingArchive(agentDir, bmForBuild, repoVer.path);
          if (!matches) {
            console.log("");
            console.log("conflicts:");
            console.log(`    [${bm.plugin_id}]`);
            console.log(
              `        build-manifest.toml: v${bm.version} (${formatDisplayPath(
                path.join(agentDir, "build-manifest.toml")
              )})`
            );
            console.log(
              `        repository: v${repoVer.version} (${formatDisplayPath(repoVer.path)})`
            );
            console.log(
              `        message: something's not write, repository output (v${repoVer.version}) does not match current sources for the same version. Resolve this manually before packing can continue.`
            );
            console.log("");
            process.exitCode = 1;
            return;
          }
          console.log(
            `skipped: ${repoVer.version} already exists in repository (verified, assumed current revision)`
          );
          skipped = true;
        } else {
          console.log(
            `skipped: ${repoVer.version} already exists in repository (assumed current revision)`
          );
          skipped = true;
        }
      }

      if (forcePack) {
        console.log(
          `${repoVer.version} exists in repository (force-pack overwriting)`
        );
      }
    }
  }

  if (skipped) {
    console.log("");
    console.log(
      "note: if you did not expect repo to be skipped, it is a good idea to periodically run the " +
      "--verify-existing flag to confirm the hashes of all current agents before public release to ensure " +
      "that the released artifact is the version that was expected. --force-pack can also be used but this " +
      "will overwrite artifacts and if you are not careful it is possible that a version mismatch could occur. " +
      "best to use --verify-existing unless you know what you're doing."
    );
    console.log("");
    return;
  }

  if (bm.version !== desiredVersion) {
    bm.version = desiredVersion;
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
