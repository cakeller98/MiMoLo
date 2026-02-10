import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import type { BuildManifest } from "./pack_agent_core.js";
import { packZip, writeManifest, writePayloadHashes } from "./pack_agent_core.js";

const REPO_SKIP_NOTE =
  "note: if you did not expect repo to be skipped, it is a good idea to periodically run the " +
  "--verify-existing flag to confirm the hashes of all current agents before public release to ensure " +
  "that the released artifact is the version that was expected. --force-pack can also be used but this " +
  "will overwrite artifacts and if you are not careful it is possible that a version mismatch could occur. " +
  "best to use --verify-existing unless you know what you're doing.";

export async function packAgentToRepo(
  agentDir: string,
  bm: BuildManifest,
  outDir: string,
): Promise<void> {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "mimolo-pack-"));
  try {
    const manifestPath = await writeManifest(tmpDir, bm);
    const hashesPath = await writePayloadHashes(agentDir, tmpDir, bm);
    await packZip(agentDir, bm, outDir, manifestPath, hashesPath);
  } finally {
    // Always remove temporary pack workspace, regardless of pack success/failure.
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
}

export function logRepoSkipNote(): void {
  console.log("");
  console.log(REPO_SKIP_NOTE);
  console.log("");
}
