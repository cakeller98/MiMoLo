import path from "node:path";
import semver from "semver";
import type { BuildManifest, RepoVersion } from "./pack_agent_core.js";
import { formatDisplayPath } from "./pack_agent_cli_helpers.js";
import {
  ensureRepoDir,
  findHighestRepoVersion,
  readBuildManifest,
  resolveOutDir,
  updateBuildManifest,
  verifyExistingArchive,
} from "./pack_agent_core.js";
import { logRepoSkipNote, packAgentToRepo } from "./pack_agent_packing_helpers.js";
import type { PrereleaseType, ReleaseType } from "./pack_agent_versioning.js";
import { bumpVersion } from "./pack_agent_versioning.js";

export type SinglePackOptions = {
  sourcePath: string;
  out?: string;
  release?: ReleaseType;
  prerelease?: PrereleaseType;
  verifyExisting: boolean;
  forcePack: boolean;
};

export type SinglePackResult = {
  hadErrors: boolean;
  errorCount: number;
  skipped: boolean;
  packed: boolean;
};

export async function packSingleAgent(options: SinglePackOptions): Promise<SinglePackResult> {
  const agentDir = path.resolve(options.sourcePath);
  // Default output is ../repository relative to the source agent folder.
  const outDir = resolveOutDir(agentDir, options.out);

  const bm = await readBuildManifest(agentDir);
  const hasBump = Boolean(options.release || options.prerelease);
  const desiredVersion = bumpVersion(bm.version, options.release, options.prerelease);
  let skipped = false;

  await ensureRepoDir(outDir);
  const repoVer: RepoVersion | null = await findHighestRepoVersion(outDir, bm.plugin_id);

  if (repoVer) {
    if (semver.gt(repoVer.version, desiredVersion)) {
      console.log("");
      console.log("conflicts:");
      console.log(`    [${bm.plugin_id}]`);
      console.log(
        `        build-manifest.toml: v${bm.version} (${formatDisplayPath(path.join(agentDir, "build-manifest.toml"))})`,
      );
      console.log(`        repository: v${repoVer.version} (${formatDisplayPath(repoVer.path)})`);
      console.log(
        `        message: something's not write, you have output (v${repoVer.version}) that supersedes the build-manifest.toml (v${bm.version}). Resolve this manually before packing can continue.`,
      );
      console.log("");
      return {
        hadErrors: true,
        errorCount: 1,
        skipped: false,
        packed: false,
      };
    }

    if (semver.eq(repoVer.version, desiredVersion)) {
      if (hasBump && !options.forcePack) {
        console.log("");
        console.log("conflicts:");
        console.log(`    [${bm.plugin_id}]`);
        console.log(
          `        build-manifest.toml: v${bm.version} (${formatDisplayPath(path.join(agentDir, "build-manifest.toml"))})`,
        );
        console.log(`        repository: v${repoVer.version} (${formatDisplayPath(repoVer.path)})`);
        console.log(
          `        message: something's not write, you requested a version bump but output (v${repoVer.version}) already exists. Resolve this manually before packing can continue.`,
        );
        console.log("");
        return {
          hadErrors: true,
          errorCount: 1,
          skipped: false,
          packed: false,
        };
      }

      if (!hasBump && !options.forcePack) {
        if (options.verifyExisting) {
          const bmForBuild: BuildManifest = { ...bm, version: desiredVersion };
          const matches = await verifyExistingArchive(agentDir, bmForBuild, repoVer.path);
          if (!matches) {
            console.log("");
            console.log("conflicts:");
            console.log(`    [${bm.plugin_id}]`);
            console.log(
              `        build-manifest.toml: v${bm.version} (${formatDisplayPath(path.join(agentDir, "build-manifest.toml"))})`,
            );
            console.log(
              `        repository: v${repoVer.version} (${formatDisplayPath(repoVer.path)})`,
            );
            console.log(
              `        message: something's not write, repository output (v${repoVer.version}) does not match current sources for the same version. Resolve this manually before packing can continue.`,
            );
            console.log("");
            return {
              hadErrors: true,
              errorCount: 1,
              skipped: false,
              packed: false,
            };
          }
          console.log(
            `skipped: ${repoVer.version} already exists in repository (verified, assumed current revision)`,
          );
          skipped = true;
        } else {
          console.log(
            `skipped: ${repoVer.version} already exists in repository (assumed current revision)`,
          );
          skipped = true;
        }
      }

      if (options.forcePack) {
        console.log(`${repoVer.version} exists in repository (force-pack overwriting)`);
      }
    }
  }

  if (skipped) {
    logRepoSkipNote();
    return {
      hadErrors: false,
      errorCount: 0,
      skipped: true,
      packed: false,
    };
  }

  if (bm.version !== desiredVersion) {
    bm.version = desiredVersion;
    await updateBuildManifest(agentDir, bm);
  }
  await packAgentToRepo(agentDir, bm, outDir);

  console.log(`packed ${bm.plugin_id} v${bm.version}`);
  return {
    hadErrors: false,
    errorCount: 0,
    skipped: false,
    packed: true,
  };
}
