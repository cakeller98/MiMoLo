import { existsSync, promises as fs } from "node:fs";
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
  ensureRepoDir,
  findHighestRepoVersion,
  normalizeSemver,
  readBuildManifest,
  readSourcesFile,
  resolveOutDir,
  updateBuildManifest,
  verifyExistingArchive,
} from "./pack_agent_core.js";
import { logRepoSkipNote, packAgentToRepo } from "./pack_agent_packing_helpers.js";
import type { PrereleaseType, ReleaseType } from "./pack_agent_versioning.js";
import { bumpVersion } from "./pack_agent_versioning.js";

export type SourceListProcessOptions = {
  sourceListPath: string;
  out?: string;
  release?: ReleaseType;
  prerelease?: PrereleaseType;
  verifyExisting: boolean;
  forcePack: boolean;
  sourcesCreated: boolean;
};

export type SourceListProcessResult = {
  hadErrors: boolean;
  errorCount: number;
  packedCount: number;
  skippedCount: number;
  sourceListStatus: "created" | "updated" | "unchanged";
};

export type CreateSourceListResult = {
  created: boolean;
  sourcesPath: string;
  skippedNoManifest: string[];
  message?: string;
};

export async function processSourceList(
  options: SourceListProcessOptions,
): Promise<SourceListProcessResult> {
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
    if (!existsSync(agentDir)) {
      console.error(`    [${entry.id}] missing path: ${formatDisplayPath(agentDir)}`);
      hadErrors = true;
      errorCount += 1;
      continue;
    }
    const stat = await fs.stat(agentDir);
    if (!stat.isDirectory()) {
      console.error(
        `    [${entry.id}] source path is not a directory: ${formatDisplayPath(agentDir)}`,
      );
      hadErrors = true;
      errorCount += 1;
      continue;
    }
    const manifestPath = path.join(agentDir, "build-manifest.toml");
    if (!existsSync(manifestPath)) {
      console.error(
        `    [${entry.id}] missing build-manifest.toml: ${formatDisplayPath(manifestPath)}`,
      );
      hadErrors = true;
      errorCount += 1;
      continue;
    }

    const bm: BuildManifest = await readBuildManifest(agentDir);
    const sourceVer: string = normalizeSemver(entry.ver, `${entry.id} sources.ver`);
    const bmVer: string = normalizeSemver(bm.version, `${entry.id} build-manifest.toml version`);

    const baseVersion = semver.gte(bmVer, sourceVer) ? bmVer : sourceVer;
    const buildVersion = bumpVersion(baseVersion, options.release, options.prerelease);
    const outDir = resolveOutDir(agentDir, options.out);
    await ensureRepoDir(outDir);
    const repoVer: RepoVersion | null = await findHighestRepoVersion(outDir, bm.plugin_id);

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
    await packAgentToRepo(agentDir, bmForBuild, outDir);

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
    logRepoSkipNote();
  }
  console.log(`completed: ${formatTimestamp()}`);
  console.log("");

  return {
    hadErrors,
    errorCount,
    packedCount,
    skippedCount,
    sourceListStatus,
  };
}

export async function createSourceListFromDir(
  agentRoot: string,
  force?: boolean,
): Promise<CreateSourceListResult> {
  const sourcesPath = path.join(agentRoot, "sources.json");
  const rootItems = await fs.readdir(agentRoot, { withFileTypes: true });
  const existingSources = rootItems.some(
    (item) => item.isFile() && item.name === "sources.json",
  );
  if (existingSources && !force) {
    return {
      created: false,
      sourcesPath,
      skippedNoManifest: [],
      message: `sources.json already exists at ${formatDisplayPath(sourcesPath)} (use --force to overwrite)`,
    };
  }

  const candidateDirs = rootItems
    .filter((item) => item.isDirectory())
    .map((item) => item.name);
  const skippedNoManifest: string[] = [];
  const agentDirs: string[] = [];

  for (const dirName of candidateDirs) {
    const entries = await fs.readdir(path.join(agentRoot, dirName), { withFileTypes: true });
    const hasManifest = entries.some(
      (entry) => entry.isFile() && entry.name === "build-manifest.toml",
    );
    if (hasManifest) {
      agentDirs.push(dirName);
    } else {
      skippedNoManifest.push(dirName);
    }
  }

  const sources: SourceEntry[] = [];
  for (const dirName of agentDirs) {
    const agentDir = path.join(agentRoot, dirName);
    const bm = await readBuildManifest(agentDir);
    const ver = normalizeSemver(bm.version, `${dirName} build-manifest.toml version`);
    sources.push({
      id: dirName,
      path: dirName,
      ver,
    });
  }

  const payload: SourcesFile = { sources };
  await fs.writeFile(sourcesPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  console.log("");
  console.log("created:");
  console.log(`    ${formatDisplayPath(sourcesPath)}`);
  if (skippedNoManifest.length > 0) {
    console.log("skipped folders (no build-manifest.toml):");
    for (const skipped of skippedNoManifest.sort()) {
      console.log(`    - ${skipped}`);
    }
  }
  return {
    created: true,
    sourcesPath,
    skippedNoManifest,
  };
}
