import electronDefault, * as electronNamespace from "electron";
import { spawn } from "node:child_process";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import net from "node:net";
import path from "node:path";
import type {
  AgentInstanceSnapshot,
  AgentTemplateSnapshot,
  ControlCommandPayload,
  ControlTimingSettings,
  IpcResponsePayload,
  IpcTrafficClass,
  IpcTrafficPayload,
  MonitorSettingsSnapshot,
  OperationsControlRequest,
  OperationsProcessState,
  OperationsControlSnapshot,
  OpsStatusPayload,
  PendingIpcRequest,
  RuntimeProcess,
} from "./types.js";
import { buildHtml } from "./ui_html.js";
import {
  normalizeControlTimingSettings,
  parseControlSettingsFromToml,
} from "./control_timing.js";

const electronRuntime = (
  (electronDefault as unknown as Record<string, unknown>) ??
  (electronNamespace as unknown as Record<string, unknown>)
) as Record<string, unknown>;
const electronFallback = electronNamespace as unknown as Record<string, unknown>;
const app = (electronRuntime.app ?? electronFallback.app) as typeof import("electron").app;
const BrowserWindow = (
  electronRuntime.BrowserWindow ?? electronFallback.BrowserWindow
) as typeof import("electron").BrowserWindow;
const dialog = (electronRuntime.dialog ?? electronFallback.dialog) as typeof import("electron").dialog;
const ipcMain = (electronRuntime.ipcMain ?? electronFallback.ipcMain) as typeof import("electron").ipcMain;
if (!app || !BrowserWindow || !dialog || !ipcMain) {
  throw new Error("electron_runtime_exports_unavailable");
}


const maybeRuntimeProcess = (globalThis as { process?: RuntimeProcess }).process;

if (!maybeRuntimeProcess) {
  throw new Error("Node.js process global is unavailable");
}
const runtimeProcess: RuntimeProcess = maybeRuntimeProcess;

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

const ipcPath = runtimeProcess.env.MIMOLO_IPC_PATH || "";
const opsLogPath = runtimeProcess.env.MIMOLO_OPS_LOG_PATH || "";
const controlDevMode = parseEnabledEnv(runtimeProcess.env.MIMOLO_CONTROL_DEV_MODE);

let mainWindow: InstanceType<typeof BrowserWindow> | null = null;
let logCursor = 0;
let statusTimer: ReturnType<typeof setInterval> | null = null;
let logTimer: ReturnType<typeof setInterval> | null = null;
let instanceTimer: ReturnType<typeof setInterval> | null = null;

let lastStatus: OpsStatusPayload = {
  state: "starting",
  detail: "waiting_for_operations",
  timestamp: new Date().toISOString(),
};

const DEFAULT_MONITOR_SETTINGS: MonitorSettingsSnapshot = {
  cooldown_seconds: 600,
  poll_tick_s: 0.2,
  console_verbosity: "info",
};

let lastMonitorSettings: MonitorSettingsSnapshot = { ...DEFAULT_MONITOR_SETTINGS };

let lastAgentInstances: Record<string, AgentInstanceSnapshot> = {};
let opsLogWarningPrinted = false;
let opsLogWriteQueue: Promise<void> = Promise.resolve();
let operationsProcess: ReturnType<typeof spawn> | null = null;
let operationsStopRequested = false;
let quitInProgress = false;
let operationsControlState: OperationsControlSnapshot = {
  state: "stopped",
  detail: "not_managed",
  managed: false,
  pid: null,
  timestamp: new Date().toISOString(),
};

const IPC_MAX_PENDING_REQUESTS = 256;
type IpcSocket = ReturnType<typeof net.createConnection>;

const DEFAULT_CONTROL_TIMING_SETTINGS: ControlTimingSettings = {
  indicator_fade_step_s: 0.2,
  status_poll_connected_s: 1.0,
  status_poll_disconnected_s: 5.0,
  instance_poll_connected_s: 1.0,
  instance_poll_disconnected_s: 5.0,
  log_poll_connected_s: 1.0,
  log_poll_disconnected_s: 5.0,
  ipc_request_timeout_s: 1.5,
  ipc_connect_backoff_initial_s: 1.0,
  ipc_connect_backoff_extended_s: 5.0,
  ipc_connect_backoff_escalate_after: 5,
  status_repeat_throttle_connected_s: 0.25,
  status_repeat_throttle_disconnected_s: 3.0,
  stop_wait_disconnect_poll_s: 0.15,
  stop_wait_disconnect_timeout_s: 5.0,
  stop_wait_managed_exit_s: 1.0,
  stop_wait_graceful_exit_s: 5.0,
  stop_wait_forced_exit_s: 1.5,
  template_cache_ttl_s: 3.0,
  toast_duration_s: 2.8,
  widget_auto_tick_s: 0.25,
  widget_auto_refresh_default_s: 15.0,
};

let ipcSocket: IpcSocket | null = null;
let ipcSocketState: "disconnected" | "connecting" | "connected" = "disconnected";
let ipcSocketBuffer = "";
let ipcConnectPromise: Promise<void> | null = null;
let ipcConnectResolve: (() => void) | null = null;
let ipcConnectReject: ((error: Error) => void) | null = null;
let ipcInFlightRequest: PendingIpcRequest | null = null;
let ipcQueueDrainRunning = false;
let ipcRequestCounter = 0;
let ipcLastConnectFailureAt = 0;
let ipcConnectFailureCount = 0;
let ipcNextConnectAttemptAt = 0;
const ipcPendingRequestQueue: PendingIpcRequest[] = [];
let templateCache: { fetchedAtMs: number; templates: Record<string, AgentTemplateSnapshot> } | null = null;
let templateRefreshInFlight: Promise<Record<string, AgentTemplateSnapshot>> | null = null;

let controlTimingSettings: ControlTimingSettings = { ...DEFAULT_CONTROL_TIMING_SETTINGS };
let ipcRequestTimeoutMs = Math.max(
  1,
  Math.round(DEFAULT_CONTROL_TIMING_SETTINGS.ipc_request_timeout_s * 1000),
);
let templateCacheTtlMs = Math.max(
  1,
  Math.round(DEFAULT_CONTROL_TIMING_SETTINGS.template_cache_ttl_s * 1000),
);

function applyControlTimingSettings(raw: unknown): void {
  controlTimingSettings = normalizeControlTimingSettings(
    raw,
    DEFAULT_CONTROL_TIMING_SETTINGS,
  );
  ipcRequestTimeoutMs = Math.max(
    1,
    Math.round(controlTimingSettings.ipc_request_timeout_s * 1000),
  );
  templateCacheTtlMs = Math.max(
    1,
    Math.round(controlTimingSettings.template_cache_ttl_s * 1000),
  );
}

