import { readFile } from "node:fs/promises";
import type { RuntimeProcess } from "./types.js";
import { parseControlSettingsFromToml } from "./control_timing.js";

export async function loadControlTimingSettingsFromConfigFile(
  runtimeProcess: RuntimeProcess,
  applyControlTimingSettings: (raw: unknown) => void,
): Promise<void> {
  const configCandidates: string[] = [];
  const runtimeConfigPath = runtimeProcess.env.MIMOLO_RUNTIME_CONFIG_PATH;
  if (runtimeConfigPath && runtimeConfigPath.trim().length > 0) {
    configCandidates.push(runtimeConfigPath.trim());
  }
  const sourceConfigPath = runtimeProcess.env.MIMOLO_CONFIG_SOURCE_PATH;
  if (sourceConfigPath && sourceConfigPath.trim().length > 0) {
    configCandidates.push(sourceConfigPath.trim());
  }
  configCandidates.push("mimolo.toml");

  for (const candidate of configCandidates) {
    try {
      const content = await readFile(candidate, "utf8");
      const parsed = parseControlSettingsFromToml(content);
      applyControlTimingSettings(parsed);
      return;
    } catch {
      continue;
    }
  }
}
