import type {
  OperationsControlSnapshot,
  OpsStatusPayload,
  QuitProgressPayload,
  QuitProgressStep,
} from "./types.js";

type OperationsControlResult = {
  ok: boolean;
  error?: string;
};

type QuitDeps = {
  isQuitInProgress: () => boolean;
  setQuitInProgress: (value: boolean) => void;
  operationsMayBeRunning: () => boolean;
  publishQuitProgress: (payload: QuitProgressPayload) => void;
  stopBackgroundLoops: () => void;
  quitApp: () => void;
  promptQuitBehavior: () => Promise<number>;
  stopOperations: () => Promise<OperationsControlResult>;
  showShutdownError: (detail: string) => Promise<void>;
};

function updateStepState(
  steps: QuitProgressStep[],
  key: string,
  state: QuitProgressStep["state"],
): QuitProgressStep[] {
  return steps.map((step) => (step.key === key ? { ...step, state } : step));
}

function publishProgress(
  deps: QuitDeps,
  title: string,
  steps: QuitProgressStep[],
  detail?: string,
): void {
  deps.publishQuitProgress({
    visible: true,
    title,
    detail,
    steps,
  });
}

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
  event.preventDefault();
  if (!deps.operationsMayBeRunning()) {
    let steps: QuitProgressStep[] = [
      { key: "loops", label: "Stop background polling", state: "active" },
      { key: "close", label: "Close Control", state: "pending" },
    ];
    publishProgress(deps, "Closing MiMoLo Control Proto", steps);
    deps.stopBackgroundLoops();
    steps = updateStepState(steps, "loops", "done");
    steps = updateStepState(steps, "close", "active");
    publishProgress(deps, "Closing MiMoLo Control Proto", steps);
    deps.setQuitInProgress(true);
    steps = updateStepState(steps, "close", "done");
    publishProgress(deps, "Closing MiMoLo Control Proto", steps);
    deps.quitApp();
    return;
  }

  const response = await deps.promptQuitBehavior();
  if (response === 2) {
    deps.publishQuitProgress({
      visible: false,
      title: "",
      steps: [],
    });
    return;
  }

  if (response === 0) {
    let steps: QuitProgressStep[] = [
      { key: "ops", label: "Request Operations shutdown", state: "active" },
      { key: "loops", label: "Stop background polling", state: "pending" },
      { key: "close", label: "Close Control", state: "pending" },
    ];
    publishProgress(
      deps,
      "Shutting Down Operations",
      steps,
      "Waiting for Operations and Agents to stop cleanly.",
    );
    const stopResult = await deps.stopOperations();
    if (!stopResult.ok) {
      steps = updateStepState(steps, "ops", "error");
      publishProgress(
        deps,
        "Shutting Down Operations",
        steps,
        stopResult.error || "unknown_error",
      );
      await deps.showShutdownError(stopResult.error || "unknown_error");
      deps.publishQuitProgress({
        visible: false,
        title: "",
        steps: [],
      });
      return;
    }
    steps = updateStepState(steps, "ops", "done");
    steps = updateStepState(steps, "loops", "active");
    publishProgress(
      deps,
      "Shutting Down Operations",
      steps,
      "Operations shutdown complete. Closing Control.",
    );
    deps.stopBackgroundLoops();
    steps = updateStepState(steps, "loops", "done");
    steps = updateStepState(steps, "close", "active");
    publishProgress(
      deps,
      "Shutting Down Operations",
      steps,
      "Operations shutdown complete. Closing Control.",
    );
    deps.setQuitInProgress(true);
    steps = updateStepState(steps, "close", "done");
    publishProgress(
      deps,
      "Shutting Down Operations",
      steps,
      "Operations shutdown complete. Closing Control.",
    );
    deps.quitApp();
    return;
  }

  let steps: QuitProgressStep[] = [
    { key: "loops", label: "Stop background polling", state: "active" },
    { key: "close", label: "Close Control", state: "pending" },
  ];
  publishProgress(
    deps,
    "Leaving Operations Running",
    steps,
    "Disconnecting Control and leaving Operations active.",
  );
  deps.stopBackgroundLoops();
  steps = updateStepState(steps, "loops", "done");
  steps = updateStepState(steps, "close", "active");
  publishProgress(
    deps,
    "Leaving Operations Running",
    steps,
    "Disconnecting Control and leaving Operations active.",
  );
  deps.setQuitInProgress(true);
  steps = updateStepState(steps, "close", "done");
  publishProgress(
    deps,
    "Leaving Operations Running",
    steps,
    "Disconnecting Control and leaving Operations active.",
  );
  deps.quitApp();
}
