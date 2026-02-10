import archiver from "archiver";
import { createHash } from "node:crypto";
import { createWriteStream, promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import type { BuildManifest } from "./pack_agent_types.js";
import { writeManifest } from "./pack_agent_manifest_io.js";

export async function hashFile(absPath: string): Promise<string> {
  const buf = await fs.readFile(absPath);
  return createHash("sha256").update(buf).digest("hex");
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

    // Archiver finalize may reject asynchronously; route directly to Promise rejection.
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
    // Always clean temporary verification artifacts, independent of pack/hash outcome.
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
}
