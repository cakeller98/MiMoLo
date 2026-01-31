import archiver from "archiver";
import { createWriteStream, promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
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

async function main(): Promise<void> {
  const { source, out, release, prerelease } = parseArgs(process.argv.slice(2));
  if (!source) {
    console.error(
      "usage: release-pack-agent --source <agent_dir> [--out <out_dir>] [--major|--minor|--patch] [--alpha|--beta|--rc]"
    );
    process.exit(1);
  }

  const agentDir = path.resolve(source);
  // Default output is ../repository relative to the source agent folder.
  const outDirRaw = out ?? path.join(agentDir, "..", "repository");
  const outDir = path.isAbsolute(outDirRaw)
    ? outDirRaw
    : path.resolve(agentDir, outDirRaw);

  const bm = await readBuildManifest(agentDir);
  if (release || prerelease) {
    bm.version = bumpVersion(bm.version, release, prerelease);
    const updated = [
      `plugin_id = \"${bm.plugin_id}\"`,
      `name = \"${bm.name}\"`,
      `version = \"${bm.version}\"`,
      `entry = \"${bm.entry}\"`,
      `files = [${bm.files.map((f) => `\"${f}\"`).join(", ")}]`
    ];
    await fs.writeFile(path.join(agentDir, "build-manifest.toml"), updated.join("\n") + "\n", "utf8");
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
