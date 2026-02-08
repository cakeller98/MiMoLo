import electronDefault, * as electronNamespace from "electron";
import { readFile, stat } from "node:fs/promises";
import net from "node:net";

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
  platform?: string;
}

interface OpsStatusPayload {
  detail: string;
  state: "connected" | "disconnected" | "starting";
  timestamp: string;
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
  label?: string;
  timestamp: string;
}

interface PendingIpcRequest {
  id: string;
  payload: Record<string, unknown>;
  reject: (reason: Error) => void;
  resolve: (value: IpcResponsePayload) => void;
  timeoutHandle: ReturnType<typeof setTimeout> | null;
  trafficLabel?: string;
}

const maybeRuntimeProcess = (globalThis as { process?: RuntimeProcess }).process;

if (!maybeRuntimeProcess) {
  throw new Error("Node.js process global is unavailable");
}
const runtimeProcess: RuntimeProcess = maybeRuntimeProcess;

const ipcPath = runtimeProcess.env.MIMOLO_IPC_PATH || "";
const opsLogPath = runtimeProcess.env.MIMOLO_OPS_LOG_PATH || "";

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

let lastAgentInstances: Record<string, AgentInstanceSnapshot> = {};

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
      .tx-flash { background: #2fcf70; box-shadow: 0 0 10px rgba(47, 207, 112, 0.8); }
      .rx-flash { background: #d94c4c; box-shadow: 0 0 10px rgba(217, 76, 76, 0.8); }
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
        <div class="row"><strong>MiMoLo Control Proto</strong> - operations stream viewer</div>
        <div class="row">IPC: <span id="ipcPath"></span></div>
        <div class="row">Ops log: <span id="opsLogPath"></span></div>
        <div class="row">Status: <span id="status">starting</span></div>
      </div>
      <div class="main">
        <div class="log-pane"><pre id="log"></pre></div>
        <div class="controls">
          <div class="controls-head">
            <div class="controls-row">
              <div class="controls-title">Agent Control Panel</div>
              <div class="controls-actions">
                <button class="install-btn" id="installPluginBtn" title="Install or upgrade plugin zip">Install</button>
                <button class="add-btn" id="addAgentBtn" title="Add agent instance">+ Add</button>
              </div>
            </div>
            <div class="controls-sub">Per-instance controls and configuration</div>
          </div>
          <div class="cards" id="cards"></div>
        </div>
      </div>
    </div>
    <div id="dropHint" class="drop-hint" hidden>Drop plugin zip to install</div>
    <div id="modalHost"></div>
    <div id="toastHost" class="toast-host"></div>
    <script>
      const electronRuntime = typeof require === "function" ? require("electron") : null;
      const ipcRenderer = electronRuntime ? electronRuntime.ipcRenderer : null;
      const statusEl = document.getElementById("status");
      const logEl = document.getElementById("log");
      const ipcPathEl = document.getElementById("ipcPath");
      const opsLogPathEl = document.getElementById("opsLogPath");
      const cardsRoot = document.getElementById("cards");
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
      let dropDepth = 0;

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

      function applyLifeClass(light, state) {
        light.classList.remove("light-running", "light-shutting-down", "light-inactive", "light-error");
        light.classList.add("light-" + state);
      }

      function pulseTxRx(label, direction) {
        const card = cards.get(label);
        if (!card) return;
        const txrx = card.querySelector(".js-txrx");
        if (!txrx) return;
        txrx.classList.remove("tx-flash", "rx-flash");
        txrx.classList.add(direction === "tx" ? "tx-flash" : "rx-flash");
        setTimeout(() => {
          txrx.classList.remove("tx-flash", "rx-flash");
          txrx.classList.add("light-inactive");
        }, 180);
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
            const manifest = await ipcRenderer.invoke("mml:get-widget-manifest", identity);
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
            const length = render.html.length;
            canvasEl.textContent = "render fragment ready (" + length + " bytes)";
            canvasEl.classList.remove("widget-muted");
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
        }
      }

      function refreshWidgetsAuto() {
        for (const label of cards.keys()) {
          if (widgetPausedLabels.has(label)) {
            continue;
          }
          void refreshWidgetForLabel(label, false);
        }
      }

      async function sendCommand(payload) {
        if (!ipcRenderer) {
          append("[ui] ipc renderer unavailable");
          return { ok: false, error: "ipc_renderer_unavailable" };
        }
        if (payload.label) pulseTxRx(payload.label, "tx");
        try {
          const response = await ipcRenderer.invoke("mml:agent-command", payload);
          if (payload.label) pulseTxRx(payload.label, "rx");
          return response;
        } catch (err) {
          if (payload.label) pulseTxRx(payload.label, "rx");
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

      async function showInstallDialog(initialZipPath) {
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
              <div class="light light-inactive js-txrx"></div>
              <div class="signal-text">tx/rx</div>
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
          applyLifeClass(life, state);
          stateText.textContent = state;
          detail.textContent = info;
          if (isNewCard) {
            void refreshWidgetForLabel(label, false);
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
        if (!addAgentBtn) {
          append("[ui] add button not found in DOM");
        } else {
          addAgentBtn.addEventListener("click", () => {
            void showAddDialog();
          });
        }
        if (!installPluginBtn) {
          append("[ui] install button not found in DOM");
        } else {
          installPluginBtn.addEventListener("click", () => {
            void showInstallDialog("");
          });
        }
        if (dropHint) {
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
        }, 2500);
        ipcRenderer.on("ops:status", (_event, payload) => {
          setStatus(payload.state + " - " + payload.detail);
        });

        ipcRenderer.on("ops:line", (_event, line) => {
          append(line);
        });

        ipcRenderer.on("ops:instances", (_event, payload) => {
          renderInstances(payload.instances || {});
        });

        ipcRenderer.on("ops:traffic", (_event, payload) => {
          if (!payload || !payload.label) {
            return;
          }
          pulseTxRx(payload.label, payload.direction === "tx" ? "tx" : "rx");
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

function publishTraffic(direction: "tx" | "rx", label?: string): void {
  if (!mainWindow) {
    return;
  }
  const payload: IpcTrafficPayload = {
    direction,
    label,
    timestamp: new Date().toISOString(),
  };
  mainWindow.webContents.send("ops:traffic", payload);
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

async function sendIpcCommand(
  cmd: string,
  extraPayload?: Record<string, unknown>,
  trafficLabel?: string,
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
  publishTraffic("rx", request.trafficLabel);
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
      publishTraffic("tx", nextRequest.trafficLabel);
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
    const response = await sendIpcCommand("ping");
    if (response.ok) {
      setStatus("connected", "ipc_ready");
      return;
    }
    setStatus("disconnected", response.error || "ipc_unavailable");
  } catch (err) {
    const detail = err instanceof Error ? err.message : "ipc_unavailable";
    setStatus("disconnected", detail);
  }
}

async function refreshAgentInstances(): Promise<void> {
  try {
    const response = await sendIpcCommand("get_agent_instances");
    if (!response.ok) {
      return;
    }
    publishInstances(extractAgentInstances(response));
  } catch {
    // Ignore transient polling failures; status loop reports IPC health.
  }
}

async function refreshTemplates(): Promise<Record<string, AgentTemplateSnapshot>> {
  const response = await sendIpcCommand("list_agent_templates");
  if (!response.ok) {
    return {};
  }
  return extractTemplates(response);
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
    const detail = err instanceof Error ? err.message : "ops_log_read_failed";
    setStatus("disconnected", `ops_log_error:${detail}`);
  }
}

async function loadInitialSnapshot(): Promise<void> {
  await refreshIpcStatus();
  try {
    const registeredResponse = await sendIpcCommand("get_registered_plugins");
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
  return sendIpcCommand(
    "get_widget_manifest",
    {
      plugin_id: pluginId,
      instance_id: instanceId,
    },
    instanceId,
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
  );
}

async function inspectPluginArchive(
  payload: Record<string, unknown>,
): Promise<IpcResponsePayload> {
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

function startBackgroundLoops(): void {
  void loadInitialSnapshot();
  void pumpOpsLog();
  void refreshAgentInstances();

  statusTimer = setInterval(() => {
    void refreshIpcStatus();
  }, 900);

  logTimer = setInterval(() => {
    void pumpOpsLog();
  }, 320);

  instanceTimer = setInterval(() => {
    void refreshAgentInstances();
  }, 950);
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
    instances: lastAgentInstances,
  };
});

ipcMain.handle("mml:list-agent-templates", async () => {
  const templates = await refreshTemplates();
  return {
    ok: true,
    templates,
  };
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
