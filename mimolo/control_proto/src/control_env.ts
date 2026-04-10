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
  ipcMode: "auto" | "unix" | "slowpoke";
  ipcPath: string;
  ipcSlowpokeRoot: string;
  opsLogPath: string;
  controlDevMode: boolean;
};

function parseIpcMode(raw: string | undefined): "auto" | "unix" | "slowpoke" {
  const normalized = raw?.trim().toLowerCase() || "auto";
  if (normalized === "unix" || normalized === "slowpoke") {
    return normalized;
  }
  return "auto";
}

export function resolveControlEnvironment(
  runtimeProcess: RuntimeProcess,
): ControlEnvironment {
  return {
    ipcMode: parseIpcMode(runtimeProcess.env.MIMOLO_IPC_MODE),
    ipcPath: runtimeProcess.env.MIMOLO_IPC_PATH || "",
    ipcSlowpokeRoot: runtimeProcess.env.MIMOLO_IPC_SLOWPOKE_ROOT || "",
    opsLogPath: runtimeProcess.env.MIMOLO_OPS_LOG_PATH || "",
    controlDevMode: parseEnabledEnv(runtimeProcess.env.MIMOLO_CONTROL_DEV_MODE),
  };
}