async function loadControlTimingSettingsFromConfigFile(): Promise<void> {
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
  applyControlTimingSettings(DEFAULT_CONTROL_TIMING_SETTINGS);
}

function publishLine(line: string): void {
  if (!mainWindow) {
    return;
  }
  mainWindow.webContents.send("ops:line", line);
}

function publishTraffic(
  direction: "tx" | "rx",
  kind: IpcTrafficClass,
  label?: string,
): void {
  if (!mainWindow) {
    return;
  }
  const payload: IpcTrafficPayload = {
    direction,
    kind,
    label,
    timestamp: new Date().toISOString(),
  };
  mainWindow.webContents.send("ops:traffic", payload);
}

function publishOperationsControlState(): void {
  if (!mainWindow) {
    return;
  }
  mainWindow.webContents.send("ops:process", operationsControlState);
}

function setOperationsControlState(
  state: OperationsProcessState,
  detail: string,
  managed: boolean,
  pid: number | null,
): void {
  if (
    operationsControlState.state === state &&
    operationsControlState.detail === detail &&
    operationsControlState.managed === managed &&
    operationsControlState.pid === pid
  ) {
    return;
  }
  operationsControlState = {
    state,
    detail,
    managed,
    pid,
    timestamp: new Date().toISOString(),
  };
  publishOperationsControlState();
}

function appendOpsLogChunk(rawChunk: unknown): void {
  if (!opsLogPath) {
    return;
  }
  const chunk =
    typeof rawChunk === "string"
      ? rawChunk
      : (rawChunk && typeof rawChunk === "object" && "toString" in rawChunk
        ? String((rawChunk as { toString: () => string }).toString())
        : "");
  if (chunk.length === 0) {
    return;
  }
  opsLogWriteQueue = opsLogWriteQueue
    .then(() => writeFile(opsLogPath, chunk, { flag: "a" }))
    .catch(() => {
      // Keep the write chain alive on transient write failures.
    });
}

