import electronDefault, * as electronNamespace from "electron";
import { readFile, writeFile } from "node:fs/promises";
import type {
  AgentInstanceSnapshot,
  AgentTemplateSnapshot,
  ControlCommandPayload,
  ControlTimingSettings,
  IpcResponsePayload,
  IpcTrafficClass,
  IpcTrafficPayload,
  MonitorSettingsSnapshot,
  OperationsControlSnapshot,
  OperationsProcessState,
  OpsStatusPayload,
  RuntimeProcess,
} from "./types.js";
import { buildHtml } from "./ui_html.js";
import {
  normalizeControlTimingSettings,
  parseControlSettingsFromToml,
} from "./control_timing.js";
import {
  deriveInstanceLoopMs,
  deriveLogLoopMs,
  deriveStatusLoopMs,
  extractAgentInstances,
  extractTemplates,
  normalizeDisconnectedStatusDetail,
  normalizeMonitorSettings,
  parseIpcResponse,
} from "./control_proto_utils.js";
import {
  getWidgetManifestWrapper,
  inspectPluginArchiveWrapper,
  installPluginArchiveWrapper,
  requestWidgetRenderWrapper,
  runAgentCommandWrapper,
} from "./control_command_wrappers.js";
import { PersistentIpcClient } from "./control_persistent_ipc.js";
import { OperationsController } from "./control_operations.js";
import { registerIpcHandlers } from "./control_ipc_handlers.js";
import { OpsLogTailer } from "./control_ops_log_tailer.js";
import { TemplateCache } from "./control_template_cache.js";
import { BackgroundLoopController } from "./control_background_loops.js";

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
let opsLogWriteQueue: Promise<void> = Promise.resolve();
let quitInProgress = false;
let operationsControlState: OperationsControlSnapshot = {
  state: "stopped",
  detail: "not_managed",
  managed: false,
  pid: null,
  timestamp: new Date().toISOString(),
};

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

let controlTimingSettings: ControlTimingSettings = { ...DEFAULT_CONTROL_TIMING_SETTINGS };
let templateCacheTtlMs = Math.max(
  1,
  Math.round(DEFAULT_CONTROL_TIMING_SETTINGS.template_cache_ttl_s * 1000),
);
const templateCache = new TemplateCache(() => templateCacheTtlMs);

