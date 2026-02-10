import type { RuntimeProcess } from "./types.js";

function parseEnabledEnv(raw: string | undefined): boolean {
  if (!raw) {
    return false;
  }
  const normalized = raw.trim().toLowerCase();
  return (
    normalized === "1" ||
    normalized === "true" ||
    normalized === "yes" ||
    normalized === "on"
  );
}

export type ControlEnvironment = {
  ipcPath: string;
  opsLogPath: string;
  controlDevMode: boolean;
};

export function resolveControlEnvironment(
  runtimeProcess: RuntimeProcess,
): ControlEnvironment {
  return {
    ipcPath: runtimeProcess.env.MIMOLO_IPC_PATH || "",
    opsLogPath: runtimeProcess.env.MIMOLO_OPS_LOG_PATH || "",
    controlDevMode: parseEnabledEnv(runtimeProcess.env.MIMOLO_CONTROL_DEV_MODE),
  };
}
