import { createInterface } from "node:readline/promises";
import path from "node:path";
import type { PrereleaseType, ReleaseType } from "./pack_agent_modes.js";
import {
  createSourceListFromDir,
  packSingleAgent,
  processSourceList,
} from "./pack_agent_modes.js";
import {
  formatDisplayPath,
  formatTimestamp,
  logSourcesSelection,
  readPackageVersion,
  resolveDefaultAgentsDir,
  resolveDefaultSourcesCandidates,
} from "./pack_agent_cli_helpers.js";

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
  release?: ReleaseType;
  prerelease?: PrereleaseType;
};

type ParseArgsResult =
  | { ok: true; args: ArgMap }
  | { ok: false; error: string };

function parseArgs(argv: string[]): ParseArgsResult {
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
    return {
      ok: false,
      error: `release flags are mutually exclusive: ${releaseFlags.join(", ")}`,
    };
  }
  if (prereleaseFlags.length > 1) {
    return {
      ok: false,
      error: `prerelease flags are mutually exclusive: ${prereleaseFlags.join(", ")}`,
    };
  }
  return { ok: true, args };
}

function printHelp(): void {
  console.log("");
  console.log("pack-agent");
  console.log("");
  console.log("usage:");
  console.log(
    "  pack-agent --source <agent_dir> | --source-list <sources.json> [--out <out_dir>]",
  );
  console.log(
    "           [--major|--minor|--patch] [--alpha|--beta|--rc] [--verify-existing] [--force-pack]",
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
    output: process.stdout,
  });
  try {
    const answer = await rl.question(
      `sources.json not found. Create one from ${formatDisplayPath(agentsDir)}? (y/N) `,
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
    // Readline handle must always be closed to avoid dangling TTY resources.
    rl.close();
  }
}

async function main(): Promise<void> {
  const parseResult = parseArgs(process.argv.slice(2));
  if (!parseResult.ok) {
    console.error(parseResult.error);
    process.exitCode = 1;
    return;
  }
  const args = parseResult.args;
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
          const createResult = await createSourceListFromDir(agentsDir, false);
          if (!createResult.created) {
            console.error(createResult.message ?? "failed to create sources.json");
            process.exitCode = 1;
            return;
          }
          args.sourceList = path.join(agentsDir, "sources.json");
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
    const createResult = await createSourceListFromDir(args.source, args.force);
    if (!createResult.created) {
      console.error(createResult.message ?? "failed to create sources.json");
      process.exitCode = 1;
    }
    return;
  }

  if (args.sourceList) {
    logSourcesSelection(args.sourceList, defaultCandidates);
    const result = await processSourceList({
      sourceListPath: args.sourceList,
      out: args.out,
      release: args.release,
      prerelease: args.prerelease,
      verifyExisting: Boolean(args.verifyExisting),
      forcePack: Boolean(args.forcePack),
      sourcesCreated: Boolean(args.sourcesCreated),
    });
    if (result.hadErrors) {
      console.error(
        `pack-agent failed: ${result.errorCount} conflict(s) detected in source-list processing`,
      );
      process.exitCode = 1;
    }
    return;
  }

  if (!args.source) {
    console.error(
      "usage: pack-agent --source <agent_dir> | --source-list <sources.json> [--out <out_dir>] [--major|--minor|--patch] [--alpha|--beta|--rc] [--verify-existing] [--force-pack]",
    );
    process.exit(1);
  }

  const result = await packSingleAgent({
    sourcePath: args.source,
    out: args.out,
    release: args.release,
    prerelease: args.prerelease,
    verifyExisting: Boolean(args.verifyExisting),
    forcePack: Boolean(args.forcePack),
  });
  if (result.hadErrors) {
    console.error(`pack-agent failed: ${result.errorCount} conflict(s) detected in single-agent mode`);
    process.exitCode = 1;
  }
}

void main().catch((error: unknown) => {
  // CLI entrypoint boundary: emit actionable diagnostics and exit non-zero.
  const detail = error instanceof Error ? error.message : String(error);
  console.error(detail);
  process.exitCode = 1;
});
