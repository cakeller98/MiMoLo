import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import type {
  IpcResponsePayload,
  IpcTrafficClass,
  OperationsControlRequest,
  OperationsControlSnapshot,
  OperationsProcessState,
  OpsStatusPayload,
  RuntimeProcess,
} from "./types.js";

type SendIpcCommandFn = (
  cmd: string,
  extraPayload?: Record<string, unknown>,
  trafficLabel?: string,
  trafficClass?: IpcTrafficClass,
) => Promise<IpcResponsePayload>;

interface OperationsControllerDependencies {
  appendOpsLogChunk: (rawChunk: unknown) => void;
  getLastStatusState: () => OpsStatusPayload["state"];
  getOperationsControlState: () => OperationsControlSnapshot;
  getStopWaitDisconnectPollMs: () => number;
  getStopWaitDisconnectTimeoutMs: () => number;
  getStopWaitForcedExitMs: () => number;
  getStopWaitGracefulExitMs: () => number;
  getStopWaitManagedExitMs: () => number;
  opsLogPath: string;
  publishLine: (line: string) => void;
  runtimeProcess: RuntimeProcess;
  sendIpcCommand: SendIpcCommandFn;
  setOperationsControlState: (
    state: OperationsProcessState,
    detail: string,
    managed: boolean,
    pid: number | null,
  ) => void;
}

interface OperationsControlResult {
  error?: string;
  ok: boolean;
  state: OperationsControlSnapshot;
}

function quoteBashArg(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function waitForProcessExit(
  processRef: ReturnType<typeof spawn>,
  timeoutMs: number,
): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value: boolean) => {
      if (settled) {
        return;
      }
      settled = true;
      resolve(value);
    };

    processRef.on("exit", () => {
      finish(true);
    });

    setTimeout(() => {
      finish(false);
    }, timeoutMs);
  });
}