function applyControlTimingSettings(raw: unknown): void {
  controlTimingSettings = normalizeControlTimingSettings(
    raw,
    DEFAULT_CONTROL_TIMING_SETTINGS,
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

const opsLogTailer = new OpsLogTailer(opsLogPath, publishLine);

function publishInstances(
  instances: Record<string, AgentInstanceSnapshot>,
): void {
  lastAgentInstances = instances;
  if (!mainWindow) {
    return;
  }
  mainWindow.webContents.send("ops:instances", { instances });
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

function publishMonitorSettings(): void {
  if (!mainWindow) {
    return;
  }
  mainWindow.webContents.send("ops:monitor-settings", {
    monitor: lastMonitorSettings,
  });
}

const persistentIpcClient = new PersistentIpcClient({
  ipcPath,
  parseResponse: parseIpcResponse,
  publishLine,
  publishTraffic,
  getTimingSnapshot: () => ({
    requestTimeoutMs: Math.max(
      1,
      Math.round(controlTimingSettings.ipc_request_timeout_s * 1000),
    ),
    backoffInitialMs: Math.max(
      1,
      Math.round(controlTimingSettings.ipc_connect_backoff_initial_s * 1000),
    ),
    backoffExtendedMs: Math.max(
      1,
      Math.round(controlTimingSettings.ipc_connect_backoff_extended_s * 1000),
    ),
    backoffEscalateAfter: Math.max(
      1,
      Math.floor(controlTimingSettings.ipc_connect_backoff_escalate_after),
    ),
  }),
});

async function sendIpcCommand(
  cmd: string,
  extraPayload?: Record<string, unknown>,
  trafficLabel?: string,
  trafficClass: IpcTrafficClass = "interactive",
): Promise<IpcResponsePayload> {
  if (!ipcPath) {
    throw new Error("MIMOLO_IPC_PATH not set");
  }
  return persistentIpcClient.sendCommand(
    cmd,
    extraPayload,
    trafficLabel,
    trafficClass,
  );
}

function resetIpcConnectBackoff(): void {
  persistentIpcClient.resetBackoff();
}

const operationsController = new OperationsController({
  runtimeProcess,
  opsLogPath,
  sendIpcCommand,
  appendOpsLogChunk,
  publishLine,
  getLastStatusState: () => lastStatus.state,
  getOperationsControlState: () => operationsControlState,
  setOperationsControlState,
  getStopWaitDisconnectPollMs: () =>
    Math.max(1, Math.round(controlTimingSettings.stop_wait_disconnect_poll_s * 1000)),
  getStopWaitDisconnectTimeoutMs: () =>
    Math.max(1, Math.round(controlTimingSettings.stop_wait_disconnect_timeout_s * 1000)),
  getStopWaitManagedExitMs: () =>
    Math.max(1, Math.round(controlTimingSettings.stop_wait_managed_exit_s * 1000)),
  getStopWaitGracefulExitMs: () =>
    Math.max(1, Math.round(controlTimingSettings.stop_wait_graceful_exit_s * 1000)),
  getStopWaitForcedExitMs: () =>
    Math.max(1, Math.round(controlTimingSettings.stop_wait_forced_exit_s * 1000)),
});

async function refreshIpcStatus(): Promise<void> {
  try {
    const response = await sendIpcCommand("ping", undefined, undefined, "background");
    if (response.ok) {
      setStatus("connected", "ipc_ready");
      if (!operationsController.hasManagedProcess()) {
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
    if (!operationsController.hasManagedProcess()) {
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
    if (!operationsController.hasManagedProcess()) {
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
  return templateCache.getTemplates(forceRefresh, refreshTemplates);
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
    lastMonitorSettings = normalizeMonitorSettings(
      monitorRaw,
      DEFAULT_MONITOR_SETTINGS,
    );
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
  lastMonitorSettings = normalizeMonitorSettings(
    monitorRaw,
    DEFAULT_MONITOR_SETTINGS,
  );
  applyControlTimingSettings(controlRaw);
  publishMonitorSettings();
  restartBackgroundTimers();
  return response;
}

async function pumpOpsLog(): Promise<void> {
  await opsLogTailer.pump();
}

async function loadInitialSnapshot(): Promise<void> {
  await opsLogTailer.initializeLogFile();
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
  return runAgentCommandWrapper(payload, sendIpcCommand, refreshAgentInstances);
}

async function getWidgetManifest(
  payload: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  return getWidgetManifestWrapper(payload, sendIpcCommand);
}

async function requestWidgetRender(
  payload: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  return requestWidgetRenderWrapper(payload, sendIpcCommand);
}

async function inspectPluginArchive(
  payload: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  return inspectPluginArchiveWrapper(payload, sendIpcCommand, controlDevMode);
}

async function installPluginArchive(
  payload: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  return installPluginArchiveWrapper(payload, sendIpcCommand, controlDevMode);
}

function deriveBackgroundIntervals(): {
  statusMs: number;
  logMs: number;
  instanceMs: number;
} {
  const statusMs = deriveStatusLoopMs(
    lastMonitorSettings,
    lastStatus.state,
    controlTimingSettings,
  );
  const logMs = deriveLogLoopMs(
    lastMonitorSettings,
    lastStatus.state,
    controlTimingSettings,
  );
  const instanceMs = deriveInstanceLoopMs(
    lastMonitorSettings,
    lastStatus.state,
    controlTimingSettings,
  );
  return {
    statusMs,
    logMs,
    instanceMs,
  };
}

const backgroundLoopController = new BackgroundLoopController({
  loadInitialSnapshot,
  refreshStatus: refreshIpcStatus,
  refreshInstances: refreshAgentInstances,
  pumpLog: pumpOpsLog,
  deriveIntervals: deriveBackgroundIntervals,
  stopPersistentIpc: () => persistentIpcClient.stop("control_shutdown"),
});

function restartBackgroundTimers(): void {
  backgroundLoopController.restart();
}

function startBackgroundLoops(): void {
  backgroundLoopController.start();
}

function stopBackgroundLoops(): void {
  backgroundLoopController.stop();
}

function operationsMayBeRunning(): boolean {
  if (operationsController.hasManagedProcess()) {
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
    const stopResult = await operationsController.control({ action: "stop" });
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

registerIpcHandlers({
  ipcMain,
  dialog,
  ipcPath,
  opsLogPath,
  controlDevMode,
  getMainWindow: () => mainWindow,
  getStatus: () => lastStatus,
  getOpsControlState: () => operationsControlState,
  getMonitorSettings: () => lastMonitorSettings,
  getControlSettings: () => controlTimingSettings,
  getInstances: () => lastAgentInstances,
  resetReconnectBackoff: resetIpcConnectBackoff,
  controlOperations: (request) => operationsController.control(request),
  refreshTemplatesCached,
  refreshMonitorSettings,
  updateMonitorSettings,
  getWidgetManifest,
  requestWidgetRender,
  inspectPluginArchive,
  installPluginArchive,
  runAgentCommand,
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
  operationsController.haltManagedForShutdown();
  void handleQuitRequest(event);
});
