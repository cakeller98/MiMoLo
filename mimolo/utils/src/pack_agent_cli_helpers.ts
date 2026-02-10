import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { SourceEntry, SourcesFile } from "./pack_agent_core.js";

export function formatDisplayPath(targetPath: string): string {
  const rel = path.relative(process.cwd(), targetPath);
  if (!rel) {
    return ".";
  }
  if (!rel.startsWith(".") && !rel.startsWith("..")) {
    return `./${rel}`;
  }
  return rel;
}

export function formatTimestamp(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

export async function readPackageVersion(): Promise<string> {
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

export async function resolveDefaultSourcesCandidates(): Promise<string[]> {
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

export async function resolveDefaultAgentsDir(): Promise<string | null> {
  const agentsDir = path.resolve(process.cwd(), "..", "agents");
  try {
    const stat = await fs.stat(agentsDir);
    return stat.isDirectory() ? agentsDir : null;
  } catch {
    return null;
  }
}

export function logSourcesSelection(selected: string, candidates?: string[]): void {
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

export function nextSourcesVersionLabel(existing: string[]): string {
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

export async function writeSourcesVersioned(
  listPath: string,
  sources: SourceEntry[],
): Promise<string> {
  const dir = path.dirname(listPath);
  const files = await fs.readdir(dir);
  const name = nextSourcesVersionLabel(files);
  const outPath = path.join(dir, name);
  const payload: SourcesFile = { sources };
  await fs.writeFile(outPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  return outPath;
}

export async function writeSourcesBackup(
  listPath: string,
  raw: string,
): Promise<string> {
  const dir = path.dirname(listPath);
  const files = await fs.readdir(dir);
  const name = nextSourcesVersionLabel(files);
  const outPath = path.join(dir, name);
  await fs.writeFile(outPath, raw, "utf8");
  return outPath;
}
