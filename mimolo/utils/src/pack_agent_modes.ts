import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import semver from "semver";
import type {
  BuildManifest,
  ConflictReason,
  RepoVersion,
  SourceEntry,
  SourcesFile,
} from "./pack_agent_core.js";
import { formatDisplayPath, formatTimestamp, writeSourcesBackup } from "./pack_agent_cli_helpers.js";
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

export type ReleaseType = "major" | "minor" | "patch";
export type PrereleaseType = "alpha" | "beta" | "rc";

export type SourceListProcessOptions = {
  sourceListPath: string;
  out?: string;
  release?: ReleaseType;
  prerelease?: PrereleaseType;
  verifyExisting: boolean;
  forcePack: boolean;
  sourcesCreated: boolean;
};

export function bumpVersion(
  current: string,
  release?: ReleaseType,
  prerelease?: PrereleaseType,
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

export async function processSourceList(options: SourceListProcessOptions): Promise<void> {
  const listPath = options.sourceListPath;
  const rawList = await fs.readFile(listPath, "utf8");
  const entries = await readSourcesFile(listPath);
  const updated: SourceEntry[] = entries.map((entry) => ({ ...entry }));
  const listDir = path.dirname(listPath);
  let updatedSources = false;
  let hadErrors = false;
  let errorCount = 0;
  let packedCount = 0;
  let skippedCount = 0;
  const conflicts: Array<{
    id: string;
    path: string;
    buildManifest: string;
    sourceList: string;
    repo: RepoVersion;
    reason: ConflictReason;
  }> = [];
  const hasBump = Boolean(options.release || options.prerelease);
  const verifyExisting = options.verifyExisting;
  const forcePack = options.forcePack;
  const sourcesCreated = options.sourcesCreated;
  console.log("building agent packs:");

  for (let i = 0; i < updated.length; i += 1) {
    const entry = updated[i];
    const agentDir = path.resolve(listDir, entry.path);
    try {
      const stat = await fs.stat(agentDir);
      if (!stat.isDirectory()) {
        throw new Error("path is not a directory");
      }
    } catch {
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
        `    [${entry.id}] failed to read build-manifest.toml: ${(err as Error).message}`,
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
    const buildVersion = bumpVersion(baseVersion, options.release, options.prerelease);
    const outDir = resolveOutDir(agentDir, options.out);
    let repoVer: RepoVersion | null = null;

    try {
      repoVer = await findHighestRepoVersion(outDir, bm.plugin_id);
    } catch (err) {
      console.error(`    [${entry.id}] failed to read repository: ${(err as Error).message}`);
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
          reason: "repo-newer",
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
            reason: "repo-exists-bump",
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
                reason: "hash-mismatch",
              });
              hadErrors = true;
              errorCount += 1;
              continue;
            }
            console.log(
              `    [${entry.id}] ${repoVer.version} already exists in repository (verified, skipped)`,
            );
            skippedCount += 1;
            continue;
          }
          console.log(
            `    [${entry.id}] ${repoVer.version} already exists in repository (skipped, assumed current revision)`,
          );
          skippedCount += 1;
          continue;
        }

        if (forcePack) {
          console.log(
            `    [${entry.id}] ${repoVer.version} exists in repository (force-pack overwriting)`,
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

    console.log(`    [${entry.id}] packed ${bmForBuild.plugin_id} v${bmForBuild.version} (packed)`);
    packedCount += 1;
    if (entry.ver !== bmForBuild.version) {
      entry.ver = bmForBuild.version;
      updatedSources = true;
    }
  }

  if (updatedSources) {
    const backupPath = await writeSourcesBackup(listPath, rawList);
    await fs.writeFile(listPath, JSON.stringify({ sources: updated }, null, 2) + "\n", "utf8");
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
      console.log(
        `        build-manifest.toml: v${conflict.buildManifest} (${formatDisplayPath(manifestPath)})`,
      );
      console.log(`        sources.json: v${conflict.sourceList} (${formatDisplayPath(listPath)})`);
      console.log(`        repository: v${conflict.repo.version} (${formatDisplayPath(conflict.repo.path)})`);
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
  const sourceListStatus = sourcesCreated ? "created" : updatedSources ? "updated" : "unchanged";
  console.log(
    `summary: packed ${packedCount}, skipped ${skippedCount}, errors ${errorCount}, source list ${sourceListStatus}`,
  );
  console.log("");
  if (skippedCount > 0) {
    console.log(
      "note: if you did not expect repo to be skipped, it is a good idea to periodically run the " +
        "--verify-existing flag to confirm the hashes of all current agents before public release to ensure " +
        "that the released artifact is the version that was expected. --force-pack can also be used but this " +
        "will overwrite artifacts and if you are not careful it is possible that a version mismatch could occur. " +
        "best to use --verify-existing unless you know what you're doing.",
    );
    console.log("");
  }
  console.log(`completed: ${formatTimestamp()}`);
  console.log("");

  if (hadErrors) {
    process.exitCode = 1;
  }
}

export async function createSourceListFromDir(agentRoot: string, force?: boolean): Promise<void> {
  const sourcesPath = path.join(agentRoot, "sources.json");
  try {
    await fs.access(sourcesPath);
    if (!force) {
      console.error(
        `sources.json already exists at ${formatDisplayPath(sourcesPath)} (use --force to overwrite)`,
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
        ver,
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
