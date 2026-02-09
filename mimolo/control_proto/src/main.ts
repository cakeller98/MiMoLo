import electronDefault, * as electronNamespace from "electron";
import { spawn } from "node:child_process";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import net from "node:net";
import path from "node:path";

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

interface RuntimeProcess {
  env: Record<string, string | undefined>;
  cwd?: () => string;
  platform?: string;
}

interface OpsStatusPayload {
  detail: string;
  state: "connected" | "disconnected" | "starting";
  timestamp: string;
}

interface MonitorSettingsSnapshot {
  console_verbosity: "debug" | "info" | "warning" | "error";
  cooldown_seconds: number;
  poll_tick_s: number;
}

type AgentLifecycleState = "running" | "shutting-down" | "inactive" | "error";
type AgentCommandAction =
  | "start_agent"
  | "stop_agent"
  | "restart_agent"
  | "add_agent_instance"
  | "duplicate_agent_instance"
  | "remove_agent_instance"
  | "update_agent_instance";

interface AgentInstanceSnapshot {
  config: Record<string, unknown>;
  detail: string;
  label: string;
  state: AgentLifecycleState;
  template_id: string;
}

interface AgentTemplateSnapshot {
  default_config: Record<string, unknown>;
  script: string;
  template_id: string;
}

interface ControlCommandPayload {
  action: AgentCommandAction;
  label?: string;
  requested_label?: string;
  template_id?: string;
  updates?: Record<string, unknown>;
}

interface IpcResponsePayload {
  cmd?: string;
  data?: Record<string, unknown>;
  error?: string;
  ok: boolean;
  request_id?: string;
  timestamp?: string;
}

interface IpcTrafficPayload {
  direction: "tx" | "rx";
  kind: IpcTrafficClass;
  label?: string;
  timestamp: string;
}

type IpcTrafficClass = "interactive" | "background";

interface PendingIpcRequest {
  id: string;
  payload: Record<string, unknown>;
  reject: (reason: Error) => void;
  resolve: (value: IpcResponsePayload) => void;
  timeoutHandle: ReturnType<typeof setTimeout> | null;
  trafficClass: IpcTrafficClass;
  trafficLabel?: string;
}

type OperationsProcessState = "running" | "stopped" | "starting" | "stopping" | "error";

interface OperationsControlSnapshot {
  detail: string;
  managed: boolean;
  pid: number | null;
  state: OperationsProcessState;
  timestamp: string;
}

