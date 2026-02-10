import type { OperationsControlSnapshot, OpsStatusPayload } from "./types.js";

type OperationsControlResult = {
  ok: boolean;
  error?: string;
};

type QuitDeps = {
  isQuitInProgress: () => boolean;
  setQuitInProgress: (value: boolean) => void;
  operationsMayBeRunning: () => boolean;
  stopBackgroundLoops: () => void;
  quitApp: () => void;
  promptQuitBehavior: () => Promise<number>;
  stopOperations: () => Promise<OperationsControlResult>;
  showShutdownError: (detail: string) => Promise<void>;
};

export function operationsMayBeRunning(
  hasManagedProcess: boolean,
  lastStatusState: OpsStatusPayload["state"],
  operationsControlState: OperationsControlSnapshot,
): boolean {
  if (hasManagedProcess) {
    return true;
  }
  if (lastStatusState === "connected") {
    return true;
  }
  return (
    operationsControlState.state === "running" ||
    operationsControlState.state === "starting" ||
    operationsControlState.state === "stopping"
  );
}

export async function handleQuitRequest(
  event: { preventDefault: () => void },
  deps: QuitDeps,
): Promise<void> {
  if (deps.isQuitInProgress()) {
    return;
  }
  if (!deps.operationsMayBeRunning()) {
    deps.stopBackgroundLoops();
    deps.setQuitInProgress(true);
    deps.quitApp();
    return;
  }

  event.preventDefault();
  const response = await deps.promptQuitBehavior();
  if (response === 2) {
    return;
  }

  if (response === 0) {
    const stopResult = await deps.stopOperations();
    if (!stopResult.ok) {
      await deps.showShutdownError(stopResult.error || "unknown_error");
      return;
    }
  }

  deps.stopBackgroundLoops();
  deps.setQuitInProgress(true);
  deps.quitApp();
}