function sleepMs(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export class OperationsController {
  private readonly deps: OperationsControllerDependencies;
  private operationsProcess: ReturnType<typeof spawn> | null = null;
  private operationsStopRequested = false;

  public constructor(deps: OperationsControllerDependencies) {
    this.deps = deps;
  }

  public hasManagedProcess(): boolean {
    return this.operationsProcess !== null;
  }

  public haltManagedForShutdown(): void {
    if (!this.operationsProcess) {
      return;
    }
    const child = this.operationsProcess;
    this.operationsStopRequested = true;
    try {
      child.kill("SIGTERM");
    } catch {
      try {
        child.kill("SIGKILL");
      } catch {
        // Ignore shutdown-time kill failures.
      }
    }
  }

  public async control(
    request: OperationsControlRequest,
  ): Promise<OperationsControlResult> {
    if (request.action === "status") {
      return {
        ok: true,
        state: this.deps.getOperationsControlState(),
      };
    }
    if (request.action === "start") {
      return this.start();
    }
    if (request.action === "stop") {
      return this.stop();
    }
    if (request.action === "restart") {
      const stopResult = await this.stop();
      if (!stopResult.ok && stopResult.error !== "operations_not_managed") {
        return stopResult;
      }
      return this.start();
    }
    return {
      ok: false,
      error: "invalid_ops_action",
      state: this.deps.getOperationsControlState(),
    };
  }

  private buildStartCommand(): { args: string[]; command: string } {
    const configPath = this.deps.runtimeProcess.env.MIMOLO_RUNTIME_CONFIG_PATH || "";
    const override = this.deps.runtimeProcess.env.MIMOLO_OPERATIONS_START_CMD || "";
    const defaultCmd = configPath
      ? `exec poetry run python -m mimolo.cli ops --config ${quoteBashArg(configPath)}`
      : "exec poetry run python -m mimolo.cli ops";
    const shellCommand = override.trim().length > 0 ? override.trim() : defaultCmd;
    if (this.deps.runtimeProcess.platform === "win32") {
      return {
        command: "pwsh",
        args: ["-NoProfile", "-Command", shellCommand],
      };
    }
    return {
      command: "bash",
      args: ["-lc", shellCommand],
    };
  }

  private async waitForIpcDisconnect(timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    const pollMs = Math.max(1, this.deps.getStopWaitDisconnectPollMs());
    while (Date.now() < deadline) {
      try {
        const pingResponse = await this.deps.sendIpcCommand(
          "ping",
          undefined,
          undefined,
          "background",
        );
        if (!pingResponse.ok) {
          return true;
        }
      } catch {
        return true;
      }
      await sleepMs(pollMs);
    }
    return false;
  }

  private async requestOperationsStopOverIpc(): Promise<{ error?: string; ok: boolean }> {
    try {
      const stopResponse = await this.deps.sendIpcCommand(
        "control_orchestrator",
        { action: "stop" },
        undefined,
        "interactive",
      );
      if (!stopResponse.ok) {
        return {
          ok: false,
          error: stopResponse.error || "external_stop_rejected",
        };
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : "external_stop_failed";
      return {
        ok: false,
        error: detail,
      };
    }

    const disconnected = await this.waitForIpcDisconnect(
      Math.max(1, this.deps.getStopWaitDisconnectTimeoutMs()),
    );
    if (!disconnected) {
      return {
        ok: false,
        error: "external_stop_timeout",
      };
    }
    return {
      ok: true,
    };
  }

  private async start(): Promise<OperationsControlResult> {
    if (this.operationsProcess) {
      this.deps.setOperationsControlState(
        "running",
        "already_running_managed",
        true,
        typeof this.operationsProcess.pid === "number"
          ? this.operationsProcess.pid
          : null,
      );
      return {
        ok: true,
        state: this.deps.getOperationsControlState(),
      };
    }

    if (this.deps.getLastStatusState() === "connected") {
      this.deps.setOperationsControlState("running", "external_unmanaged", false, null);
      return {
        ok: false,
        error: "operations_running_unmanaged",
        state: this.deps.getOperationsControlState(),
      };
    }

    const cwdRaw = this.deps.runtimeProcess.env.MIMOLO_REPO_ROOT || "";
    const spawnCwd = cwdRaw.trim().length > 0
      ? cwdRaw.trim()
      : (typeof this.deps.runtimeProcess.cwd === "function"
        ? this.deps.runtimeProcess.cwd()
        : undefined);

    this.deps.setOperationsControlState("starting", "launching", true, null);
    if (this.deps.opsLogPath) {
      try {
        await mkdir(path.dirname(this.deps.opsLogPath), { recursive: true });
        await writeFile(this.deps.opsLogPath, "", { flag: "a" });
        this.deps.appendOpsLogChunk("\n[control] starting operations process\n");
      } catch (err) {
        const detail = err instanceof Error ? err.message : "ops_log_init_failed";
        this.deps.publishLine(`[ops-log] init failed before spawn: ${detail}`);
      }
    }

    const launch = this.buildStartCommand();
    try {
      const child = spawn(launch.command, launch.args, {
        cwd: spawnCwd,
        env: this.deps.runtimeProcess.env,
        stdio: ["ignore", "pipe", "pipe"],
      });
      this.operationsStopRequested = false;
      this.operationsProcess = child;
      this.deps.setOperationsControlState(
        "running",
        "spawned_by_control",
        true,
        typeof child.pid === "number" ? child.pid : null,
      );

      if (child.stdout) {
        child.stdout.on("data", (chunk: unknown) => {
          this.deps.appendOpsLogChunk(chunk);
        });
      }
      if (child.stderr) {
        child.stderr.on("data", (chunk: unknown) => {
          this.deps.appendOpsLogChunk(chunk);
        });
      }

      child.on("error", (err: { message?: string }) => {
        if (this.operationsProcess !== child) {
          return;
        }
        this.operationsProcess = null;
        this.operationsStopRequested = false;
        const detail = err && typeof err.message === "string"
          ? err.message
          : "spawn_failed";
        this.deps.setOperationsControlState("error", `spawn_error:${detail}`, true, null);
        this.deps.publishLine(`[ops] spawn failed: ${detail}`);
      });

      child.on("exit", (code: number | null, signal: string | null) => {
        if (this.operationsProcess !== child) {
          return;
        }
        this.operationsProcess = null;
        const stopRequested = this.operationsStopRequested;
        this.operationsStopRequested = false;
        if (stopRequested) {
          this.deps.setOperationsControlState("stopped", "stopped_by_control", false, null);
          return;
        }
        if (code === 0) {
          this.deps.setOperationsControlState("stopped", "exited_clean", false, null);
          return;
        }
        const detail = `exited_unexpectedly(code=${String(code)},signal=${String(signal)})`;
        this.deps.setOperationsControlState("error", detail, false, null);
      });

      return {
        ok: true,
        state: this.deps.getOperationsControlState(),
      };
    } catch (err) {
      const detail = err instanceof Error ? err.message : "spawn_failed";
      this.deps.setOperationsControlState("error", `spawn_failed:${detail}`, true, null);
      return {
        ok: false,
        error: "spawn_failed",
        state: this.deps.getOperationsControlState(),
      };
    }
  }

  private async stop(): Promise<OperationsControlResult> {
    if (!this.operationsProcess) {
      if (this.deps.getLastStatusState() === "connected") {
        this.deps.setOperationsControlState(
          "stopping",
          "external_stop_requested",
          false,
          null,
        );
        const stopResult = await this.requestOperationsStopOverIpc();
        if (!stopResult.ok) {
          this.deps.setOperationsControlState("running", "external_unmanaged", false, null);
          return {
            ok: false,
            error: stopResult.error,
            state: this.deps.getOperationsControlState(),
          };
        }
        this.deps.setOperationsControlState("stopped", "stopped_via_ipc", false, null);
        return {
          ok: true,
          state: this.deps.getOperationsControlState(),
        };
      }
      this.deps.setOperationsControlState("stopped", "not_managed", false, null);
      return {
        ok: true,
        state: this.deps.getOperationsControlState(),
      };
    }

    const child = this.operationsProcess;
    if (this.deps.getLastStatusState() === "connected") {
      this.deps.setOperationsControlState(
        "stopping",
        "managed_stop_requested_via_ipc",
        true,
        typeof child.pid === "number" ? child.pid : null,
      );
      const stopResult = await this.requestOperationsStopOverIpc();
      if (stopResult.ok) {
        await waitForProcessExit(
          child,
          Math.max(1, this.deps.getStopWaitManagedExitMs()),
        );
        if (this.operationsProcess === child) {
          this.operationsProcess = null;
        }
        this.operationsStopRequested = false;
        this.deps.setOperationsControlState("stopped", "stopped_via_ipc", false, null);
        return {
          ok: true,
          state: this.deps.getOperationsControlState(),
        };
      }
    }

    this.operationsStopRequested = true;
    this.deps.setOperationsControlState(
      "stopping",
      "stop_requested",
      true,
      typeof child.pid === "number" ? child.pid : null,
    );

    try {
      child.kill("SIGTERM");
    } catch (err) {
      const detail = err instanceof Error ? err.message : "kill_failed";
      this.deps.setOperationsControlState("error", `stop_failed:${detail}`, true, null);
      return {
        ok: false,
        error: "stop_failed",
        state: this.deps.getOperationsControlState(),
      };
    }

    const exitedGracefully = await waitForProcessExit(
      child,
      Math.max(1, this.deps.getStopWaitGracefulExitMs()),
    );
    if (!exitedGracefully && this.operationsProcess === child) {
      try {
        child.kill("SIGKILL");
      } catch (err) {
        const detail = err instanceof Error ? err.message : "kill_force_failed";
        this.deps.setOperationsControlState("error", `force_stop_failed:${detail}`, true, null);
        return {
          ok: false,
          error: "force_stop_failed",
          state: this.deps.getOperationsControlState(),
        };
      }
      await waitForProcessExit(
        child,
        Math.max(1, this.deps.getStopWaitForcedExitMs()),
      );
    }

    if (this.operationsProcess === child) {
      this.operationsProcess = null;
      this.operationsStopRequested = false;
      this.deps.setOperationsControlState("stopped", "stopped_by_control", false, null);
    }
    return {
      ok: true,
      state: this.deps.getOperationsControlState(),
    };
  }
}