interface OperationsControlRequest {
  action: "start" | "stop" | "restart" | "status";
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
let operationsControlState: OperationsControlSnapshot = {
  state: "stopped",
  detail: "not_managed",
  managed: false,
  pid: null,
  timestamp: new Date().toISOString(),
};

const IPC_REQUEST_TIMEOUT_MS = 1500;
const IPC_MAX_PENDING_REQUESTS = 256;
type IpcSocket = ReturnType<typeof net.createConnection>;

let ipcSocket: IpcSocket | null = null;
let ipcSocketState: "disconnected" | "connecting" | "connected" = "disconnected";
let ipcSocketBuffer = "";
let ipcConnectPromise: Promise<void> | null = null;
let ipcConnectResolve: (() => void) | null = null;
let ipcConnectReject: ((error: Error) => void) | null = null;
let ipcInFlightRequest: PendingIpcRequest | null = null;
let ipcQueueDrainRunning = false;
let ipcRequestCounter = 0;
const ipcPendingRequestQueue: PendingIpcRequest[] = [];

function buildHtml(): string {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>MiMoLo Control Proto</title>
    <style>
      :root {
        --bg: #0e1014;
        --panel: #171a21;
        --card: #1c212c;
        --text: #d9dee9;
        --muted: #8d98aa;
        --accent: #56d8a9;
        --running: #2fcf70;
        --shutting: #d6b845;
        --error: #d94c4c;
        --neutral: #3f4550;
        --border: #2b3342;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        background: radial-gradient(circle at top right, #1a2436 0%, var(--bg) 55%);
        color: var(--text);
      }
      .shell {
        display: grid;
        grid-template-rows: auto 1fr;
        height: 100vh;
      }
      .top {
        border-bottom: 1px solid var(--border);
        padding: 12px 14px;
        background: rgba(23, 26, 33, 0.82);
      }
      .row {
        margin: 3px 0;
        font-size: 12px;
        color: var(--muted);
      }
      .row strong { color: var(--text); }
      #status { color: var(--accent); }
      .top-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 3px;
      }
      .ops-global {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .ops-btn {
        background: #253047;
        color: var(--text);
        border: 1px solid #33405a;
        border-radius: 6px;
        font-family: inherit;
        font-size: 10px;
        padding: 4px 7px;
        cursor: pointer;
      }
      .ops-btn:hover {
        background: #2d3b55;
      }
      .ops-btn:disabled {
        cursor: default;
        opacity: 0.65;
      }
      .ops-process-state {
        font-size: 11px;
        color: var(--muted);
      }
      .main {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 390px;
        min-height: 0;
      }
      .log-pane {
        border-right: 1px solid var(--border);
        min-height: 0;
      }
      #log {
        margin: 0;
        padding: 12px 14px;
        overflow: auto;
        height: 100%;
        white-space: pre-wrap;
        line-height: 1.4;
        font-size: 12px;
      }
      .controls {
        display: grid;
        grid-template-rows: auto 1fr;
        min-height: 0;
        background: rgba(18, 22, 29, 0.75);
      }
      .controls-head {
        border-bottom: 1px solid var(--border);
        padding: 10px 12px;
      }
      .controls-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
      }
      .controls-actions {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .controls-title {
        font-size: 12px;
        font-weight: 700;
        color: var(--text);
      }
      .controls-sub {
        margin-top: 4px;
        font-size: 11px;
        color: var(--muted);
      }
      .dev-warning {
        color: #d4b25c;
      }
      .add-btn {
        background: #22324a;
        color: var(--text);
        border: 1px solid #344762;
        border-radius: 6px;
        font-family: inherit;
        font-size: 11px;
        padding: 5px 8px;
        cursor: pointer;
      }
      .add-btn:hover { background: #2a3d59; }
      .install-btn {
        background: #29422f;
        color: var(--text);
        border: 1px solid #3a6643;
        border-radius: 6px;
        font-family: inherit;
        font-size: 11px;
        padding: 5px 8px;
        cursor: pointer;
      }
      .install-btn:hover { background: #35533c; }
      .cards {
        padding: 10px;
        overflow-y: auto;
        min-height: 0;
      }
      .drop-hint {
        position: fixed;
        inset: 0;
        z-index: 2100;
        background: rgba(8, 11, 16, 0.72);
        border: 2px dashed #4d6f56;
        color: #b5dfc1;
        font-size: 14px;
        font-weight: 700;
        display: flex;
        align-items: center;
        justify-content: center;
        letter-spacing: 0.03em;
      }
      .toast-host {
        position: fixed;
        right: 12px;
        bottom: 12px;
        z-index: 2200;
        display: grid;
        gap: 8px;
        pointer-events: none;
      }
      .toast {
        border: 1px solid #33405a;
        border-radius: 8px;
        background: rgba(16, 22, 32, 0.95);
        color: var(--text);
        font-size: 11px;
        line-height: 1.3;
        padding: 8px 10px;
        min-width: 240px;
        max-width: 420px;
      }
      .toast-ok {
        border-color: #3d7a50;
      }
      .toast-warn {
        border-color: #8f7a33;
      }
      .toast-err {
        border-color: #8e4040;
      }
      .agent-card {
        border: 1px solid var(--border);
        border-radius: 8px;
        background: var(--card);
        padding: 10px;
        margin-bottom: 10px;
      }
      .agent-top {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 8px;
        align-items: start;
      }
      .agent-label {
        font-size: 12px;
        font-weight: 700;
        color: var(--text);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .agent-icons {
        display: flex;
        gap: 4px;
      }
      .icon-btn {
        width: 20px;
        height: 20px;
        border-radius: 5px;
        border: 1px solid #344357;
        background: #27354a;
        color: #d6dce8;
        font-family: inherit;
        font-size: 11px;
        line-height: 1;
        padding: 0;
        cursor: pointer;
      }
      .icon-btn:hover { background: #33445e; }
      .signal-group {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .signal-text {
        font-size: 11px;
        color: var(--muted);
      }
      .light {
        width: 9px;
        height: 9px;
        border-radius: 999px;
        background: var(--neutral);
        box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08);
      }
      .light-running { background: var(--running); box-shadow: 0 0 8px rgba(47, 207, 112, 0.7); }
      .light-shutting-down { background: var(--shutting); box-shadow: 0 0 8px rgba(214, 184, 69, 0.6); }
      .light-inactive { background: var(--neutral); box-shadow: none; }
      .light-error { background: var(--error); box-shadow: 0 0 8px rgba(217, 76, 76, 0.65); }
      .light-bg-online {
        background: var(--neutral);
        box-shadow: inset 0 0 0 1px rgba(47, 207, 112, 0.9), 0 0 6px rgba(47, 207, 112, 0.35);
      }
      .light-bg-offline {
        background: var(--error);
        box-shadow: 0 0 8px rgba(217, 76, 76, 0.65);
      }
      .light-small {
        width: 7px;
        height: 7px;
      }
      .agent-meta {
        margin-top: 7px;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .agent-detail {
        margin-top: 4px;
        font-size: 11px;
        color: var(--muted);
        min-height: 14px;
      }
      .agent-actions {
        margin-top: 10px;
        display: flex;
        gap: 6px;
      }
      .agent-actions button {
        background: #253047;
        color: var(--text);
        border: 1px solid #33405a;
        border-radius: 6px;
        font-family: inherit;
        font-size: 11px;
        padding: 5px 8px;
        cursor: pointer;
      }
      .agent-actions button:hover {
        background: #2d3b55;
      }
      .widget-head {
        margin-top: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      .widget-controls {
        display: flex;
        gap: 6px;
      }
      .mini-btn {
        background: #222d42;
        color: var(--text);
        border: 1px solid #33405a;
        border-radius: 6px;
        font-family: inherit;
        font-size: 10px;
        padding: 4px 7px;
        cursor: pointer;
      }
      .mini-btn:hover {
        background: #2b3a55;
      }
      .widget-canvas {
        margin-top: 8px;
        border: 1px solid #31415b;
        border-radius: 6px;
        background: #101722;
        min-height: 72px;
        max-height: 130px;
        overflow: auto;
        padding: 8px;
        font-size: 11px;
        color: #b8c3d6;
        line-height: 1.35;
      }
      .screen-widget-root {
        display: grid;
        gap: 6px;
      }
      .screen-widget-image {
        width: 100%;
        max-height: 180px;
        object-fit: contain;
        border-radius: 4px;
        background: #0c1018;
      }
      .screen-widget-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        font-size: 10px;
        color: #8f9db2;
      }
      .screen-widget-file {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .screen-widget-time {
        white-space: nowrap;
      }
      .widget-muted {
        color: #7f8ca0;
      }
      .modal-overlay {
        position: fixed;
        inset: 0;
        background: rgba(7, 10, 14, 0.76);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 2000;
      }
      .modal-card {
        width: min(560px, calc(100vw - 30px));
        background: #171d27;
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 12px;
      }
      .modal-title {
        font-size: 12px;
        font-weight: 700;
        color: var(--text);
        margin-bottom: 10px;
      }
      .modal-body {
        display: grid;
        gap: 8px;
      }
      .modal-body label {
        font-size: 11px;
        color: var(--muted);
      }
      .modal-body input,
      .modal-body select,
      .modal-body textarea {
        width: 100%;
        border: 1px solid #344357;
        border-radius: 6px;
        background: #0f141d;
        color: var(--text);
        font-family: inherit;
        font-size: 11px;
        padding: 6px;
      }
      .modal-body textarea {
        min-height: 220px;
        resize: vertical;
      }
      .modal-actions {
        margin-top: 10px;
        display: flex;
        justify-content: flex-end;
        gap: 8px;
      }
      .modal-actions button {
        background: #253047;
        color: var(--text);
        border: 1px solid #33405a;
        border-radius: 6px;
        font-family: inherit;
        font-size: 11px;
        padding: 5px 10px;
        cursor: pointer;
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="top">
        <div class="top-head">
          <div class="row"><strong>MiMoLo Control Proto</strong> - operations stream viewer</div>
          <div class="ops-global">
            <button class="ops-btn" id="opsStartBtn" title="Start Operations">Start Ops</button>
            <button class="ops-btn" id="opsStopBtn" title="Stop Operations">Stop Ops</button>
            <button class="ops-btn" id="opsRestartBtn" title="Restart Operations">Restart Ops</button>
            <div class="light light-inactive light-small" id="globalBgActivity" title="Background polling activity"></div>
            <div class="signal-text">bg</div>
            <div class="light light-inactive" id="globalTxLight" title="Global tx"></div>
            <div class="signal-text">tx</div>
            <div class="light light-inactive" id="globalRxLight" title="Global rx"></div>
            <div class="signal-text">rx</div>
          </div>
        </div>
        <div class="row ops-process-state">Ops process: <span id="opsProcessState">stopped - not_managed</span></div>
        <div class="row">IPC: <span id="ipcPath"></span></div>
        <div class="row">Ops log: <span id="opsLogPath"></span></div>
        <div class="row">Monitor: <span id="monitorSettings">poll_tick_s=?, cooldown_seconds=?</span></div>
        <div class="row">Status: <span id="status">starting</span></div>
        ${
          controlDevMode
            ? `<div class="row dev-warning"><strong>Dev mode:</strong> unsigned zip plugin sideload is enabled (signature allowlist is not implemented yet).</div>`
            : ""
        }
      </div>
      <div class="main">
        <div class="log-pane"><pre id="log"></pre></div>
        <div class="controls">
          <div class="controls-head">
            <div class="controls-row">
              <div class="controls-title">Agent Control Panel</div>
              <div class="controls-actions">
                <button class="add-btn" id="monitorSettingsBtn" title="Edit global monitor settings">Monitor</button>
                ${
                  controlDevMode
                    ? `<button class="install-btn" id="installPluginBtn" title="Install or upgrade plugin zip (developer mode only)">Install (dev)</button>`
                    : ""
                }
                <button class="add-btn" id="addAgentBtn" title="Add agent instance">+ Add</button>
              </div>
            </div>
            <div class="controls-sub">Per-instance controls and configuration from registered templates</div>
          </div>
          <div class="cards" id="cards"></div>
        </div>
      </div>
    </div>
    ${
      controlDevMode
        ? `<div id="dropHint" class="drop-hint" hidden>Drop plugin zip to install (developer mode)</div>`
        : ""
    }
    <div id="modalHost"></div>
    <div id="toastHost" class="toast-host"></div>
    <script>
      const electronRuntime = typeof require === "function" ? require("electron") : null;
      const ipcRenderer = electronRuntime ? electronRuntime.ipcRenderer : null;
      const installDevMode = ${controlDevMode ? "true" : "false"};
      const statusEl = document.getElementById("status");
      const logEl = document.getElementById("log");
      const opsProcessStateEl = document.getElementById("opsProcessState");
      const ipcPathEl = document.getElementById("ipcPath");
      const opsLogPathEl = document.getElementById("opsLogPath");
      const monitorSettingsEl = document.getElementById("monitorSettings");
      const opsStartBtn = document.getElementById("opsStartBtn");
      const opsStopBtn = document.getElementById("opsStopBtn");
      const opsRestartBtn = document.getElementById("opsRestartBtn");
      const globalBgActivity = document.getElementById("globalBgActivity");
      const globalTxLight = document.getElementById("globalTxLight");
      const globalRxLight = document.getElementById("globalRxLight");
      const cardsRoot = document.getElementById("cards");
      const monitorSettingsBtn = document.getElementById("monitorSettingsBtn");
      const addAgentBtn = document.getElementById("addAgentBtn");
      const installPluginBtn = document.getElementById("installPluginBtn");
      const dropHint = document.getElementById("dropHint");
      const modalHost = document.getElementById("modalHost");
      const toastHost = document.getElementById("toastHost");
      const cards = new Map();
      const instancesByLabel = new Map();
      const templatesById = new Map();
      const widgetPausedLabels = new Set();
      const widgetInFlight = new Set();
      const widgetManifestLoaded = new Set();
      const widgetNextAutoRefreshAt = new Map();
      let monitorSettingsState = {
        cooldown_seconds: 600,
        poll_tick_s: 0.2,
        console_verbosity: "info",
      };

      const lines = [];
      const maxLines = 1800;

      function append(line) {
        lines.push(line);
        if (lines.length > maxLines) lines.shift();
        logEl.textContent = lines.join("\\n");
        logEl.scrollTop = logEl.scrollHeight;
      }

      function setStatus(text) {
        statusEl.textContent = text;
      }

      function normalizeMonitorSettings(raw) {
        if (!raw || typeof raw !== "object") {
          return {
            cooldown_seconds: 600,
            poll_tick_s: 0.2,
            console_verbosity: "info",
          };
        }
        const cooldownRaw = raw.cooldown_seconds;
        const pollTickRaw = raw.poll_tick_s;
        const verbosityRaw = raw.console_verbosity;
        const cooldown =
          typeof cooldownRaw === "number" && Number.isFinite(cooldownRaw) && cooldownRaw > 0
            ? cooldownRaw
            : 600;
        const pollTick =
          typeof pollTickRaw === "number" && Number.isFinite(pollTickRaw) && pollTickRaw > 0
            ? pollTickRaw
            : 0.2;
        const verbosity =
          verbosityRaw === "debug" ||
          verbosityRaw === "info" ||
          verbosityRaw === "warning" ||
          verbosityRaw === "error"
            ? verbosityRaw
            : "info";
        return {
          cooldown_seconds: cooldown,
          poll_tick_s: pollTick,
          console_verbosity: verbosity,
        };
      }

      function renderMonitorSettings(raw) {
        monitorSettingsState = normalizeMonitorSettings(raw);
        if (!monitorSettingsEl) {
          return;
        }
        monitorSettingsEl.textContent =
          "poll_tick_s=" + String(monitorSettingsState.poll_tick_s) +
          ", cooldown_seconds=" + String(monitorSettingsState.cooldown_seconds) +
          ", console_verbosity=" + String(monitorSettingsState.console_verbosity);
      }

      function setBgLightState(lightEl, state) {
        if (!lightEl) {
          return;
        }
        lightEl.classList.remove("light-bg-online", "light-bg-offline", "light-inactive");
        if (state === "online") {
          lightEl.classList.add("light-bg-online");
          return;
        }
        if (state === "offline") {
          lightEl.classList.add("light-bg-offline");
          return;
        }
        lightEl.classList.add("light-inactive");
      }

      function applyGlobalBgState(opsState, opsDetail) {
        if (!globalBgActivity) {
          return;
        }
        if (opsState === "connected") {
          setBgLightState(globalBgActivity, "online");
          return;
        }
        if (opsState === "disconnected") {
          const detail = typeof opsDetail === "string" ? opsDetail : "";
          if (detail === "not_managed" || detail === "stopped_by_control") {
            setBgLightState(globalBgActivity, "neutral");
            return;
          }
          setBgLightState(globalBgActivity, "offline");
          return;
        }
        setBgLightState(globalBgActivity, "neutral");
      }

      function renderOpsProcessState(state) {
        if (!opsProcessStateEl) {
          return;
        }
        const stateText = state && typeof state.state === "string" ? state.state : "unknown";
        const detailText = state && typeof state.detail === "string" ? state.detail : "unknown";
        const managedText = state && state.managed === true ? "managed" : "external_or_stopped";
        const pidText = state && typeof state.pid === "number" ? " pid=" + String(state.pid) : "";
        opsProcessStateEl.textContent = stateText + " - " + detailText + " (" + managedText + ")" + pidText;

        if (opsStartBtn) {
          opsStartBtn.disabled = stateText === "running" || stateText === "starting";
        }
        if (opsStopBtn) {
          opsStopBtn.disabled = stateText === "stopped" || stateText === "stopping";
        }
        if (opsRestartBtn) {
          opsRestartBtn.disabled = stateText === "starting" || stateText === "stopping";
        }
      }

      async function runOpsControl(action) {
        if (!ipcRenderer) {
          append("[ops] control failed: ipc renderer unavailable");
          return;
        }
        try {
          const response = await ipcRenderer.invoke("mml:ops-control", { action });
          if (response && response.state) {
            renderOpsProcessState(response.state);
          }
          if (!response || !response.ok) {
            const errText = response && response.error ? String(response.error) : "ops_control_failed";
            append("[ops] " + action + " failed: " + errText);
            return;
          }
          const detail = response && response.state && response.state.detail
            ? String(response.state.detail)
            : "ok";
          append("[ops] " + action + " -> " + detail);
        } catch (err) {
          const detail = err instanceof Error ? err.message : "ops_control_failed";
          append("[ops] " + action + " failed: " + detail);
        }
      }

      function showToast(message, kind) {
        if (!toastHost) {
          return;
        }
        const toast = document.createElement("div");
        const tone = kind === "ok" ? "toast-ok" : (kind === "err" ? "toast-err" : "toast-warn");
        toast.className = "toast " + tone;
        toast.textContent = message;
        toastHost.appendChild(toast);
        setTimeout(() => {
          toast.remove();
        }, 2800);
      }

      function showModal(build) {
        if (!modalHost) {
          return Promise.resolve(null);
        }
        return new Promise((resolve) => {
          modalHost.innerHTML = "";
          const overlay = document.createElement("div");
          overlay.className = "modal-overlay";
          const card = document.createElement("div");
          card.className = "modal-card";
          overlay.appendChild(card);
          modalHost.appendChild(overlay);

          function close(result) {
            modalHost.innerHTML = "";
            resolve(result);
          }

          build(card, close);
        });
      }

      async function pickTemplateModal(templateIds) {
        return showModal((card, close) => {
          const title = document.createElement("div");
          title.className = "modal-title";
          title.textContent = "Add agent instance";
          const body = document.createElement("div");
          body.className = "modal-body";

          const labelTemplate = document.createElement("label");
          labelTemplate.textContent = "Template";
          const select = document.createElement("select");
          for (const id of templateIds) {
            const opt = document.createElement("option");
            opt.value = id;
            opt.textContent = id;
            select.appendChild(opt);
          }
          labelTemplate.appendChild(select);

          const labelName = document.createElement("label");
          labelName.textContent = "Instance label (optional)";
          const input = document.createElement("input");
          input.placeholder = "leave blank for default";
          labelName.appendChild(input);

          body.appendChild(labelTemplate);
          body.appendChild(labelName);

          const actions = document.createElement("div");
          actions.className = "modal-actions";
          const cancelBtn = document.createElement("button");
          cancelBtn.textContent = "Cancel";
          cancelBtn.addEventListener("click", () => close(null));
          const addBtn = document.createElement("button");
          addBtn.textContent = "Add";
          addBtn.addEventListener("click", () => {
            close({
              template_id: select.value,
              requested_label: input.value.trim(),
            });
          });
          actions.appendChild(cancelBtn);
          actions.appendChild(addBtn);

          card.appendChild(title);
          card.appendChild(body);
          card.appendChild(actions);
          select.focus();
        });
      }

      async function confirmModal(message) {
        const result = await showModal((card, close) => {
          const title = document.createElement("div");
          title.className = "modal-title";
          title.textContent = message;
          const actions = document.createElement("div");
          actions.className = "modal-actions";
          const cancelBtn = document.createElement("button");
          cancelBtn.textContent = "Cancel";
          cancelBtn.addEventListener("click", () => close(false));
          const okBtn = document.createElement("button");
          okBtn.textContent = "Confirm";
          okBtn.addEventListener("click", () => close(true));
          actions.appendChild(cancelBtn);
          actions.appendChild(okBtn);
          card.appendChild(title);
          card.appendChild(actions);
          okBtn.focus();
        });
        return result === true;
      }

      async function editJsonModal(titleText, defaultValue) {
        return showModal((card, close) => {
          const title = document.createElement("div");
          title.className = "modal-title";
          title.textContent = titleText;
          const body = document.createElement("div");
          body.className = "modal-body";
          const label = document.createElement("label");
          label.textContent = "JSON";
          const area = document.createElement("textarea");
          area.value = defaultValue;
          label.appendChild(area);
          body.appendChild(label);

          const actions = document.createElement("div");
          actions.className = "modal-actions";
          const cancelBtn = document.createElement("button");
          cancelBtn.textContent = "Cancel";
          cancelBtn.addEventListener("click", () => close(null));
          const saveBtn = document.createElement("button");
          saveBtn.textContent = "Save";
          saveBtn.addEventListener("click", () => close(area.value));
          actions.appendChild(cancelBtn);
          actions.appendChild(saveBtn);
          card.appendChild(title);
          card.appendChild(body);
          card.appendChild(actions);
          area.focus();
        });
      }

      async function editMonitorSettingsModal(currentSettings) {
        return showModal((card, close) => {
          const title = document.createElement("div");
          title.className = "modal-title";
          title.textContent = "Global monitor settings";

          const body = document.createElement("div");
          body.className = "modal-body";

          const pollLabel = document.createElement("label");
          pollLabel.textContent = "poll_tick_s (seconds, > 0)";
          const pollInput = document.createElement("input");
          pollInput.type = "number";
          pollInput.step = "0.1";
          pollInput.min = "0.1";
          pollInput.value = String(currentSettings.poll_tick_s);
          pollLabel.appendChild(pollInput);

          const cooldownLabel = document.createElement("label");
          cooldownLabel.textContent = "cooldown_seconds (seconds, > 0)";
          const cooldownInput = document.createElement("input");
          cooldownInput.type = "number";
          cooldownInput.step = "1";
          cooldownInput.min = "1";
          cooldownInput.value = String(currentSettings.cooldown_seconds);
          cooldownLabel.appendChild(cooldownInput);

          const verbosityLabel = document.createElement("label");
          verbosityLabel.textContent = "console_verbosity";
          const verbositySelect = document.createElement("select");
          const verbosityValues = ["debug", "info", "warning", "error"];
          for (const value of verbosityValues) {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = value;
            verbositySelect.appendChild(option);
          }
          verbositySelect.value = String(currentSettings.console_verbosity);
          verbosityLabel.appendChild(verbositySelect);

          body.appendChild(pollLabel);
          body.appendChild(cooldownLabel);
          body.appendChild(verbosityLabel);

          const actions = document.createElement("div");
          actions.className = "modal-actions";
          const cancelBtn = document.createElement("button");
          cancelBtn.textContent = "Cancel";
          cancelBtn.addEventListener("click", () => close(null));
          const saveBtn = document.createElement("button");
          saveBtn.textContent = "Save";
          saveBtn.addEventListener("click", () => {
            const pollTick = Number(pollInput.value);
            const cooldownSeconds = Number(cooldownInput.value);
            if (!Number.isFinite(pollTick) || pollTick <= 0) {
              append("[ui] monitor settings invalid: poll_tick_s must be > 0");
              return;
            }
            if (!Number.isFinite(cooldownSeconds) || cooldownSeconds <= 0) {
              append("[ui] monitor settings invalid: cooldown_seconds must be > 0");
              return;
            }
            close({
              poll_tick_s: pollTick,
              cooldown_seconds: cooldownSeconds,
              console_verbosity: verbositySelect.value,
            });
          });
          actions.appendChild(cancelBtn);
          actions.appendChild(saveBtn);
          card.appendChild(title);
          card.appendChild(body);
          card.appendChild(actions);
          pollInput.focus();
        });
      }

      function applyLifeClass(light, state) {
        light.classList.remove("light-running", "light-shutting-down", "light-inactive", "light-error");
        light.classList.add("light-" + state);
      }

      const INDICATOR_FADE_LEVELS = [0.9, 0.6, 0.3, 0.1];
      const INDICATOR_FADE_STEP_MS = 200;
      const WIDGET_AUTO_TICK_MS = 250;
      const DEFAULT_WIDGET_AUTO_REFRESH_MS = 15000;
      const INDICATOR_COLORS = {
        tx: { bg: "#2fcf70", glow: "47, 207, 112" },
        rx: { bg: "#d94c4c", glow: "217, 76, 76" },
        bg: { bg: "#7ba0cf", glow: "123, 160, 207" },
      };

      function createActivityIndicator(lightEl, palette) {
        if (!lightEl) {
          return {
            trigger: function noop() {},
          };
        }
        const state = {
          active: false,
          stepIndex: 0,
          timer: null,
        };

        function resetVisual() {
          lightEl.classList.add("light-inactive");
          lightEl.style.opacity = "1";
          lightEl.style.background = "";
          lightEl.style.boxShadow = "";
        }

        function applyVisual(level) {
          lightEl.classList.remove("light-inactive");
          lightEl.style.opacity = String(level);
          lightEl.style.background = palette.bg;
          lightEl.style.boxShadow = "0 0 10px rgba(" + palette.glow + ", " + String(level) + ")";
        }

        function scheduleNextTick() {
          state.timer = setTimeout(() => {
            runTick();
          }, INDICATOR_FADE_STEP_MS);
        }

        function runTick() {
          state.timer = null;
          if (!state.active) {
            resetVisual();
            return;
          }

          const level = INDICATOR_FADE_LEVELS[state.stepIndex];
          applyVisual(level);
          state.stepIndex += 1;

          if (state.stepIndex < INDICATOR_FADE_LEVELS.length) {
            scheduleNextTick();
            return;
          }

          state.active = false;
          resetVisual();
        }

        return {
          trigger() {
            if (state.timer) {
              clearTimeout(state.timer);
              state.timer = null;
            }
            state.active = true;
            state.stepIndex = 0;
            runTick();
          },
        };
      }

      const globalTxIndicator = createActivityIndicator(globalTxLight, INDICATOR_COLORS.tx);
      const globalRxIndicator = createActivityIndicator(globalRxLight, INDICATOR_COLORS.rx);
      const perAgentTxIndicators = new Map();
      const perAgentRxIndicators = new Map();

      function getAgentIndicator(label, mapRef, selector, palette) {
        const existing = mapRef.get(label);
        if (existing) {
          return existing;
        }
        const card = cards.get(label);
        if (!card) {
          return null;
        }
        const txrx = card.querySelector(selector);
        if (!txrx) {
          return null;
        }
        const indicator = createActivityIndicator(txrx, palette);
        mapRef.set(label, indicator);
        return indicator;
      }

      function getAgentTxIndicator(label) {
        return getAgentIndicator(label, perAgentTxIndicators, ".js-tx", INDICATOR_COLORS.tx);
      }

      function getAgentRxIndicator(label) {
        return getAgentIndicator(label, perAgentRxIndicators, ".js-rx", INDICATOR_COLORS.rx);
      }

      function getWidgetIdentity(label) {
        const instance = instancesByLabel.get(label);
        const templateRaw = instance && typeof instance.template_id === "string" ? instance.template_id : "";
        const pluginId = templateRaw && templateRaw.trim().length > 0 ? templateRaw.trim() : label;
        return {
          plugin_id: pluginId,
          instance_id: label,
        };
      }

      function setWidgetPaused(label, paused) {
        if (paused) {
          widgetPausedLabels.add(label);
        } else {
          widgetPausedLabels.delete(label);
        }
        const card = cards.get(label);
        if (!card) return;
        const toggle = card.querySelector(".js-widget-toggle");
        if (!toggle) return;
        toggle.textContent = paused ? "play" : "pause";
        toggle.title = paused ? "Resume widget auto-refresh" : "Pause widget auto-refresh";
      }

      const WIDGET_ALLOWED_TAGS = new Set([
        "DIV",
        "SPAN",
        "P",
        "IMG",
        "UL",
        "LI",
        "STRONG",
        "EM",
        "SMALL",
        "TIME",
        "BR",
      ]);
      const WIDGET_ALLOWED_ATTRS = new Set(["class", "title", "alt", "datetime", "aria-label"]);

      function sanitizeWidgetUrl(rawUrl) {
        if (typeof rawUrl !== "string") {
          return "";
        }
        const trimmed = rawUrl.trim();
        if (trimmed.startsWith("file://")) {
          return trimmed;
        }
        if (trimmed.startsWith("data:image/")) {
          return trimmed;
        }
        return "";
      }

      function sanitizeWidgetNode(node) {
        if (node.nodeType === Node.TEXT_NODE) {
          return document.createTextNode(node.textContent || "");
        }
        if (node.nodeType !== Node.ELEMENT_NODE) {
          return null;
        }
        const element = node;
        const tagName = element.tagName.toUpperCase();
        if (!WIDGET_ALLOWED_TAGS.has(tagName)) {
          return document.createTextNode(element.textContent || "");
        }
        const clean = document.createElement(tagName.toLowerCase());
        for (const attr of Array.from(element.attributes)) {
          const name = attr.name.toLowerCase();
          const value = attr.value;
          if (name === "src" && tagName === "IMG") {
            const safeSrc = sanitizeWidgetUrl(value);
            if (safeSrc) {
              clean.setAttribute("src", safeSrc);
            }
            continue;
          }
          if (name.startsWith("on")) {
            continue;
          }
          if (WIDGET_ALLOWED_ATTRS.has(name)) {
            clean.setAttribute(name, value);
          }
        }
        for (const child of Array.from(element.childNodes)) {
          const sanitizedChild = sanitizeWidgetNode(child);
          if (sanitizedChild) {
            clean.appendChild(sanitizedChild);
          }
        }
        return clean;
      }

      function renderWidgetHtml(canvasEl, htmlFragment) {
        const template = document.createElement("template");
        template.innerHTML = htmlFragment;
        const fragment = document.createDocumentFragment();
        for (const child of Array.from(template.content.childNodes)) {
          const sanitized = sanitizeWidgetNode(child);
          if (sanitized) {
            fragment.appendChild(sanitized);
          }
        }
        canvasEl.innerHTML = "";
        canvasEl.appendChild(fragment);
        canvasEl.classList.remove("widget-muted");
      }

      async function refreshWidgetForLabel(label, manualRequest) {
        if (!ipcRenderer) {
          return;
        }
        if (widgetInFlight.has(label)) {
          return;
        }
        const card = cards.get(label);
        if (!card) {
          return;
        }
        const manifestEl = card.querySelector(".js-widget-manifest");
        const renderStatusEl = card.querySelector(".js-widget-status");
        const canvasEl = card.querySelector(".js-widget-canvas");
        if (!manifestEl || !renderStatusEl || !canvasEl) {
          return;
        }
        const identity = getWidgetIdentity(label);
        const requestId = label + "-" + Date.now();
        widgetInFlight.add(label);
        if (manualRequest) {
          append("[widget] manual update requested for " + label);
        }
        try {
          const shouldFetchManifest = manualRequest || !widgetManifestLoaded.has(label);
          if (shouldFetchManifest) {
            const manifest = await ipcRenderer.invoke("mml:get-widget-manifest", {
              ...identity,
              manual: manualRequest,
            });
            if (manifest && manifest.data && manifest.data.widget) {
              const widget = manifest.data.widget;
              const supports = widget.supports_render === true ? "yes" : "no";
              const ratio = typeof widget.default_aspect_ratio === "string" ? widget.default_aspect_ratio : "n/a";
              manifestEl.textContent = "manifest: supports_render=" + supports + ", aspect=" + ratio;
              widgetManifestLoaded.add(label);
            } else {
              manifestEl.textContent = "manifest: unavailable";
            }
          }

          const renderResponse = await ipcRenderer.invoke("mml:request-widget-render", {
            ...identity,
            request_id: requestId,
            mode: "html_fragment_v1",
            manual: manualRequest,
            canvas: {
              aspect_ratio: "16:9",
              max_width_px: 960,
              max_height_px: 540,
            },
          });
          const render = renderResponse && renderResponse.data ? renderResponse.data.render : null;
          const warningText = render && Array.isArray(render.warnings) && render.warnings.length > 0
            ? render.warnings.join(", ")
            : (renderResponse && renderResponse.error ? String(renderResponse.error) : "no_status");
          renderStatusEl.textContent = "render: " + warningText;

          if (render && typeof render.html === "string" && render.html.trim().length > 0) {
            renderWidgetHtml(canvasEl, render.html);
          } else {
            canvasEl.textContent = "widget canvas waiting: " + warningText;
            canvasEl.classList.add("widget-muted");
          }
        } catch (err) {
          const detail = err instanceof Error ? err.message : "widget_refresh_failed";
          manifestEl.textContent = "manifest: error";
          renderStatusEl.textContent = "render: error";
          canvasEl.textContent = "widget error: " + detail;
          canvasEl.classList.add("widget-muted");
          append("[widget] " + label + " refresh failed: " + detail);
        } finally {
          widgetInFlight.delete(label);
          if (manualRequest) {
            const instance = instancesByLabel.get(label);
            const nextMs = resolveWidgetAutoRefreshMs(instance);
            widgetNextAutoRefreshAt.set(label, Date.now() + nextMs);
          }
        }
      }

      function resolveWidgetAutoRefreshMs(instance) {
        const globalFloorMs = Math.max(
          1000,
          Math.round(monitorSettingsState.poll_tick_s * 1000)
        );
        if (!instance || !instance.config) {
          return Math.max(DEFAULT_WIDGET_AUTO_REFRESH_MS, globalFloorMs);
        }
        const effectiveHeartbeatRaw = instance.config.effective_heartbeat_interval_s;
        if (
          typeof effectiveHeartbeatRaw === "number" &&
          Number.isFinite(effectiveHeartbeatRaw) &&
          effectiveHeartbeatRaw > 0
        ) {
          return Math.max(globalFloorMs, Math.round(effectiveHeartbeatRaw * 1000));
        }
        if (typeof effectiveHeartbeatRaw === "string") {
          const parsedEffective = Number(effectiveHeartbeatRaw);
          if (Number.isFinite(parsedEffective) && parsedEffective > 0) {
            return Math.max(globalFloorMs, Math.round(parsedEffective * 1000));
          }
        }
        const heartbeatRaw = instance.config.heartbeat_interval_s;
        if (typeof heartbeatRaw === "number" && Number.isFinite(heartbeatRaw) && heartbeatRaw > 0) {
          return Math.max(globalFloorMs, Math.round(heartbeatRaw * 1000));
        }
        if (typeof heartbeatRaw === "string") {
          const parsed = Number(heartbeatRaw);
          if (Number.isFinite(parsed) && parsed > 0) {
            return Math.max(globalFloorMs, Math.round(parsed * 1000));
          }
        }
        return Math.max(DEFAULT_WIDGET_AUTO_REFRESH_MS, globalFloorMs);
      }

      function refreshWidgetsAuto() {
        const now = Date.now();
        for (const label of cards.keys()) {
          if (widgetPausedLabels.has(label)) {
            continue;
          }
          const instance = instancesByLabel.get(label);
          const state = instance && typeof instance.state === "string" ? instance.state : "inactive";
          if (state !== "running") {
            continue;
          }
          const nextAllowedAt = widgetNextAutoRefreshAt.get(label);
          if (typeof nextAllowedAt === "number" && now < nextAllowedAt) {
            continue;
          }
          const intervalMs = resolveWidgetAutoRefreshMs(instance);
          widgetNextAutoRefreshAt.set(label, now + intervalMs);
          void refreshWidgetForLabel(label, false);
        }
      }

      async function sendCommand(payload) {
        if (!ipcRenderer) {
          append("[ui] ipc renderer unavailable");
          return { ok: false, error: "ipc_renderer_unavailable" };
        }
        try {
          const response = await ipcRenderer.invoke("mml:agent-command", payload);
          return response;
        } catch (err) {
          const detail = err instanceof Error ? err.message : "command_failed";
          return { ok: false, error: detail };
        }
      }

      async function configureLabel(label) {
        const current = instancesByLabel.get(label);
        if (!current) {
          append("[ui] configure failed: unknown instance " + label);
          return;
        }
        const editable = {
          enabled: current.config.enabled,
          executable: current.config.executable,
          args: current.config.args,
          heartbeat_interval_s: current.config.heartbeat_interval_s,
          agent_flush_interval_s: current.config.agent_flush_interval_s,
          launch_in_separate_terminal: current.config.launch_in_separate_terminal,
        };
        const input = await editJsonModal(
          "Edit JSON for " + label + " (supported keys only)",
          JSON.stringify(editable, null, 2)
        );
        if (input === null) return;
        let parsed;
        try {
          parsed = JSON.parse(input);
        } catch {
          append("[ui] configure failed: invalid JSON");
          return;
        }
        const response = await sendCommand({
          action: "update_agent_instance",
          label,
          updates: parsed,
        });
        if (!response.ok) {
          append("[ipc] update failed for " + label + ": " + (response.error || "unknown_error"));
        }
      }

      async function showAddDialog() {
        if (!ipcRenderer) {
          append("[ui] add failed: ipc renderer unavailable");
          return;
        }
        if (templatesById.size === 0) {
          await refreshTemplatesCache();
        }
        const templateIds = Array.from(templatesById.keys()).sort();
        if (templateIds.length === 0) {
          append("[ui] no templates available (templates cache empty)");
          return;
        }
        const selection = await pickTemplateModal(templateIds);
        if (selection === null) return;
        const templateId = selection.template_id.trim();
        if (!templatesById.has(templateId)) {
          append("[ui] unknown template: " + templateId);
          return;
        }
        const payload = {
          action: "add_agent_instance",
          template_id: templateId,
        };
        if (selection.requested_label && selection.requested_label.trim()) {
          payload.requested_label = selection.requested_label.trim();
        }
        const response = await sendCommand(payload);
        if (!response.ok) {
          append("[ipc] add failed: " + (response.error || "unknown_error"));
        }
      }

      async function configureMonitorSettings() {
        if (!ipcRenderer) {
          append("[ui] monitor settings unavailable: ipc renderer missing");
          return;
        }
        let current = monitorSettingsState;
        try {
          const currentResponse = await ipcRenderer.invoke("mml:get-monitor-settings");
          if (currentResponse && currentResponse.ok && currentResponse.monitor) {
            current = normalizeMonitorSettings(currentResponse.monitor);
            renderMonitorSettings(current);
          }
        } catch (err) {
          const detail = err instanceof Error ? err.message : "monitor_settings_read_failed";
          append("[ui] monitor settings read failed: " + detail);
        }

        const updates = await editMonitorSettingsModal(current);
        if (updates === null) {
          return;
        }

        try {
          const response = await ipcRenderer.invoke("mml:update-monitor-settings", { updates });
          if (!response || !response.ok) {
            const errText = response && response.error ? String(response.error) : "monitor_settings_update_failed";
            append("[ui] monitor settings update failed: " + errText);
            return;
          }
          if (response.data && response.data.monitor) {
            renderMonitorSettings(response.data.monitor);
          }
          append("[ui] monitor settings updated");
        } catch (err) {
          const detail = err instanceof Error ? err.message : "monitor_settings_update_failed";
          append("[ui] monitor settings update failed: " + detail);
        }
      }

      async function showInstallDialog(initialZipPath) {
        if (!installDevMode) {
          append("[install] blocked: developer mode is required");
          showToast("Plugin zip install is disabled outside --dev mode", "warn");
          return;
        }
        if (!ipcRenderer) {
          append("[ui] install failed: ipc renderer unavailable");
          return;
        }

        await showModal((card, close) => {
          const title = document.createElement("div");
          title.className = "modal-title";
          title.textContent = "Install or upgrade plugin";

          const body = document.createElement("div");
          body.className = "modal-body";

          const zipLabel = document.createElement("label");
          zipLabel.textContent = "Plugin zip path";
          const zipInput = document.createElement("input");
          zipInput.placeholder = "/path/to/plugin.zip";
          if (typeof initialZipPath === "string" && initialZipPath.trim().length > 0) {
            zipInput.value = initialZipPath.trim();
          }
          zipLabel.appendChild(zipInput);

          const zipActions = document.createElement("div");
          zipActions.className = "modal-actions";
          zipActions.style.marginTop = "0";
          zipActions.style.justifyContent = "space-between";
          const inspectBtn = document.createElement("button");
          inspectBtn.textContent = "Inspect";
          const browseBtn = document.createElement("button");
          browseBtn.textContent = "Browse…";
          zipActions.appendChild(inspectBtn);
          zipActions.appendChild(browseBtn);

          const classLabel = document.createElement("label");
          classLabel.textContent = "Plugin class";
          const classSelect = document.createElement("select");
          classSelect.disabled = true;
          classLabel.appendChild(classSelect);

          const actionLabel = document.createElement("label");
          actionLabel.textContent = "Action";
          const actionSelect = document.createElement("select");
          actionSelect.disabled = true;
          const actionInstall = document.createElement("option");
          actionInstall.value = "install";
          actionInstall.textContent = "install";
          const actionUpgrade = document.createElement("option");
          actionUpgrade.value = "upgrade";
          actionUpgrade.textContent = "upgrade";
          actionSelect.appendChild(actionInstall);
          actionSelect.appendChild(actionUpgrade);
          actionLabel.appendChild(actionSelect);

          const details = document.createElement("textarea");
          details.readOnly = true;
          details.value = "Inspect a plugin archive to validate it and choose install/upgrade.";

          body.appendChild(zipLabel);
          body.appendChild(zipActions);
          body.appendChild(classLabel);
          body.appendChild(actionLabel);
          body.appendChild(details);

          const actions = document.createElement("div");
          actions.className = "modal-actions";
          const cancelBtn = document.createElement("button");
          cancelBtn.textContent = "Cancel";
          cancelBtn.addEventListener("click", () => close(null));
          const installBtn = document.createElement("button");
          installBtn.textContent = "Run";
          installBtn.disabled = true;
          actions.appendChild(cancelBtn);
          actions.appendChild(installBtn);

          card.appendChild(title);
          card.appendChild(body);
          card.appendChild(actions);

          async function runInspection() {
            const zipPath = zipInput.value.trim();
            if (!zipPath) {
              details.value = "Select a zip path first.";
              installBtn.disabled = true;
              classSelect.disabled = true;
              actionSelect.disabled = true;
              return;
            }

            details.value = "Inspecting archive...";
            installBtn.disabled = true;
            classSelect.disabled = true;
            actionSelect.disabled = true;

            try {
              const response = await ipcRenderer.invoke("mml:inspect-plugin-archive", {
                zip_path: zipPath,
              });
              if (!(response && response.ok && response.data && response.data.inspection)) {
                const errText = response && response.error ? String(response.error) : "inspection_failed";
                details.value = "Inspection failed: " + errText;
                return;
              }

              const inspection = response.data.inspection;
              const allowedRaw = Array.isArray(inspection.allowed_plugin_classes)
                ? inspection.allowed_plugin_classes
                : [];
              const allowed = allowedRaw
                .map((v) => String(v))
                .filter((v) => v === "agents" || v === "reporters" || v === "widgets");
              classSelect.innerHTML = "";
              for (const pluginClass of allowed) {
                const option = document.createElement("option");
                option.value = pluginClass;
                option.textContent = pluginClass;
                classSelect.appendChild(option);
              }
              if (classSelect.options.length === 0) {
                const fallback = document.createElement("option");
                fallback.value = "agents";
                fallback.textContent = "agents";
                classSelect.appendChild(fallback);
              }
              const suggestedClass = typeof inspection.suggested_plugin_class === "string"
                ? inspection.suggested_plugin_class
                : "agents";
              classSelect.value = classSelect.querySelector('option[value="' + suggestedClass + '"]')
                ? suggestedClass
                : classSelect.options[0].value;

              const suggestedAction = inspection.suggested_action === "upgrade" ? "upgrade" : "install";
              actionSelect.value = suggestedAction;

              classSelect.disabled = false;
              actionSelect.disabled = false;
              installBtn.disabled = false;

              const latest = inspection.latest_installed_version_for_suggested_class || "none";
              const manifestClass = inspection.manifest_plugin_class || "(not declared)";
              details.value = [
                "validated",
                "plugin_id: " + String(inspection.plugin_id || ""),
                "version: " + String(inspection.version || ""),
                "entry: " + String(inspection.entry || ""),
                "manifest_plugin_class: " + String(manifestClass),
                "suggested_plugin_class: " + String(suggestedClass),
                "latest_installed_version: " + String(latest),
                "suggested_action: " + String(suggestedAction),
              ].join("\\n");
            } catch (err) {
              const detail = err instanceof Error ? err.message : "inspection_failed";
              details.value = "Inspection failed: " + detail;
            }
          }

          inspectBtn.addEventListener("click", () => {
            void runInspection();
          });

          browseBtn.addEventListener("click", async () => {
            try {
              const response = await ipcRenderer.invoke("mml:pick-plugin-archive");
              if (
                response &&
                response.ok &&
                typeof response.zip_path === "string" &&
                response.zip_path.trim().length > 0
              ) {
                zipInput.value = response.zip_path.trim();
                await runInspection();
              }
            } catch (err) {
              const detail = err instanceof Error ? err.message : "browse_failed";
              details.value = "Browse failed: " + detail;
            }
          });

          installBtn.addEventListener("click", async () => {
            const zipPath = zipInput.value.trim();
            const pluginClass = classSelect.value.trim() || "agents";
            const action = actionSelect.value === "upgrade" ? "upgrade" : "install";
            if (!zipPath) {
              details.value = "Zip path is required.";
              return;
            }
            details.value = "Running " + action + "...";
            try {
              const response = await ipcRenderer.invoke("mml:install-plugin", {
                action,
                plugin_class: pluginClass,
                zip_path: zipPath,
              });
              if (!response || !response.ok) {
                const errText = response && response.error ? String(response.error) : "install_failed";
                details.value = "Install failed: " + errText;
                append("[ipc] plugin install failed: " + errText);
                return;
              }
              const result = response.data && response.data.install_result ? response.data.install_result : {};
              const pluginId = typeof result.plugin_id === "string" ? result.plugin_id : "unknown_plugin";
              const version = typeof result.version === "string" ? result.version : "unknown_version";
              append("[ipc] plugin " + action + " complete: " + pluginId + "@" + version + " (" + pluginClass + ")");
              void refreshTemplatesCache();
              close({ ok: true });
            } catch (err) {
              const detail = err instanceof Error ? err.message : "install_failed";
              details.value = "Install failed: " + detail;
              append("[ipc] plugin install failed: " + detail);
            }
          });

          zipInput.focus();
          if (zipInput.value.trim().length > 0) {
            void runInspection();
          }
        });
      }

      async function installArchivePassive(zipPath) {
        if (!installDevMode) {
          append("[install] blocked: drag/drop install requires developer mode");
          showToast("Drag/drop install is disabled outside --dev mode", "warn");
          return;
        }
        if (!ipcRenderer) {
          append("[install] failed: ipc renderer unavailable");
          return;
        }
        const normalized = typeof zipPath === "string" ? zipPath.trim() : "";
        if (!normalized) {
          append("[install] failed: zip path missing");
          showToast("Install failed: zip path missing", "err");
          return;
        }
        if (!normalized.toLowerCase().endsWith(".zip")) {
          append("[install] skipped non-zip: " + normalized);
          showToast("Skipped non-zip drop", "warn");
          return;
        }

        append("[install] drop accepted: " + normalized);
        showToast("Drop accepted: inspecting archive", "warn");
        try {
          const inspectResponse = await ipcRenderer.invoke("mml:inspect-plugin-archive", {
            zip_path: normalized,
          });
          if (!(inspectResponse && inspectResponse.ok && inspectResponse.data && inspectResponse.data.inspection)) {
            const errText = inspectResponse && inspectResponse.error ? String(inspectResponse.error) : "inspection_failed";
            append("[install] inspect failed: " + errText);
            showToast("Inspect failed: " + errText, "err");
            return;
          }

          const inspection = inspectResponse.data.inspection;
          const pluginId = typeof inspection.plugin_id === "string" ? inspection.plugin_id : "unknown_plugin";
          const version = typeof inspection.version === "string" ? inspection.version : "unknown_version";
          const pluginClass = typeof inspection.suggested_plugin_class === "string"
            ? inspection.suggested_plugin_class
            : "agents";
          const action = inspection.suggested_action === "upgrade" ? "upgrade" : "install";
          append("[install] validated " + pluginId + "@" + version + " (" + pluginClass + ", " + action + ")");
          showToast("Validated " + pluginId + "@" + version + " (" + action + ")", "ok");

          const installResponse = await ipcRenderer.invoke("mml:install-plugin", {
            action,
            plugin_class: pluginClass,
            zip_path: normalized,
          });
          if (!installResponse || !installResponse.ok) {
            const errText = installResponse && installResponse.error ? String(installResponse.error) : "install_failed";
            append("[install] failed: " + errText);
            showToast("Install failed: " + errText, "err");
            return;
          }

          const result = installResponse.data && installResponse.data.install_result ? installResponse.data.install_result : {};
          const installedPluginId = typeof result.plugin_id === "string" ? result.plugin_id : pluginId;
          const installedVersion = typeof result.version === "string" ? result.version : version;
          append("[install] complete: " + installedPluginId + "@" + installedVersion + " (" + pluginClass + ")");
          showToast("Installed " + installedPluginId + "@" + installedVersion, "ok");
          await refreshTemplatesCache();
        } catch (err) {
          const detail = err instanceof Error ? err.message : "install_failed";
          append("[install] failed: " + detail);
          showToast("Install failed: " + detail, "err");
        }
      }

      async function refreshTemplatesCache() {
        if (!ipcRenderer) {
          return;
        }
        try {
          const refresh = await ipcRenderer.invoke("mml:list-agent-templates");
          if (!(refresh && refresh.ok && refresh.templates)) {
            return;
          }
          templatesById.clear();
          for (const [k, v] of Object.entries(refresh.templates)) {
            templatesById.set(k, v);
          }
        } catch (err) {
          const detail = err instanceof Error ? err.message : "template_refresh_failed";
          append("[ui] template refresh failed: " + detail);
        }
      }

      function ensureCard(label) {
        if (cards.has(label)) return cards.get(label);
        const el = document.createElement("div");
        el.className = "agent-card";
        el.dataset.label = label;
        el.innerHTML = \`
          <div class="agent-top">
            <div class="agent-label">\${label}</div>
            <div class="agent-icons">
              <button class="icon-btn js-dup" title="Duplicate instance" aria-label="Duplicate instance">⧉</button>
              <button class="icon-btn js-del" title="Remove instance" aria-label="Remove instance">−</button>
              <button class="icon-btn js-cfg" title="Configure instance" aria-label="Configure instance">⚙</button>
            </div>
          </div>
          <div class="agent-meta">
            <div class="signal-group">
              <div class="light light-inactive js-life"></div>
              <div class="signal-text js-state-text">inactive</div>
            </div>
            <div class="signal-group">
              <div class="light light-inactive js-tx"></div>
              <div class="signal-text">tx</div>
            </div>
            <div class="signal-group">
              <div class="light light-inactive js-rx"></div>
              <div class="signal-text">rx</div>
            </div>
            <div class="signal-group">
              <div class="light light-inactive light-small js-bg"></div>
              <div class="signal-text">bg</div>
            </div>
          </div>
          <div class="agent-detail js-detail">configured</div>
          <div class="agent-actions">
            <button data-action="start_agent">start</button>
            <button data-action="stop_agent">stop</button>
            <button data-action="restart_agent">restart</button>
          </div>
          <div class="widget-head">
            <div class="signal-text">widget canvas</div>
            <div class="widget-controls">
              <button class="mini-btn js-widget-refresh" title="Request widget update">update</button>
              <button class="mini-btn js-widget-toggle" title="Pause widget auto-refresh">pause</button>
            </div>
          </div>
          <div class="widget-canvas js-widget-canvas widget-muted">widget canvas waiting: pending</div>
          <div class="agent-detail js-widget-manifest">manifest: pending</div>
          <div class="agent-detail js-widget-status">render: pending</div>
        \`;
        el.querySelectorAll("button[data-action]").forEach((button) => {
          button.addEventListener("click", async () => {
            const action = button.dataset.action;
            if (!action) return;
            const response = await sendCommand({ action, label });
            if (!response.ok) {
              append("[ipc] " + action + " failed for " + label + ": " + (response.error || "unknown_error"));
            }
          });
        });
        const dup = el.querySelector(".js-dup");
        const del = el.querySelector(".js-del");
        const cfg = el.querySelector(".js-cfg");
        dup.addEventListener("click", async () => {
          const response = await sendCommand({
            action: "duplicate_agent_instance",
            label,
          });
          if (!response.ok) {
            append("[ipc] duplicate failed for " + label + ": " + (response.error || "unknown_error"));
          }
        });
        del.addEventListener("click", async () => {
          const ok = await confirmModal("Remove instance '" + label + "'?");
          if (!ok) return;
          const response = await sendCommand({
            action: "remove_agent_instance",
            label,
          });
          if (!response.ok) {
            append("[ipc] remove failed for " + label + ": " + (response.error || "unknown_error"));
          }
        });
        cfg.addEventListener("click", () => {
          void configureLabel(label);
        });
        const widgetRefresh = el.querySelector(".js-widget-refresh");
        const widgetToggle = el.querySelector(".js-widget-toggle");
        widgetRefresh.addEventListener("click", () => {
          void refreshWidgetForLabel(label, true);
        });
        widgetToggle.addEventListener("click", () => {
          const paused = widgetPausedLabels.has(label);
          setWidgetPaused(label, !paused);
        });
        setWidgetPaused(label, false);
        cardsRoot.appendChild(el);
        cards.set(label, el);
        return el;
      }

      function renderInstances(instances) {
        const labels = Object.keys(instances).sort();
        instancesByLabel.clear();
        for (const label of labels) {
          const instance = instances[label];
          instancesByLabel.set(label, instance);
          const isNewCard = !cards.has(label);
          const card = ensureCard(label);
          const life = card.querySelector(".js-life");
          const stateText = card.querySelector(".js-state-text");
          const detail = card.querySelector(".js-detail");
          const state = instance && instance.state ? instance.state : "inactive";
          const info = instance && instance.detail ? instance.detail : "configured";
          const bgLight = card.querySelector(".js-bg");
          applyLifeClass(life, state);
          stateText.textContent = state;
          detail.textContent = info;
          if (state === "running") {
            setBgLightState(bgLight, "online");
          } else if (state === "error") {
            setBgLightState(bgLight, "offline");
          } else {
            setBgLightState(bgLight, "neutral");
          }
          if (isNewCard) {
            if (state === "running") {
              const intervalMs = resolveWidgetAutoRefreshMs(instance);
              widgetNextAutoRefreshAt.set(label, Date.now() + intervalMs);
              void refreshWidgetForLabel(label, false);
            } else {
              widgetNextAutoRefreshAt.delete(label);
            }
          } else if (state !== "running") {
            widgetNextAutoRefreshAt.delete(label);
          }
        }

        for (const [label, card] of cards.entries()) {
          if (labels.includes(label)) continue;
          card.remove();
          cards.delete(label);
          instancesByLabel.delete(label);
          widgetPausedLabels.delete(label);
          widgetInFlight.delete(label);
          widgetManifestLoaded.delete(label);
          widgetNextAutoRefreshAt.delete(label);
          perAgentTxIndicators.delete(label);
          perAgentRxIndicators.delete(label);
        }
      }

      async function refreshInitialState() {
        if (!ipcRenderer) {
          setStatus("disconnected - ipc_renderer_unavailable");
          return;
        }
        try {
          const state = await ipcRenderer.invoke("mml:initial-state");
          ipcPathEl.textContent = state.ipcPath || "(unset)";
          opsLogPathEl.textContent = state.opsLogPath || "(unset)";
          setStatus(state.status.state + " - " + state.status.detail);
          applyGlobalBgState(state.status.state, state.status.detail);
          renderOpsProcessState(state.opsControl || {});
          renderMonitorSettings(state.monitorSettings || null);
          renderInstances(state.instances || {});
        } catch (err) {
          const detail = err instanceof Error ? err.message : "initial_state_failed";
          setStatus("disconnected - " + detail);
        }
      }

      void refreshInitialState();

      if (!ipcRenderer) {
        append("[proto] electron ipcRenderer unavailable in renderer");
      } else {
        if (opsStartBtn) {
          opsStartBtn.addEventListener("click", () => {
            void runOpsControl("start");
          });
        }
        if (opsStopBtn) {
          opsStopBtn.addEventListener("click", () => {
            void runOpsControl("stop");
          });
        }
        if (opsRestartBtn) {
          opsRestartBtn.addEventListener("click", () => {
            void runOpsControl("restart");
          });
        }
        if (installDevMode) {
          append("[dev] unsigned plugin zip install enabled (signature allowlist is not implemented yet)");
        }
        if (monitorSettingsBtn) {
          monitorSettingsBtn.addEventListener("click", () => {
            void configureMonitorSettings();
          });
        } else {
          append("[ui] monitor settings button not found in DOM");
        }
        if (!addAgentBtn) {
          append("[ui] add button not found in DOM");
        } else {
          addAgentBtn.addEventListener("click", () => {
            void showAddDialog();
          });
        }
        if (installDevMode) {
          if (!installPluginBtn) {
            append("[ui] install button not found in DOM (developer mode)");
          } else {
            installPluginBtn.addEventListener("click", () => {
              void showInstallDialog("");
            });
          }
        }
        if (installDevMode && dropHint) {
          let dropDepth = 0;
          const showDropHint = () => {
            dropHint.hidden = false;
          };
          const hideDropHint = () => {
            dropHint.hidden = true;
          };
          window.addEventListener("dragenter", (event) => {
            event.preventDefault();
            dropDepth += 1;
            showDropHint();
          });
          window.addEventListener("dragover", (event) => {
            event.preventDefault();
            showDropHint();
          });
          window.addEventListener("dragleave", (event) => {
            event.preventDefault();
            dropDepth = Math.max(0, dropDepth - 1);
            if (dropDepth === 0 && event.relatedTarget === null) {
              hideDropHint();
            }
          });
          window.addEventListener("drop", (event) => {
            event.preventDefault();
            dropDepth = 0;
            hideDropHint();
            const files = event.dataTransfer && event.dataTransfer.files
              ? event.dataTransfer.files
              : null;
            if (!files || files.length === 0) {
              append("[install] drop ignored: no files");
              return;
            }
            for (const file of files) {
              const droppedPath = typeof file.path === "string" ? file.path.trim() : "";
              if (!droppedPath) {
                append("[install] dropped item has no local file path");
                continue;
              }
              void installArchivePassive(droppedPath);
            }
          });
        }
        void refreshTemplatesCache();
        setInterval(() => {
          void refreshTemplatesCache();
        }, 4500);
        setInterval(() => {
          refreshWidgetsAuto();
        }, WIDGET_AUTO_TICK_MS);
        ipcRenderer.on("ops:status", (_event, payload) => {
          setStatus(payload.state + " - " + payload.detail);
          applyGlobalBgState(payload.state, payload.detail);
        });

        ipcRenderer.on("ops:line", (_event, line) => {
          append(line);
        });

        ipcRenderer.on("ops:instances", (_event, payload) => {
          renderInstances(payload.instances || {});
        });

        ipcRenderer.on("ops:process", (_event, payload) => {
          renderOpsProcessState(payload || {});
        });

        ipcRenderer.on("ops:monitor-settings", (_event, payload) => {
          const monitor = payload && payload.monitor ? payload.monitor : null;
          renderMonitorSettings(monitor);
        });

        ipcRenderer.on("ops:traffic", (_event, payload) => {
          if (!payload) {
            return;
          }
          const direction = payload.direction === "tx" ? "tx" : "rx";
          if (direction === "tx") {
            globalTxIndicator.trigger();
          } else {
            globalRxIndicator.trigger();
          }
          if (payload.label) {
            const indicator = direction === "tx"
              ? getAgentTxIndicator(payload.label)
              : getAgentRxIndicator(payload.label);
            if (indicator) {
              indicator.trigger();
            }
          }
        });
      }
    </script>
  </body>
</html>`;
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
    ? `exec poetry run python -m mimolo.cli monitor --config ${quoteBashArg(configPath)}`
    : "exec poetry run python -m mimolo.cli monitor";
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

async function stopOperationsProcess(): Promise<{
  error?: string;
  ok: boolean;
  state: OperationsControlSnapshot;
}> {
  if (!operationsProcess) {
    if (lastStatus.state === "connected") {
      setOperationsControlState("running", "external_unmanaged", false, null);
      return {
        ok: false,
        error: "operations_not_managed",
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

  const exitedGracefully = await waitForProcessExit(child, 5000);
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
    await waitForProcessExit(child, 1500);
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

function setStatus(state: OpsStatusPayload["state"], detail: string): void {
  lastStatus = {
    state,
    detail,
    timestamp: new Date().toISOString(),
  };
  if (!mainWindow) {
    return;
  }
  mainWindow.webContents.send("ops:status", lastStatus);
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
  return Math.max(250, Math.round(settings.poll_tick_s * 1000));
}

function deriveInstanceLoopMs(settings: MonitorSettingsSnapshot): number {
  return Math.max(250, Math.round(settings.poll_tick_s * 1000));
}

function deriveLogLoopMs(settings: MonitorSettingsSnapshot): number {
  return Math.min(3000, Math.max(250, Math.round(settings.poll_tick_s * 1000)));
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

  settleInFlightWithError(reason);
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
        setStatus("disconnected", detail);
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
      }, IPC_REQUEST_TIMEOUT_MS);

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
        setOperationsControlState("running", "external_unmanaged", false, null);
      }
      return;
    }
    setStatus("disconnected", response.error || "ipc_unavailable");
    if (!operationsProcess) {
      setOperationsControlState("stopped", "not_managed", false, null);
    }
  } catch (err) {
    const detail = err instanceof Error ? err.message : "ipc_unavailable";
    setStatus("disconnected", detail);
    if (!operationsProcess) {
      setOperationsControlState("stopped", "not_managed", false, null);
    }
  }
}

async function refreshAgentInstances(): Promise<void> {
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
    lastMonitorSettings = normalizeMonitorSettings(monitorRaw);
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
  lastMonitorSettings = normalizeMonitorSettings(monitorRaw);
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
  haltManagedOperationsForShutdown();
  stopPersistentIpc();
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

  const html = buildHtml();
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
    instances: lastAgentInstances,
  };
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
  const templates = await refreshTemplates();
  return {
    ok: true,
    templates,
  };
});

ipcMain.handle("mml:get-monitor-settings", async () => {
  await refreshMonitorSettings();
  return {
    ok: true,
    monitor: lastMonitorSettings,
  };
});

ipcMain.handle("mml:update-monitor-settings", (_event, payload: unknown) => {
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
  return updateMonitorSettings(updatesRaw as Record<string, unknown>);
});

ipcMain.handle("mml:get-widget-manifest", (_event, payload: unknown) => {
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      error: "invalid_widget_payload",
    };
  }
  return getWidgetManifest(payload as Record<string, unknown>);
});

ipcMain.handle("mml:request-widget-render", (_event, payload: unknown) => {
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      error: "invalid_widget_payload",
    };
  }
  return requestWidgetRender(payload as Record<string, unknown>);
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

  return runAgentCommand(cmd);
});

app.whenReady().then(() => {
  createWindow();
  startBackgroundLoops();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", () => {
  stopBackgroundLoops();
});

app.on("window-all-closed", () => {
  stopBackgroundLoops();
  if (runtimeProcess.platform !== "darwin") {
    app.quit();
  }
});
