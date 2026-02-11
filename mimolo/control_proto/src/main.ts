import electronDefault, * as electronNamespace from "electron";
import type {
  AgentInstanceSnapshot,
  AgentTemplateSnapshot,
  ControlCommandPayload,
  ControlTimingSettings,
  IpcResponsePayload,
  IpcTrafficClass,
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
import { resolveControlEnvironment } from "./control_env.js";
import {
  deriveInstanceLoopMs,
  deriveLogLoopMs,
  deriveStatusLoopMs,
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
import { OpsLogWriter } from "./control_ops_log_writer.js";
import { TemplateCache } from "./control_template_cache.js";
import { BackgroundLoopController } from "./control_background_loops.js";
import { OperationsStateStore } from "./control_operations_state.js";
import { loadControlTimingSettingsFromConfigFile } from "./control_timing_loader.js";
import {
  handleQuitRequest as handleQuitRequestImpl,
  operationsMayBeRunning as operationsMayBeRunningImpl,
} from "./control_quit.js";
import { createMainWindow } from "./control_window.js";
import { ControlSnapshotRefresher } from "./control_snapshot_refresher.js";
import { WindowPublisher } from "./control_window_publisher.js";

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
const { ipcPath, opsLogPath, controlDevMode } =
  resolveControlEnvironment(runtimeProcess);

let mainWindow: InstanceType<typeof BrowserWindow> | null = null;
const windowPublisher = new WindowPublisher(() => mainWindow);
const operationsStateStore = new OperationsStateStore((state) => {
  windowPublisher.publishOperationsControlState(state);
});

const DEFAULT_MONITOR_SETTINGS: MonitorSettingsSnapshot = {
  cooldown_seconds: 600,
  poll_tick_s: 0.2,
  console_verbosity: "info",
};

let quitInProgress = false;

function setOperationsControlState(
  state: OperationsProcessState,
  detail: string,
  managed: boolean,
  pid: number | null,
): void {
  operationsStateStore.set(state, detail, managed, pid);
}

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

const opsLogWriter = new OpsLogWriter(opsLogPath);
const appendOpsLogChunk = opsLogWriter.append.bind(opsLogWriter);

const publishLine = windowPublisher.publishLine.bind(windowPublisher);
const publishBootstrapLine = windowPublisher.publishBootstrapLine.bind(windowPublisher);
const publishTraffic = windowPublisher.publishTraffic.bind(windowPublisher);
const publishInstances = windowPublisher.publishInstances.bind(windowPublisher);
const publishStatus = windowPublisher.publishStatus.bind(windowPublisher);
const publishMonitorSettings =
  windowPublisher.publishMonitorSettings.bind(windowPublisher);

const opsLogTailer = new OpsLogTailer(opsLogPath, publishLine);

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

let snapshotRefresher: ControlSnapshotRefresher;

const operationsController = new OperationsController({
  runtimeProcess,
  opsLogPath,
  sendIpcCommand,
  appendOpsLogChunk,
  publishBootstrapLine,
  publishLine,
  getLastStatusState: () => snapshotRefresher.getStatus().state,
  getOperationsControlState: () => operationsStateStore.get(),
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

snapshotRefresher = new ControlSnapshotRefresher({
  applyControlTimingSettings,
  defaultMonitorSettings: DEFAULT_MONITOR_SETTINGS,
  getControlTimingSettings: () => controlTimingSettings,
  getOperationsControlState: () => operationsStateStore.get(),
  hasManagedOperationsProcess: () => operationsController.hasManagedProcess(),
  initializeOpsLogFile: () => opsLogTailer.initializeLogFile(),
  publishInstances,
  publishLine,
  publishMonitorSettings,
  publishStatus,
  restartBackgroundTimers,
  sendIpcCommand,
  setOperationsControlState,
  templateCache,
});

async function refreshIpcStatus(): Promise<void> {
  await snapshotRefresher.refreshIpcStatus();
}

async function refreshAgentInstances(): Promise<void> {
  await snapshotRefresher.refreshAgentInstances();
}

async function refreshTemplates(): Promise<Record<string, AgentTemplateSnapshot>> {
  return snapshotRefresher.refreshTemplates();
}

async function refreshTemplatesCached(forceRefresh = false): Promise<Record<string, AgentTemplateSnapshot>> {
  return snapshotRefresher.refreshTemplatesCached(forceRefresh);
}

async function refreshMonitorSettings(): Promise<void> {
  await snapshotRefresher.refreshMonitorSettings();
}

async function updateMonitorSettings(
  updates: Record<string, unknown>,
): Promise<IpcResponsePayload> {
  return snapshotRefresher.updateMonitorSettings(updates);
}

async function pumpOpsLog(): Promise<void> {
  await opsLogTailer.pump();
}

async function loadInitialSnapshot(): Promise<void> {
  await snapshotRefresher.loadInitialSnapshot();
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
  const monitorSettings = snapshotRefresher.getMonitorSettings();
  const status = snapshotRefresher.getStatus();
  const statusMs = deriveStatusLoopMs(
    monitorSettings,
    status.state,
    controlTimingSettings,
  );
  const logMs = deriveLogLoopMs(
    monitorSettings,
    status.state,
    controlTimingSettings,
  );
  const instanceMs = deriveInstanceLoopMs(
    monitorSettings,
    status.state,
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
  return operationsMayBeRunningImpl(
    operationsController.hasManagedProcess(),
    snapshotRefresher.getStatus().state,
    operationsStateStore.get(),
  );
}

async function promptQuitBehavior(): Promise<number> {
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
  return prompt.response;
}

async function showShutdownError(detail: string): Promise<void> {
  await dialog.showMessageBox(mainWindow ?? undefined, {
    type: "error",
    buttons: ["OK"],
    defaultId: 0,
    noLink: true,
    title: "Shutdown Failed",
    message: "Unable to stop Operations cleanly.",
    detail,
  });
}

async function handleQuitRequest(event: { preventDefault: () => void }): Promise<void> {
  await handleQuitRequestImpl(event, {
    isQuitInProgress: () => quitInProgress,
    setQuitInProgress: (value) => {
      quitInProgress = value;
    },
    operationsMayBeRunning,
    stopBackgroundLoops,
    quitApp: () => {
      app.quit();
    },
    promptQuitBehavior,
    stopOperations: () => operationsController.control({ action: "stop" }),
    showShutdownError,
  });
}

function createWindow(): void {
  mainWindow = createMainWindow({
    BrowserWindow,
    controlTimingSettings,
    controlDevMode,
    buildHtml,
    onClosed: () => {
      mainWindow = null;
    },
  });
}

registerIpcHandlers({
  ipcMain,
  dialog,
  ipcPath,
  opsLogPath,
  controlDevMode,
  getMainWindow: () => mainWindow,
  getStatus: () => snapshotRefresher.getStatus(),
  getOpsControlState: () => operationsStateStore.get(),
  getMonitorSettings: () => snapshotRefresher.getMonitorSettings(),
  getControlSettings: () => controlTimingSettings,
  getInstances: () => snapshotRefresher.getAgentInstances(),
  resetReconnectBackoff: resetIpcConnectBackoff,
  controlOperations: (request) => operationsController.control(request),
  prepareRuntime: () => operationsController.prepareRuntime(),
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
  applyControlTimingSettings(DEFAULT_CONTROL_TIMING_SETTINGS);
  await loadControlTimingSettingsFromConfigFile(
    runtimeProcess,
    applyControlTimingSettings,
  );
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
