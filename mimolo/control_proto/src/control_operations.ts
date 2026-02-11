import { spawn } from "node:child_process";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
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
  publishBootstrapLine: (line: string) => void;
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

interface RuntimePrepareResult {
  error?: string;
  ok: boolean;
  portablePython?: string;
  runtimeConfigPath?: string;
}

function quoteBashArg(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function resolvePortableOperationsPython(
  env: RuntimeProcess["env"],
): string {
  const explicit = (env.MIMOLO_OPERATIONS_PYTHON || "").trim();
  return explicit.length > 0 ? explicit : "";
}

function resolvePortablePythonFromRuntimeVenv(
  runtimeVenvPath: string,
  platform: RuntimeProcess["platform"],
): string {
  if (runtimeVenvPath.length === 0) {
    return "";
  }
  if (platform === "win32") {
    return `${runtimeVenvPath}\\Scripts\\python.exe`;
  }
  return `${runtimeVenvPath}/bin/python`;
}

async function pathExists(pathValue: string): Promise<boolean> {
  try {
    await stat(pathValue);
    return true;
  } catch {
    // External I/O check: path may legitimately not exist yet.
    return false;
  }
}

async function waitForPathExists(
  pathValue: string,
  timeoutMs: number,
  pollMs: number,
): Promise<boolean> {
  const deadline = Date.now() + Math.max(1, timeoutMs);
  const stepMs = Math.max(1, pollMs);
  while (Date.now() <= deadline) {
    if (await pathExists(pathValue)) {
      return true;
    }
    await sleepMs(stepMs);
  }
  return false;
}

async function runtimeConfigUsesPoetry(pathValue: string): Promise<boolean> {
  try {
    const raw = await readFile(pathValue, "utf8");
    return /executable\s*=\s*"poetry"/.test(raw);
  } catch {
    // External I/O check: unreadable config should trigger runtime bootstrap.
    return true;
  }
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
  private runtimePreparePromise: Promise<RuntimePrepareResult> | null = null;

  public constructor(deps: OperationsControllerDependencies) {
    this.deps = deps;
  }

  public hasManagedProcess(): boolean {
    return this.operationsProcess !== null;
  }

  public async prepareRuntime(): Promise<RuntimePrepareResult> {
    const spawnCwd = this.getSpawnCwd();
    const result = await this.ensurePortableRuntimeReady(spawnCwd);
    if (!result.ok) {
      return {
        ok: false,
        error: result.error,
      };
    }
    return {
      ok: true,
      portablePython: result.portablePython,
      runtimeConfigPath: result.runtimeConfigPath,
    };
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
    const portablePython = resolvePortableOperationsPython(
      this.deps.runtimeProcess.env,
    );
    if (override.trim().length === 0 && portablePython.length > 0) {
      const args = ["-m", "mimolo.cli", "ops"];
      if (configPath) {
        args.push("--config", configPath);
      }
      return {
        command: portablePython,
        args,
      };
    }
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

  private getSpawnCwd(): string | undefined {
    const cwdRaw = this.deps.runtimeProcess.env.MIMOLO_REPO_ROOT || "";
    return cwdRaw.trim().length > 0
      ? cwdRaw.trim()
      : (typeof this.deps.runtimeProcess.cwd === "function"
        ? this.deps.runtimeProcess.cwd()
        : undefined);
  }

  private async ensurePortableRuntimeReady(
    spawnCwd: string | undefined,
  ): Promise<RuntimePrepareResult> {
    if (this.runtimePreparePromise) {
      return this.runtimePreparePromise;
    }

    const env = this.deps.runtimeProcess.env;
    const portablePython = resolvePortableOperationsPython(env);
    if (portablePython.length === 0) {
      return { ok: true, portablePython };
    }

    const runtimeConfigPath = (env.MIMOLO_RUNTIME_CONFIG_PATH || "").trim();
    const needsPython = !(await pathExists(portablePython));
    const needsConfig = runtimeConfigPath.length > 0
      ? !(await pathExists(runtimeConfigPath))
      : false;
    const needsConfigRewrite = runtimeConfigPath.length > 0 && !needsConfig
      ? await runtimeConfigUsesPoetry(runtimeConfigPath)
      : false;
    if (!needsPython && !needsConfig && !needsConfigRewrite) {
      this.deps.publishBootstrapLine(`[bootstrap] runtime ready: ${portablePython}`);
      if (runtimeConfigPath.length > 0) {
        this.deps.publishBootstrapLine(`[bootstrap] runtime config: ${runtimeConfigPath}`);
      }
      return {
        ok: true,
        portablePython,
        runtimeConfigPath,
      };
    }

    const prepareScript = (env.MIMOLO_RUNTIME_PREPARE_SCRIPT || "").trim();
    if (prepareScript.length === 0) {
      return {
        ok: false,
        error: "runtime_prepare_script_missing",
      };
    }
    if (!(await pathExists(prepareScript))) {
      return {
        ok: false,
        error: "runtime_prepare_script_not_found",
      };
    }

    const args: string[] = [];
    const dataDir = (env.MIMOLO_DATA_DIR || "").trim();
    const binDir = (env.MIMOLO_BIN_DIR || "").trim();
    const configSourcePath = (env.MIMOLO_CONFIG_SOURCE_PATH || "").trim();
    const opsLogPath = (env.MIMOLO_OPS_LOG_PATH || "").trim();
    const monitorLogDir = (env.MIMOLO_MONITOR_LOG_DIR || "").trim();
    const monitorJournalDir = (env.MIMOLO_MONITOR_JOURNAL_DIR || "").trim();
    const monitorCacheDir = (env.MIMOLO_MONITOR_CACHE_DIR || "").trim();
    const sourceSitePackages = (env.MIMOLO_BOOTSTRAP_SOURCE_SITE_PACKAGES || "").trim();
    const sourcePython = (env.MIMOLO_BOOTSTRAP_SOURCE_PYTHON || "").trim();
    const runtimeVenvPath = (env.MIMOLO_RUNTIME_VENV_PATH || "").trim();
    const repoRoot = (env.MIMOLO_REPO_ROOT || "").trim();
    if (dataDir.length > 0) {
      args.push("--data-dir", dataDir);
    }
    if (binDir.length > 0) {
      args.push("--bin-dir", binDir);
    }
    if (runtimeConfigPath.length > 0) {
      args.push("--runtime-config", runtimeConfigPath);
    }
    if (configSourcePath.length > 0) {
      args.push("--config-source", configSourcePath);
    }
    if (opsLogPath.length > 0) {
      args.push("--ops-log-path", opsLogPath);
    }
    if (monitorLogDir.length > 0) {
      args.push("--monitor-log-dir", monitorLogDir);
    }
    if (monitorJournalDir.length > 0) {
      args.push("--monitor-journal-dir", monitorJournalDir);
    }
    if (monitorCacheDir.length > 0) {
      args.push("--monitor-cache-dir", monitorCacheDir);
    }
    if (sourceSitePackages.length > 0) {
      args.push("--source-site-packages", sourceSitePackages);
    }
    if (sourcePython.length > 0) {
      args.push("--source-python", sourcePython);
    }
    if (runtimeVenvPath.length > 0) {
      args.push("--runtime-venv", runtimeVenvPath);
    }
    if (repoRoot.length > 0) {
      args.push("--repo-root", repoRoot);
    }

    this.deps.publishLine("[ops] preparing portable runtime...");
    if (this.deps.opsLogPath) {
      this.deps.appendOpsLogChunk("\n[control] preparing portable runtime\n");
    }

    this.runtimePreparePromise = (async (): Promise<RuntimePrepareResult> => {
      let discoveredPortablePython = portablePython;
      let discoveredRuntimeConfigPath = runtimeConfigPath;
      const handleBootstrapLine = (line: string) => {
        const runtimeReadyPrefix = "[bootstrap] runtime ready:";
        const runtimeConfigPrefix = "[bootstrap] runtime config:";
        if (line.startsWith(runtimeReadyPrefix)) {
          const value = line.slice(runtimeReadyPrefix.length).trim();
          if (value.length > 0) {
            discoveredPortablePython = value;
          }
          return;
        }
        if (line.startsWith(runtimeConfigPrefix)) {
          const value = line.slice(runtimeConfigPrefix.length).trim();
          if (value.length > 0) {
            discoveredRuntimeConfigPath = value;
          }
        }
      };

      const prepareResult = await new Promise<RuntimePrepareResult>((resolve) => {
        const child = spawn(prepareScript, args, {
          cwd: spawnCwd,
          env,
          stdio: ["ignore", "pipe", "pipe"],
        });
        let settled = false;
        let stderrDetail = "";
        const finish = (result: RuntimePrepareResult) => {
          if (settled) {
            return;
          }
          settled = true;
          resolve(result);
        };

        if (child.stdout) {
          child.stdout.on("data", (chunk: unknown) => {
            this.deps.appendOpsLogChunk(chunk);
            const text = typeof chunk === "string" ? chunk : String(chunk);
            for (const line of text.split(/\r?\n/)) {
              const trimmed = line.trim();
              if (trimmed.length > 0) {
                this.deps.publishBootstrapLine(trimmed);
                handleBootstrapLine(trimmed);
              }
            }
          });
        }
        if (child.stderr) {
          child.stderr.on("data", (chunk: unknown) => {
            this.deps.appendOpsLogChunk(chunk);
            const text = typeof chunk === "string" ? chunk : String(chunk);
            for (const line of text.split(/\r?\n/)) {
              const trimmed = line.trim();
              if (trimmed.length > 0) {
                this.deps.publishBootstrapLine(trimmed);
                handleBootstrapLine(trimmed);
              }
            }
            const chunkText = typeof chunk === "string" ? chunk : String(chunk);
            stderrDetail += chunkText;
            if (stderrDetail.length > 4000) {
              stderrDetail = stderrDetail.slice(-4000);
            }
          });
        }

        child.on("error", (err: { message?: string }) => {
          const detail = err && typeof err.message === "string"
            ? err.message
            : "runtime_prepare_spawn_failed";
          finish({
            ok: false,
            error: detail,
          });
        });

        child.on("exit", (code: number | null) => {
          if (code === 0) {
            finish({
              ok: true,
              portablePython: discoveredPortablePython,
              runtimeConfigPath: discoveredRuntimeConfigPath,
            });
            return;
          }
          const tail = stderrDetail.trim();
          const detail = tail.length > 0
            ? `runtime_prepare_failed:${tail}`
            : `runtime_prepare_exit_code_${String(code)}`;
          finish({
            ok: false,
            error: detail,
          });
        });
      });
      if (!prepareResult.ok) {
        return prepareResult;
      }

      const runtimeVenvPathEffective = (env.MIMOLO_RUNTIME_VENV_PATH || "").trim();
      const candidatePortablePythons: string[] = [];
      const reportedPortablePython = (prepareResult.portablePython || "").trim();
      if (reportedPortablePython.length > 0) {
        candidatePortablePythons.push(reportedPortablePython);
      }
      const derivedPortablePython = resolvePortablePythonFromRuntimeVenv(
        runtimeVenvPathEffective,
        this.deps.runtimeProcess.platform,
      );
      if (
        derivedPortablePython.length > 0 &&
        !candidatePortablePythons.includes(derivedPortablePython)
      ) {
        candidatePortablePythons.push(derivedPortablePython);
      }

      let resolvedPortablePython = "";
      for (const candidatePath of candidatePortablePythons) {
        const exists = await waitForPathExists(candidatePath, 3000, 100);
        if (exists) {
          resolvedPortablePython = candidatePath;
          break;
        }
      }
      if (resolvedPortablePython.length === 0) {
        const detail =
          candidatePortablePythons.length > 0
            ? candidatePortablePythons.join(" | ")
            : "[none]";
        return {
          ok: false,
          error: `runtime_prepare_missing_python:${detail}`,
        };
      }

      const effectiveRuntimeConfig = (prepareResult.runtimeConfigPath || "").trim();
      if (
        effectiveRuntimeConfig.length > 0 &&
        !(await waitForPathExists(effectiveRuntimeConfig, 1500, 100))
      ) {
        return {
          ok: false,
          error: `runtime_prepare_missing_config:${effectiveRuntimeConfig}`,
        };
      }

      env.MIMOLO_OPERATIONS_PYTHON = resolvedPortablePython;
      if (effectiveRuntimeConfig.length > 0) {
        env.MIMOLO_RUNTIME_CONFIG_PATH = effectiveRuntimeConfig;
      }

      return {
        ok: true,
        portablePython: resolvedPortablePython,
        runtimeConfigPath: effectiveRuntimeConfig,
      };
    })();
    const prepareResult = await this.runtimePreparePromise;
    this.runtimePreparePromise = null;
    return prepareResult;
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

    const spawnCwd = this.getSpawnCwd();

    const runtimeReady = await this.ensurePortableRuntimeReady(spawnCwd);
    if (!runtimeReady.ok) {
      const detail = runtimeReady.error || "runtime_prepare_failed";
      this.deps.setOperationsControlState("error", detail, false, null);
      return {
        ok: false,
        error: detail,
        state: this.deps.getOperationsControlState(),
      };
    }

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