function quoteBashArg(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function buildOperationsStartCommand(): { args: string[]; command: string } {
  const configPath = runtimeProcess.env.MIMOLO_RUNTIME_CONFIG_PATH || "";
  const override = runtimeProcess.env.MIMOLO_OPERATIONS_START_CMD || "";
  const defaultCmd = configPath
    ? `exec poetry run python -m mimolo.cli ops --config ${quoteBashArg(configPath)}`
    : "exec poetry run python -m mimolo.cli ops";
  const shellCommand = override.trim().length > 0 ? override.trim() : defaultCmd;
  if (runtimeProcess.platform === "win32") {
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

async function startOperationsProcess(): Promise<{
  error?: string;
  ok: boolean;
  state: OperationsControlSnapshot;
}> {
  if (operationsProcess) {
    setOperationsControlState(
      "running",
      "already_running_managed",
      true,
      typeof operationsProcess.pid === "number" ? operationsProcess.pid : null,
    );
    return {
      ok: true,
      state: operationsControlState,
    };
  }

  if (lastStatus.state === "connected") {
    setOperationsControlState("running", "external_unmanaged", false, null);
    return {
      ok: false,
      error: "operations_running_unmanaged",
      state: operationsControlState,
    };
  }

  const cwdRaw = runtimeProcess.env.MIMOLO_REPO_ROOT || "";
  const spawnCwd = cwdRaw.trim().length > 0
    ? cwdRaw.trim()
    : (typeof runtimeProcess.cwd === "function" ? runtimeProcess.cwd() : undefined);

  setOperationsControlState("starting", "launching", true, null);
  if (opsLogPath) {
    try {
      await mkdir(path.dirname(opsLogPath), { recursive: true });
      await writeFile(opsLogPath, "", { flag: "a" });
      appendOpsLogChunk("\n[control] starting operations process\n");
    } catch (err) {
      const detail = err instanceof Error ? err.message : "ops_log_init_failed";
      publishLine(`[ops-log] init failed before spawn: ${detail}`);
    }
  }

  const launch = buildOperationsStartCommand();
  try {
    const child = spawn(launch.command, launch.args, {
      cwd: spawnCwd,
      env: runtimeProcess.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    operationsStopRequested = false;
    operationsProcess = child;
    setOperationsControlState(
      "running",
      "spawned_by_control",
      true,
      typeof child.pid === "number" ? child.pid : null,
    );

    if (child.stdout) {
      child.stdout.on("data", (chunk: unknown) => {
        appendOpsLogChunk(chunk);
      });
    }
    if (child.stderr) {
      child.stderr.on("data", (chunk: unknown) => {
        appendOpsLogChunk(chunk);
      });
    }

    child.on("error", (err: { message?: string }) => {
      if (operationsProcess !== child) {
        return;
      }
      operationsProcess = null;
      operationsStopRequested = false;
      const detail = err && typeof err.message === "string"
        ? err.message
        : "spawn_failed";
      setOperationsControlState("error", `spawn_error:${detail}`, true, null);
      publishLine(`[ops] spawn failed: ${detail}`);
    });

    child.on("exit", (code: number | null, signal: string | null) => {
      if (operationsProcess !== child) {
        return;
      }
      operationsProcess = null;
      const stopRequested = operationsStopRequested;
      operationsStopRequested = false;
      if (stopRequested) {
        setOperationsControlState("stopped", "stopped_by_control", false, null);
        return;
      }
      if (code === 0) {
        setOperationsControlState("stopped", "exited_clean", false, null);
        return;
      }
      const detail = `exited_unexpectedly(code=${String(code)},signal=${String(signal)})`;
      setOperationsControlState("error", detail, false, null);
    });

    return {
      ok: true,
      state: operationsControlState,
    };
  } catch (err) {
    const detail = err instanceof Error ? err.message : "spawn_failed";
    setOperationsControlState("error", `spawn_failed:${detail}`, true, null);
    return {
      ok: false,
      error: "spawn_failed",
      state: operationsControlState,
    };
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

async function waitForIpcDisconnect(timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  const pollMs = Math.max(
    1,
    Math.round(controlTimingSettings.stop_wait_disconnect_poll_s * 1000),
  );
  while (Date.now() < deadline) {
    try {
      const pingResponse = await sendIpcCommand(
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

async function requestOperationsStopOverIpc(): Promise<{
  error?: string;
  ok: boolean;
}> {
  try {
    const stopResponse = await sendIpcCommand(
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

  const disconnectTimeoutMs = Math.max(
    1,
    Math.round(controlTimingSettings.stop_wait_disconnect_timeout_s * 1000),
  );
  const disconnected = await waitForIpcDisconnect(disconnectTimeoutMs);
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

async function stopOperationsProcess(): Promise<{
  error?: string;
  ok: boolean;
  state: OperationsControlSnapshot;
}> {
  if (!operationsProcess) {
    if (lastStatus.state === "connected") {
      setOperationsControlState("stopping", "external_stop_requested", false, null);
      const stopResult = await requestOperationsStopOverIpc();
      if (!stopResult.ok) {
        setOperationsControlState("running", "external_unmanaged", false, null);
        return {
          ok: false,
          error: stopResult.error,
          state: operationsControlState,
        };
      }

      setOperationsControlState("stopped", "stopped_via_ipc", false, null);
      return {
        ok: true,
        state: operationsControlState,
      };
    }
    setOperationsControlState("stopped", "not_managed", false, null);
    return {
      ok: true,
      state: operationsControlState,
    };
  }

  const child = operationsProcess;

  if (lastStatus.state === "connected") {
    setOperationsControlState(
      "stopping",
      "managed_stop_requested_via_ipc",
      true,
      typeof child.pid === "number" ? child.pid : null,
    );
    const stopResult = await requestOperationsStopOverIpc();
    if (stopResult.ok) {
      await waitForProcessExit(
        child,
        Math.max(1, Math.round(controlTimingSettings.stop_wait_managed_exit_s * 1000)),
      );
      if (operationsProcess === child) {
        operationsProcess = null;
      }
      operationsStopRequested = false;
      setOperationsControlState("stopped", "stopped_via_ipc", false, null);
      return {
        ok: true,
        state: operationsControlState,
      };
    }
  }

  operationsStopRequested = true;
  setOperationsControlState(
    "stopping",
    "stop_requested",
    true,
    typeof child.pid === "number" ? child.pid : null,
  );

  try {
    child.kill("SIGTERM");
  } catch (err) {
    const detail = err instanceof Error ? err.message : "kill_failed";
    setOperationsControlState("error", `stop_failed:${detail}`, true, null);
    return {
      ok: false,
      error: "stop_failed",
      state: operationsControlState,
    };
  }

  const exitedGracefully = await waitForProcessExit(
    child,
    Math.max(1, Math.round(controlTimingSettings.stop_wait_graceful_exit_s * 1000)),
  );
  if (!exitedGracefully && operationsProcess === child) {
    try {
      child.kill("SIGKILL");
    } catch (err) {
      const detail = err instanceof Error ? err.message : "kill_force_failed";
      setOperationsControlState("error", `force_stop_failed:${detail}`, true, null);
      return {
        ok: false,
        error: "force_stop_failed",
        state: operationsControlState,
      };
    }
    await waitForProcessExit(
      child,
      Math.max(1, Math.round(controlTimingSettings.stop_wait_forced_exit_s * 1000)),
    );
  }

  if (operationsProcess === child) {
    operationsProcess = null;
    operationsStopRequested = false;
    setOperationsControlState("stopped", "stopped_by_control", false, null);
  }
  return {
    ok: true,
    state: operationsControlState,
  };
}

async function controlOperations(
  request: OperationsControlRequest,
): Promise<{
  error?: string;
  ok: boolean;
  state: OperationsControlSnapshot;
}> {
  if (request.action === "status") {
    return {
      ok: true,
      state: operationsControlState,
    };
  }
  if (request.action === "start") {
    return startOperationsProcess();
  }
  if (request.action === "stop") {
    return stopOperationsProcess();
  }
  if (request.action === "restart") {
    const stopResult = await stopOperationsProcess();
    if (!stopResult.ok && stopResult.error !== "operations_not_managed") {
      return stopResult;
    }
    return startOperationsProcess();
  }
  return {
    ok: false,
    error: "invalid_ops_action",
    state: operationsControlState,
  };
}

function haltManagedOperationsForShutdown(): void {
  if (!operationsProcess) {
    return;
  }
  const child = operationsProcess;
  operationsStopRequested = true;
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

function publishInstances(
  instances: Record<string, AgentInstanceSnapshot>,
): void {
  lastAgentInstances = instances;
  if (!mainWindow) {
    return;
  }
  mainWindow.webContents.send("ops:instances", { instances });
}

function normalizeDisconnectedStatusDetail(detail: string): string {
  if (detail === "ipc_connect_backoff") {
    return "waiting_for_operations";
  }
  return detail;
}

function setStatus(state: OpsStatusPayload["state"], detail: string): void {
  const normalizedDetail =
    state === "disconnected" ? normalizeDisconnectedStatusDetail(detail) : detail;
  const connectedThrottleMs = Math.max(
    1,
    Math.round(controlTimingSettings.status_repeat_throttle_connected_s * 1000),
  );
  const disconnectedThrottleMs = Math.max(
    1,
    Math.round(controlTimingSettings.status_repeat_throttle_disconnected_s * 1000),
  );
  const throttleMs =
    state === "disconnected" ? disconnectedThrottleMs : connectedThrottleMs;
  const previousTimestampMs = Date.parse(lastStatus.timestamp);
  const elapsedMs = Number.isNaN(previousTimestampMs)
    ? Number.POSITIVE_INFINITY
    : Date.now() - previousTimestampMs;
  if (
    lastStatus.state === state &&
    lastStatus.detail === normalizedDetail &&
    elapsedMs < throttleMs
  ) {
    return;
  }

  lastStatus = {
    state,
    detail: normalizedDetail,
    timestamp: new Date().toISOString(),
  };
  if (!mainWindow) {
    return;
  }
  mainWindow.webContents.send("ops:status", lastStatus);
}

function resetIpcConnectBackoff(): void {
  ipcConnectFailureCount = 0;
  ipcLastConnectFailureAt = 0;
  ipcNextConnectAttemptAt = 0;
}

function recordIpcConnectFailure(): void {
  ipcConnectFailureCount += 1;
  const backoffSeconds =
    ipcConnectFailureCount >= controlTimingSettings.ipc_connect_backoff_escalate_after
      ? controlTimingSettings.ipc_connect_backoff_extended_s
      : controlTimingSettings.ipc_connect_backoff_initial_s;
  const backoffMs = Math.max(1, Math.round(backoffSeconds * 1000));
  const now = Date.now();
  ipcLastConnectFailureAt = now;
  ipcNextConnectAttemptAt = now + backoffMs;
}

function parseIpcResponse(rawLine: string): IpcResponsePayload {
  if (rawLine.length === 0) {
    throw new Error("empty_response");
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(rawLine);
  } catch {
    throw new Error("invalid_json_response");
  }

  if (!parsed || typeof parsed !== "object") {
    throw new Error("invalid_response_shape");
  }

  const record = parsed as Record<string, unknown>;
  return {
    ok: record.ok === true,
    cmd: typeof record.cmd === "string" ? record.cmd : undefined,
    timestamp: typeof record.timestamp === "string" ? record.timestamp : undefined,
    request_id:
      typeof record.request_id === "string" ? record.request_id : undefined,
    error: typeof record.error === "string" ? record.error : undefined,
    data:
      record.data && typeof record.data === "object"
        ? (record.data as Record<string, unknown>)
        : undefined,
  };
}

function extractAgentInstances(
  response: IpcResponsePayload,
): Record<string, AgentInstanceSnapshot> {
  const result: Record<string, AgentInstanceSnapshot> = {};
  const instancesRaw = response.data?.instances;
  if (!instancesRaw || typeof instancesRaw !== "object") {
    return result;
  }

  const map = instancesRaw as Record<string, unknown>;
  for (const [label, raw] of Object.entries(map)) {
    if (!raw || typeof raw !== "object") {
      continue;
    }
    const entry = raw as Record<string, unknown>;
    const stateRaw = entry.state;
    const detailRaw = entry.detail;
    const configRaw = entry.config;
    const templateRaw = entry.template_id;
    const state =
      stateRaw === "running" ||
      stateRaw === "shutting-down" ||
      stateRaw === "inactive" ||
      stateRaw === "error"
        ? stateRaw
        : "inactive";
    const detail = typeof detailRaw === "string" ? detailRaw : "configured";
    const config =
      configRaw && typeof configRaw === "object"
        ? (configRaw as Record<string, unknown>)
        : {};
    const template_id =
      typeof templateRaw === "string" ? templateRaw : label;
    result[label] = {
      label,
      state,
      detail,
      config,
      template_id,
    };
  }

  return result;
}

function extractTemplates(
  response: IpcResponsePayload,
): Record<string, AgentTemplateSnapshot> {
  const result: Record<string, AgentTemplateSnapshot> = {};
  const templatesRaw = response.data?.templates;
  if (!templatesRaw || typeof templatesRaw !== "object") {
    return result;
  }

  const map = templatesRaw as Record<string, unknown>;
  for (const [templateId, raw] of Object.entries(map)) {
    if (!raw || typeof raw !== "object") {
      continue;
    }
    const entry = raw as Record<string, unknown>;
    const scriptRaw = entry.script;
    const defaultRaw = entry.default_config;
    const default_config =
      defaultRaw && typeof defaultRaw === "object"
        ? (defaultRaw as Record<string, unknown>)
        : {};
    result[templateId] = {
      template_id: templateId,
      script: typeof scriptRaw === "string" ? scriptRaw : "",
      default_config,
    };
  }

  return result;
}

function normalizeMonitorSettings(raw: unknown): MonitorSettingsSnapshot {
  if (!raw || typeof raw !== "object") {
    return { ...DEFAULT_MONITOR_SETTINGS };
  }
  const record = raw as Record<string, unknown>;

  const cooldownRaw = record.cooldown_seconds;
  const pollTickRaw = record.poll_tick_s;
  const verbosityRaw = record.console_verbosity;

  const cooldownParsed =
    typeof cooldownRaw === "number" && Number.isFinite(cooldownRaw) && cooldownRaw > 0
      ? cooldownRaw
      : DEFAULT_MONITOR_SETTINGS.cooldown_seconds;
  const pollTickParsed =
    typeof pollTickRaw === "number" && Number.isFinite(pollTickRaw) && pollTickRaw > 0
      ? pollTickRaw
      : DEFAULT_MONITOR_SETTINGS.poll_tick_s;
  const verbosityParsed =
    verbosityRaw === "debug" ||
    verbosityRaw === "info" ||
    verbosityRaw === "warning" ||
    verbosityRaw === "error"
      ? verbosityRaw
      : DEFAULT_MONITOR_SETTINGS.console_verbosity;

  return {
    cooldown_seconds: cooldownParsed,
    poll_tick_s: pollTickParsed,
    console_verbosity: verbosityParsed,
  };
}

function deriveStatusLoopMs(settings: MonitorSettingsSnapshot): number {
  if (lastStatus.state !== "connected") {
    return Math.max(
      1,
      Math.round(controlTimingSettings.status_poll_disconnected_s * 1000),
    );
  }
  return Math.max(
    Math.round(settings.poll_tick_s * 1000),
    Math.round(controlTimingSettings.status_poll_connected_s * 1000),
  );
}

function deriveInstanceLoopMs(settings: MonitorSettingsSnapshot): number {
  if (lastStatus.state !== "connected") {
    return Math.max(
      1,
      Math.round(controlTimingSettings.instance_poll_disconnected_s * 1000),
    );
  }
  return Math.max(
    Math.round(settings.poll_tick_s * 1000),
    Math.round(controlTimingSettings.instance_poll_connected_s * 1000),
  );
}

function deriveLogLoopMs(settings: MonitorSettingsSnapshot): number {
  if (lastStatus.state !== "connected") {
    return Math.max(
      1,
      Math.round(controlTimingSettings.log_poll_disconnected_s * 1000),
    );
  }
  return Math.max(
    Math.round(settings.poll_tick_s * 1000),
    Math.round(controlTimingSettings.log_poll_connected_s * 1000),
  );
}

function publishMonitorSettings(): void {
  if (!mainWindow) {
    return;
  }
  mainWindow.webContents.send("ops:monitor-settings", {
    monitor: lastMonitorSettings,
  });
}

async function sendIpcCommand(
  cmd: string,
  extraPayload?: Record<string, unknown>,
  trafficLabel?: string,
  trafficClass: IpcTrafficClass = "interactive",
): Promise<IpcResponsePayload> {
  if (!ipcPath) {
    throw new Error("MIMOLO_IPC_PATH not set");
  }

  const providedRequestId =
    extraPayload && typeof extraPayload.request_id === "string" && extraPayload.request_id.trim().length > 0
      ? extraPayload.request_id.trim()
      : "";
  const requestId = providedRequestId || `ctrl-${Date.now()}-${++ipcRequestCounter}`;

  const requestPayload: Record<string, unknown> = {
    cmd,
    ...(extraPayload || {}),
    request_id: requestId,
  };

  return new Promise<IpcResponsePayload>((resolve, reject) => {
    if (ipcPendingRequestQueue.length >= IPC_MAX_PENDING_REQUESTS) {
      reject(new Error("ipc_queue_overloaded"));
      return;
    }

    ipcPendingRequestQueue.push({
      id: requestId,
      payload: requestPayload,
      resolve,
      reject,
      timeoutHandle: null,
      trafficClass,
      trafficLabel,
    });

    void drainIpcQueue();
  });
}

function clearRequestTimeout(request: PendingIpcRequest): void {
  if (!request.timeoutHandle) {
    return;
  }
  clearTimeout(request.timeoutHandle);
  request.timeoutHandle = null;
}

function settleInFlightWithError(reason: string): void {
  if (!ipcInFlightRequest) {
    return;
  }
  const request = ipcInFlightRequest;
  ipcInFlightRequest = null;
  clearRequestTimeout(request);
  request.reject(new Error(reason));
}

function rejectPendingQueue(reason: string): void {
  while (ipcPendingRequestQueue.length > 0) {
    const pending = ipcPendingRequestQueue.shift();
    if (!pending) {
      continue;
    }
    clearRequestTimeout(pending);
    pending.reject(new Error(reason));
  }
}

function handleIpcSocketDisconnect(reason: string): void {
  if (ipcSocket) {
    ipcSocket.removeAllListeners();
    ipcSocket.destroy();
    ipcSocket = null;
  }

  ipcSocketBuffer = "";
  ipcSocketState = "disconnected";
  if (ipcConnectReject) {
    ipcConnectReject(new Error(reason));
  }
  ipcConnectPromise = null;
  ipcConnectResolve = null;
  ipcConnectReject = null;
  recordIpcConnectFailure();

  settleInFlightWithError(reason);
  rejectPendingQueue(reason);
}

function resolveInFlightResponse(response: IpcResponsePayload): void {
  if (!ipcInFlightRequest) {
    publishLine(`[ipc] unsolicited response: ${JSON.stringify(response)}`);
    return;
  }

  const request = ipcInFlightRequest;
  const responseRequestId = response.request_id;
  if (responseRequestId && responseRequestId !== request.id) {
    publishLine(
      `[ipc] request_id mismatch: expected=${request.id} got=${responseRequestId}`,
    );
    return;
  }

  ipcInFlightRequest = null;
  clearRequestTimeout(request);
  publishTraffic("rx", request.trafficClass, request.trafficLabel);
  request.resolve(response);
  void drainIpcQueue();
}

function parseIpcSocketBuffer(): void {
  while (true) {
    const newlineIndex = ipcSocketBuffer.indexOf("\n");
    if (newlineIndex < 0) {
      return;
    }
    const rawLine = ipcSocketBuffer.slice(0, newlineIndex).trim();
    ipcSocketBuffer = ipcSocketBuffer.slice(newlineIndex + 1);
    if (rawLine.length === 0) {
      continue;
    }
    try {
      const parsed = parseIpcResponse(rawLine);
      resolveInFlightResponse(parsed);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "invalid_response";
      settleInFlightWithError(detail);
      void drainIpcQueue();
    }
  }
}

async function ensureIpcConnection(): Promise<void> {
  if (!ipcPath) {
    throw new Error("MIMOLO_IPC_PATH not set");
  }

  if (ipcSocketState === "connected" && ipcSocket) {
    return;
  }

  if (ipcSocketState === "connecting" && ipcConnectPromise) {
    return ipcConnectPromise;
  }
  const now = Date.now();
  if (now < ipcNextConnectAttemptAt) {
    throw new Error("ipc_connect_backoff");
  }

  ipcSocketState = "connecting";
  ipcConnectPromise = new Promise<void>((resolve, reject) => {
    ipcConnectResolve = resolve;
    ipcConnectReject = reject;
  });

  const socket = net.createConnection({ path: ipcPath });
  socket.setEncoding("utf8");
  ipcSocket = socket;

  socket.on("connect", () => {
    ipcSocketState = "connected";
    resetIpcConnectBackoff();
    const resolver = ipcConnectResolve;
    ipcConnectResolve = null;
    ipcConnectReject = null;
    ipcConnectPromise = null;
    if (resolver) {
      resolver();
    }
  });

  socket.on("data", (chunk: string) => {
    ipcSocketBuffer += chunk;
    parseIpcSocketBuffer();
  });

  socket.on("error", (err: { message: string }) => {
    const reason = err.message || "ipc_socket_error";
    handleIpcSocketDisconnect(reason);
  });

  socket.on("close", () => {
    handleIpcSocketDisconnect("ipc_socket_closed");
  });

  return ipcConnectPromise;
}

async function drainIpcQueue(): Promise<void> {
  if (ipcQueueDrainRunning) {
    return;
  }
  ipcQueueDrainRunning = true;

  try {
    while (!ipcInFlightRequest && ipcPendingRequestQueue.length > 0) {
      try {
        await ensureIpcConnection();
      } catch (err) {
        const detail = err instanceof Error ? err.message : "ipc_connect_failed";
        if (detail !== "ipc_connect_backoff") {
          setStatus("disconnected", detail);
        }
        rejectPendingQueue(detail);
        return;
      }

      const nextRequest = ipcPendingRequestQueue.shift();
      if (!nextRequest || !ipcSocket) {
        return;
      }

      ipcInFlightRequest = nextRequest;
      publishTraffic("tx", nextRequest.trafficClass, nextRequest.trafficLabel);
      nextRequest.timeoutHandle = setTimeout(() => {
        const timeoutRequest = ipcInFlightRequest;
        if (!timeoutRequest || timeoutRequest.id !== nextRequest.id) {
          return;
        }
        handleIpcSocketDisconnect("timeout");
        void drainIpcQueue();
      }, ipcRequestTimeoutMs);

      try {
        ipcSocket.write(`${JSON.stringify(nextRequest.payload)}\n`);
      } catch (err) {
        const detail = err instanceof Error ? err.message : "ipc_write_failed";
        handleIpcSocketDisconnect(detail);
        nextRequest.reject(new Error(detail));
        void drainIpcQueue();
      }

      return;
    }
  } finally {
    ipcQueueDrainRunning = false;
  }
}

function stopPersistentIpc(): void {
  if (ipcSocket) {
    ipcSocket.removeAllListeners();
    ipcSocket.destroy();
    ipcSocket = null;
  }
  ipcSocketBuffer = "";
  ipcSocketState = "disconnected";
  if (ipcConnectReject) {
    ipcConnectReject(new Error("control_shutdown"));
  }
  ipcConnectPromise = null;
  ipcConnectResolve = null;
  ipcConnectReject = null;

  if (ipcInFlightRequest) {
    const inflight = ipcInFlightRequest;
    ipcInFlightRequest = null;
    clearRequestTimeout(inflight);
    inflight.reject(new Error("control_shutdown"));
  }

  while (ipcPendingRequestQueue.length > 0) {
    const pending = ipcPendingRequestQueue.shift();
    if (!pending) {
      continue;
    }
    clearRequestTimeout(pending);
    pending.reject(new Error("control_shutdown"));
  }
}

async function refreshIpcStatus(): Promise<void> {
  try {
    const response = await sendIpcCommand("ping", undefined, undefined, "background");
    if (response.ok) {
      setStatus("connected", "ipc_ready");
      if (!operationsProcess) {
        if (
          operationsControlState.state !== "stopping" ||
          operationsControlState.detail !== "external_stop_requested"
        ) {
          setOperationsControlState("running", "external_unmanaged", false, null);
        }
      }
      return;
    }
    setStatus("disconnected", response.error || "ipc_unavailable");
    if (!operationsProcess) {
      if (
        operationsControlState.state === "stopping" &&
        operationsControlState.detail === "external_stop_requested"
      ) {
        setOperationsControlState("stopped", "stopped_via_ipc", false, null);
      } else {
        setOperationsControlState("stopped", "not_managed", false, null);
      }
    }
  } catch (err) {
    const detail = err instanceof Error ? err.message : "ipc_unavailable";
    setStatus("disconnected", detail);
    if (!operationsProcess) {
      if (
        operationsControlState.state === "stopping" &&
        operationsControlState.detail === "external_stop_requested"
      ) {
        setOperationsControlState("stopped", "stopped_via_ipc", false, null);
      } else {
        setOperationsControlState("stopped", "not_managed", false, null);
      }
    }
  }
}

async function refreshAgentInstances(): Promise<void> {
  if (lastStatus.state !== "connected") {
    return;
  }
  try {
    const response = await sendIpcCommand(
      "get_agent_instances",
      undefined,
      undefined,
      "background",
    );
    if (!response.ok) {
      return;
    }
    publishInstances(extractAgentInstances(response));
  } catch {
    // Ignore transient polling failures; status loop reports IPC health.
  }
}

async function refreshTemplates(): Promise<Record<string, AgentTemplateSnapshot>> {
  const response = await sendIpcCommand(
    "list_agent_templates",
    undefined,
    undefined,
    "background",
  );
  if (!response.ok) {
    return {};
  }
  return extractTemplates(response);
}

async function refreshTemplatesCached(forceRefresh = false): Promise<Record<string, AgentTemplateSnapshot>> {
  const now = Date.now();
  if (
    !forceRefresh &&
    templateCache &&
    now - templateCache.fetchedAtMs < templateCacheTtlMs
  ) {
    return templateCache.templates;
  }
  if (templateRefreshInFlight) {
    return templateRefreshInFlight;
  }
  templateRefreshInFlight = (async () => {
    const templates = await refreshTemplates();
    templateCache = {
      templates,
      fetchedAtMs: Date.now(),
    };
    return templates;
  })();
  try {
    return await templateRefreshInFlight;
  } finally {
    templateRefreshInFlight = null;
  }
}

async function refreshMonitorSettings(): Promise<void> {
  try {
    const response = await sendIpcCommand(
      "get_monitor_settings",
      undefined,
      undefined,
      "background",
    );
    if (!response.ok) {
      return;
    }
    const monitorRaw = response.data?.monitor;
    const controlRaw = response.data?.control;
    lastMonitorSettings = normalizeMonitorSettings(monitorRaw);
    applyControlTimingSettings(controlRaw);
    publishMonitorSettings();
    restartBackgroundTimers();
  } catch {
    // Ignore transient failures; status and loop timers continue with last known settings.
  }
}

async function updateMonitorSettings(
  updates: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  const response = await sendIpcCommand("update_monitor_settings", { updates });
  if (!response.ok) {
    return response;
  }

  const monitorRaw = response.data?.monitor;
  const controlRaw = response.data?.control;
  lastMonitorSettings = normalizeMonitorSettings(monitorRaw);
  applyControlTimingSettings(controlRaw);
  publishMonitorSettings();
  restartBackgroundTimers();
  return response;
}

async function pumpOpsLog(): Promise<void> {
  if (!opsLogPath) {
    return;
  }

  try {
    const fileStats = await stat(opsLogPath);
    if (fileStats.size === 0) {
      logCursor = 0;
      return;
    }

    const fullText = await readFile(opsLogPath, "utf8");
    if (fullText.length < logCursor) {
      logCursor = 0;
    }

    if (fullText.length === logCursor) {
      return;
    }

    const slice = fullText.slice(logCursor);
    logCursor = fullText.length;

    const lines = slice.split(/\r?\n/);
    for (const line of lines) {
      if (line.trim().length > 0) {
        publishLine(line);
      }
    }
  } catch (err) {
    if (
      err &&
      typeof err === "object" &&
      "code" in err &&
      (err as { code?: string }).code === "ENOENT"
    ) {
      if (!opsLogWarningPrinted) {
        publishLine(`[ops-log] waiting for file: ${opsLogPath}`);
        opsLogWarningPrinted = true;
      }
      return;
    }
    const detail = err instanceof Error ? err.message : "ops_log_read_failed";
    publishLine(`[ops-log] read failed: ${detail}`);
  }
}

async function loadInitialSnapshot(): Promise<void> {
  if (opsLogPath) {
    try {
      await mkdir(path.dirname(opsLogPath), { recursive: true });
      await writeFile(opsLogPath, "", { flag: "a" });
    } catch (err) {
      const detail = err instanceof Error ? err.message : "ops_log_init_failed";
      publishLine(`[ops-log] init failed: ${detail}`);
    }
  }
  await refreshIpcStatus();
  if (lastStatus.state === "connected") {
    await refreshMonitorSettings();
  }
  try {
    const registeredResponse = await sendIpcCommand(
      "get_registered_plugins",
      undefined,
      undefined,
      "background",
    );
    publishLine(`[ipc] ${JSON.stringify(registeredResponse)}`);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "plugin_query_failed";
    publishLine(`[ipc] get_registered_plugins failed: ${detail}`);
  }

  await refreshAgentInstances();
  await refreshTemplates();
}

async function runAgentCommand(
  payload: ControlCommandPayload,
): Promise<IpcResponsePayload> {
  const extra: Record<string, unknown> = {};
  if (payload.label) {
    extra.label = payload.label;
  }
  if (payload.template_id) {
    extra.template_id = payload.template_id;
  }
  if (payload.requested_label) {
    extra.requested_label = payload.requested_label;
  }
  if (payload.updates) {
    extra.updates = payload.updates;
  }
  const trafficLabel = payload.label;
  const response = await sendIpcCommand(payload.action, extra, trafficLabel);
  await refreshAgentInstances();
  return response;
}

function coerceNonEmptyString(raw: unknown): string | null {
  if (typeof raw !== "string") {
    return null;
  }
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function coerceBoolean(raw: unknown): boolean {
  if (typeof raw === "boolean") {
    return raw;
  }
  if (typeof raw !== "string") {
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

async function getWidgetManifest(
  payload: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  const pluginId = coerceNonEmptyString(payload.plugin_id);
  const instanceId = coerceNonEmptyString(payload.instance_id);
  if (!pluginId || !instanceId) {
    return {
      ok: false,
      error: !pluginId ? "missing_plugin_id" : "missing_instance_id",
    };
  }
  const isManual = coerceBoolean(payload.manual);
  return sendIpcCommand(
    "get_widget_manifest",
    {
      plugin_id: pluginId,
      instance_id: instanceId,
    },
    instanceId,
    isManual ? "interactive" : "background",
  );
}

async function requestWidgetRender(
  payload: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  const pluginId = coerceNonEmptyString(payload.plugin_id);
  const instanceId = coerceNonEmptyString(payload.instance_id);
  if (!pluginId || !instanceId) {
    return {
      ok: false,
      error: !pluginId ? "missing_plugin_id" : "missing_instance_id",
    };
  }

  const requestId = coerceNonEmptyString(payload.request_id);
  const mode = coerceNonEmptyString(payload.mode) || "html_fragment_v1";
  const isManual = coerceBoolean(payload.manual);
  const canvasRaw = payload.canvas;
  const canvas =
    canvasRaw && typeof canvasRaw === "object"
      ? (canvasRaw as Record<string, unknown>)
      : {};

  return sendIpcCommand(
    "request_widget_render",
    {
      plugin_id: pluginId,
      instance_id: instanceId,
      request_id: requestId || `${instanceId}-${Date.now()}`,
      mode,
      canvas,
    },
    instanceId,
    isManual ? "interactive" : "background",
  );
}

async function inspectPluginArchive(
  payload: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  if (!controlDevMode) {
    return {
      ok: false,
      error: "dev_mode_required",
      data: {
        detail:
          "plugin zip inspection/install is disabled outside developer mode",
      },
    };
  }
  const zipPath = coerceNonEmptyString(payload.zip_path);
  if (!zipPath) {
    return {
      ok: false,
      error: "missing_zip_path",
    };
  }
  return sendIpcCommand("inspect_plugin_archive", {
    zip_path: zipPath,
  });
}

async function installPluginArchive(
  payload: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  if (!controlDevMode) {
    return {
      ok: false,
      error: "dev_mode_required",
      data: {
        detail:
          "plugin zip inspection/install is disabled outside developer mode",
      },
    };
  }
  const zipPath = coerceNonEmptyString(payload.zip_path);
  if (!zipPath) {
    return {
      ok: false,
      error: "missing_zip_path",
    };
  }

  const actionRaw = coerceNonEmptyString(payload.action);
  const cmd = actionRaw === "upgrade" ? "upgrade_plugin" : "install_plugin";
  const pluginClassRaw = coerceNonEmptyString(payload.plugin_class) || "agents";
  const pluginClass = pluginClassRaw.toLowerCase();
  if (
    pluginClass !== "agents" &&
    pluginClass !== "reporters" &&
    pluginClass !== "widgets"
  ) {
    return {
      ok: false,
      error: "invalid_plugin_class",
    };
  }

  return sendIpcCommand(cmd, {
    zip_path: zipPath,
    plugin_class: pluginClass,
  });
}

function restartBackgroundTimers(): void {
  if (statusTimer) {
    clearInterval(statusTimer);
    statusTimer = null;
  }
  if (logTimer) {
    clearInterval(logTimer);
    logTimer = null;
  }
  if (instanceTimer) {
    clearInterval(instanceTimer);
    instanceTimer = null;
  }

  const statusMs = deriveStatusLoopMs(lastMonitorSettings);
  const logMs = deriveLogLoopMs(lastMonitorSettings);
  const instanceMs = deriveInstanceLoopMs(lastMonitorSettings);

  statusTimer = setInterval(() => {
    void refreshIpcStatus();
  }, statusMs);

  logTimer = setInterval(() => {
    void pumpOpsLog();
  }, logMs);

  instanceTimer = setInterval(() => {
    void refreshAgentInstances();
  }, instanceMs);
}

function startBackgroundLoops(): void {
  void loadInitialSnapshot();
  void pumpOpsLog();
  void refreshAgentInstances();
  restartBackgroundTimers();
}

function stopBackgroundLoops(): void {
  if (statusTimer) {
    clearInterval(statusTimer);
    statusTimer = null;
  }
  if (logTimer) {
    clearInterval(logTimer);
    logTimer = null;
  }
  if (instanceTimer) {
    clearInterval(instanceTimer);
    instanceTimer = null;
  }
  stopPersistentIpc();
}

function operationsMayBeRunning(): boolean {
  if (operationsProcess) {
    return true;
  }
  if (lastStatus.state === "connected") {
    return true;
  }
  return (
    operationsControlState.state === "running" ||
    operationsControlState.state === "starting" ||
    operationsControlState.state === "stopping"
  );
}

async function handleQuitRequest(event: { preventDefault: () => void }): Promise<void> {
  if (quitInProgress) {
    return;
  }
  if (!operationsMayBeRunning()) {
    stopBackgroundLoops();
    quitInProgress = true;
    app.quit();
    return;
  }

  event.preventDefault();
  const prompt = await dialog.showMessageBox(mainWindow ?? undefined, {
    type: "question",
    buttons: [
      "Shutdown Operations + Agents",
      "Leave Operations Running",
      "Cancel",
    ],
    defaultId: 0,
    cancelId: 2,
    noLink: true,
    title: "Quit MiMoLo Control Proto",
    message: "Operations appears active. Choose quit behavior.",
    detail:
      "Shutdown will gracefully stop Operations and all Agents before closing Control.",
  });

  if (prompt.response === 2) {
    return;
  }

  if (prompt.response === 0) {
    const stopResult = await controlOperations({ action: "stop" });
    if (!stopResult.ok) {
      await dialog.showMessageBox(mainWindow ?? undefined, {
        type: "error",
        buttons: ["OK"],
        defaultId: 0,
        noLink: true,
        title: "Shutdown Failed",
        message: "Unable to stop Operations cleanly.",
        detail: stopResult.error || "unknown_error",
      });
      return;
    }
  }

  stopBackgroundLoops();
  quitInProgress = true;
  app.quit();
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 820,
    minWidth: 1080,
    minHeight: 660,
    backgroundColor: "#0e1014",
    webPreferences: {
      contextIsolation: false,
      nodeIntegration: true,
      sandbox: false,
    },
  });

  const html = buildHtml(controlTimingSettings, controlDevMode);
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

ipcMain.handle("mml:initial-state", () => {
  return {
    ipcPath,
    opsLogPath,
    status: lastStatus,
    opsControl: operationsControlState,
    monitorSettings: lastMonitorSettings,
    controlSettings: controlTimingSettings,
    instances: lastAgentInstances,
  };
});

ipcMain.handle("mml:reset-reconnect-backoff", () => {
  resetIpcConnectBackoff();
  return { ok: true };
});

ipcMain.handle("mml:ops-control", async (_event, payload: unknown) => {
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      error: "invalid_ops_payload",
      state: operationsControlState,
    };
  }
  const raw = payload as Record<string, unknown>;
  const actionRaw = raw.action;
  if (
    actionRaw !== "start" &&
    actionRaw !== "stop" &&
    actionRaw !== "restart" &&
    actionRaw !== "status"
  ) {
    return {
      ok: false,
      error: "invalid_ops_action",
      state: operationsControlState,
    };
  }
  return controlOperations({
    action: actionRaw,
  });
});

ipcMain.handle("mml:list-agent-templates", async () => {
  try {
    const templates = await refreshTemplatesCached(false);
    return {
      ok: true,
      templates,
    };
  } catch (err) {
    const detail = err instanceof Error ? err.message : "template_query_failed";
    return {
      ok: false,
      error: detail,
      templates: {},
    };
  }
});

ipcMain.handle("mml:get-monitor-settings", async () => {
  try {
    await refreshMonitorSettings();
    return {
      ok: true,
      monitor: lastMonitorSettings,
    };
  } catch (err) {
    const detail = err instanceof Error ? err.message : "monitor_query_failed";
    return {
      ok: false,
      error: detail,
    };
  }
});

ipcMain.handle("mml:update-monitor-settings", async (_event, payload: unknown) => {
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      error: "invalid_monitor_payload",
    };
  }
  const raw = payload as Record<string, unknown>;
  const updatesRaw = raw.updates;
  if (!updatesRaw || typeof updatesRaw !== "object") {
    return {
      ok: false,
      error: "missing_updates",
    };
  }
  try {
    return await updateMonitorSettings(updatesRaw as Record<string, unknown>);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "monitor_update_failed";
    return {
      ok: false,
      error: detail,
    };
  }
});

ipcMain.handle("mml:get-widget-manifest", async (_event, payload: unknown) => {
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      error: "invalid_widget_payload",
    };
  }
  try {
    return await getWidgetManifest(payload as Record<string, unknown>);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "widget_manifest_failed";
    return {
      ok: false,
      error: detail,
    };
  }
});

ipcMain.handle("mml:request-widget-render", async (_event, payload: unknown) => {
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      error: "invalid_widget_payload",
    };
  }
  try {
    return await requestWidgetRender(payload as Record<string, unknown>);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "widget_render_failed";
    return {
      ok: false,
      error: detail,
    };
  }
});

ipcMain.handle("mml:pick-plugin-archive", async () => {
  if (!controlDevMode) {
    return {
      ok: false,
      error: "dev_mode_required",
      detail: "plugin zip install is disabled outside developer mode",
    };
  }
  if (!mainWindow) {
    return {
      ok: false,
      error: "window_unavailable",
    };
  }
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Select MiMoLo plugin archive",
    properties: ["openFile"],
    filters: [{ name: "Zip archives", extensions: ["zip"] }],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return {
      ok: true,
      zip_path: null,
    };
  }
  return {
    ok: true,
    zip_path: result.filePaths[0],
  };
});

ipcMain.handle("mml:inspect-plugin-archive", (_event, payload: unknown) => {
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      error: "invalid_plugin_payload",
    };
  }
  return inspectPluginArchive(payload as Record<string, unknown>);
});

ipcMain.handle("mml:install-plugin", (_event, payload: unknown) => {
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      error: "invalid_plugin_payload",
    };
  }
  return installPluginArchive(payload as Record<string, unknown>);
});

ipcMain.handle("mml:agent-command", (_event, payload: unknown) => {
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      error: "invalid_command_payload",
    };
  }

  const raw = payload as Record<string, unknown>;
  const actionRaw = raw.action;
  if (
    actionRaw !== "start_agent" &&
    actionRaw !== "stop_agent" &&
    actionRaw !== "restart_agent" &&
    actionRaw !== "add_agent_instance" &&
    actionRaw !== "duplicate_agent_instance" &&
    actionRaw !== "remove_agent_instance" &&
    actionRaw !== "update_agent_instance"
  ) {
    return {
      ok: false,
      error: "invalid_action",
    };
  }

  const cmd: ControlCommandPayload = {
    action: actionRaw,
  };

  const labelRaw = raw.label;
  if (typeof labelRaw === "string" && labelRaw.trim().length > 0) {
    cmd.label = labelRaw.trim();
  }
  const templateRaw = raw.template_id;
  if (typeof templateRaw === "string" && templateRaw.trim().length > 0) {
    cmd.template_id = templateRaw.trim();
  }
  const requestedLabelRaw = raw.requested_label;
  if (
    typeof requestedLabelRaw === "string" &&
    requestedLabelRaw.trim().length > 0
  ) {
    cmd.requested_label = requestedLabelRaw.trim();
  }
  const updatesRaw = raw.updates;
  if (updatesRaw && typeof updatesRaw === "object") {
    cmd.updates = updatesRaw as Record<string, unknown>;
  }

  return runAgentCommand(cmd).catch((err: unknown) => {
    const detail = err instanceof Error ? err.message : "agent_command_failed";
    return {
      ok: false,
      error: detail,
    };
  });
});

app.whenReady().then(async () => {
  await loadControlTimingSettingsFromConfigFile();
  createWindow();
  startBackgroundLoops();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", () => {
  // Actual quit handling is centralized in `will-quit` to allow async prompt logic.
});

app.on("window-all-closed", () => {
  if (runtimeProcess.platform !== "darwin") {
    app.quit();
  }
});

app.on("will-quit", (event) => {
  void handleQuitRequest(event);
});
