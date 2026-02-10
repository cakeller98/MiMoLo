import archiver from "archiver";
import { createHash } from "node:crypto";
import { createWriteStream, promises as fs } from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import type { BuildManifest } from "./pack_agent_types.js";

type PayloadHashesFile = {
  version: string;
  hash_algo: "sha256";
  files: Record<string, string>;
};

export async function hashFile(absPath: string): Promise<string> {
  const buf = await fs.readFile(absPath);
  return createHash("sha256").update(buf).digest("hex");
}

export async function writePayloadHashes(
  agentDir: string,
  outDir: string,
  bm: BuildManifest,
): Promise<string> {
  const payload = await buildPayloadHashesPayload(agentDir, bm);

  const outPath = path.join(outDir, "payload_hashes.json");
  await fs.writeFile(outPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  return outPath;
}

async function buildPayloadHashesPayload(
  agentDir: string,
  bm: BuildManifest,
): Promise<PayloadHashesFile> {
  const hashes: Record<string, string> = {};
  for (const rel of bm.files) {
    const abs = path.join(agentDir, rel);
    const key = path.posix.join("files", rel.replace(/\\/g, "/"));
    hashes[key] = await hashFile(abs);
  }
  return {
    version: bm.version,
    hash_algo: "sha256",
    files: hashes,
  };
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
  const expected = await buildPayloadHashesPayload(agentDir, bm);
  const payloadEntry = `${bm.plugin_id}/payload_hashes.json`;
  const rawActual = await readZipEntryUtf8(repoZipPath, payloadEntry);
  const actual = JSON.parse(rawActual) as PayloadHashesFile;
  return payloadHashesEqual(expected, actual);
}

function payloadHashesEqual(a: PayloadHashesFile, b: PayloadHashesFile): boolean {
  if (a.version !== b.version) {
    return false;
  }
  if (a.hash_algo !== b.hash_algo) {
    return false;
  }
  const aKeys = Object.keys(a.files).sort();
  const bKeys = Object.keys(b.files).sort();
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  for (let i = 0; i < aKeys.length; i += 1) {
    const key = aKeys[i];
    if (key !== bKeys[i]) {
      return false;
    }
    if (a.files[key] !== b.files[key]) {
      return false;
    }
  }
  return true;
}

function readZipEntryUtf8(zipPath: string, entryName: string): Promise<string> {
  return fs.readFile(zipPath).then((buf) => {
    const eocdOffset = findEndOfCentralDirectoryOffset(buf);
    const totalEntries = buf.readUInt16LE(eocdOffset + 10);
    const centralDirectoryOffset = buf.readUInt32LE(eocdOffset + 16);
    let cursor = centralDirectoryOffset;

    for (let i = 0; i < totalEntries; i += 1) {
      const centralSig = buf.readUInt32LE(cursor);
      if (centralSig !== 0x02014b50) {
        throw new Error(`invalid zip central directory signature in ${zipPath}`);
      }
      const compressionMethod = buf.readUInt16LE(cursor + 10);
      const compressedSize = buf.readUInt32LE(cursor + 20);
      const fileNameLength = buf.readUInt16LE(cursor + 28);
      const extraLength = buf.readUInt16LE(cursor + 30);
      const commentLength = buf.readUInt16LE(cursor + 32);
      const localHeaderOffset = buf.readUInt32LE(cursor + 42);
      const nameStart = cursor + 46;
      const nameEnd = nameStart + fileNameLength;
      const fileName = buf.toString("utf8", nameStart, nameEnd);
      if (fileName === entryName) {
        return decodeZipLocalFile(
          buf,
          zipPath,
          localHeaderOffset,
          compressedSize,
          compressionMethod,
        );
      }
      cursor = nameEnd + extraLength + commentLength;
    }

    throw new Error(`zip entry not found: ${entryName} (${zipPath})`);
  });
}

function decodeZipLocalFile(
  zipBuffer: Buffer,
  zipPath: string,
  localHeaderOffset: number,
  compressedSize: number,
  compressionMethod: number,
): string {
  const localSig = zipBuffer.readUInt32LE(localHeaderOffset);
  if (localSig !== 0x04034b50) {
    throw new Error(`invalid zip local header signature in ${zipPath}`);
  }
  const localNameLength = zipBuffer.readUInt16LE(localHeaderOffset + 26);
  const localExtraLength = zipBuffer.readUInt16LE(localHeaderOffset + 28);
  const dataOffset = localHeaderOffset + 30 + localNameLength + localExtraLength;
  const compressedData = zipBuffer.subarray(dataOffset, dataOffset + compressedSize);

  if (compressionMethod === 0) {
    return compressedData.toString("utf8");
  }
  if (compressionMethod === 8) {
    return zlib.inflateRawSync(compressedData).toString("utf8");
  }
  throw new Error(`unsupported zip compression method ${compressionMethod} in ${zipPath}`);
}

function findEndOfCentralDirectoryOffset(zipBuffer: Buffer): number {
  const minimumEocdSize = 22;
  const scanStart = Math.max(0, zipBuffer.length - 0xffff - minimumEocdSize);
  for (let i = zipBuffer.length - minimumEocdSize; i >= scanStart; i -= 1) {
    if (zipBuffer.readUInt32LE(i) === 0x06054b50) {
      return i;
    }
  }
  throw new Error("invalid zip: end-of-central-directory signature not found");
}
