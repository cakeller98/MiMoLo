import { app, BrowserWindow, ipcMain } from "electron";
import { readFile, stat } from "node:fs/promises";
import net from "node:net";

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
  timestamp?: string;
}

interface IpcTrafficPayload {
  direction: "tx" | "rx";
  label?: string;
  timestamp: string;
}

const maybeRuntimeProcess = (globalThis as { process?: RuntimeProcess }).process;

if (!maybeRuntimeProcess) {
  throw new Error("Node.js process global is unavailable");
}
const runtimeProcess: RuntimeProcess = maybeRuntimeProcess;

const ipcPath = runtimeProcess.env.MIMOLO_IPC_PATH || "";
const opsLogPath = runtimeProcess.env.MIMOLO_OPS_LOG_PATH || "";

let mainWindow: BrowserWindow | null = null;
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
      .cards {
        padding: 10px;
        overflow-y: auto;
        min-height: 0;
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
              <button class="add-btn" id="addAgentBtn" title="Add agent instance">+ Add</button>
            </div>
            <div class="controls-sub">Per-instance controls and configuration</div>
          </div>
          <div class="cards" id="cards"></div>
        </div>
      </div>
    </div>
    <div id="modalHost"></div>
    <script>
      const electronRuntime = typeof require === "function" ? require("electron") : null;
      const ipcRenderer = electronRuntime ? electronRuntime.ipcRenderer : null;
      const statusEl = document.getElementById("status");
      const logEl = document.getElementById("log");
      const ipcPathEl = document.getElementById("ipcPath");
      const opsLogPathEl = document.getElementById("opsLogPath");
      const cardsRoot = document.getElementById("cards");
      const addAgentBtn = document.getElementById("addAgentBtn");
      const modalHost = document.getElementById("modalHost");
      const cards = new Map();
      const instancesByLabel = new Map();
      const templatesById = new Map();

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
          const card = ensureCard(label);
          const life = card.querySelector(".js-life");
          const stateText = card.querySelector(".js-state-text");
          const detail = card.querySelector(".js-detail");
          const state = instance && instance.state ? instance.state : "inactive";
          const info = instance && instance.detail ? instance.detail : "configured";
          applyLifeClass(life, state);
          stateText.textContent = state;
          detail.textContent = info;
        }

        for (const [label, card] of cards.entries()) {
          if (labels.includes(label)) continue;
          card.remove();
          cards.delete(label);
          instancesByLabel.delete(label);
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
      setInterval(() => {
        void refreshInitialState();
      }, 1200);

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
        void refreshTemplatesCache();
        setInterval(() => {
          void refreshTemplatesCache();
        }, 4500);
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

  return new Promise((resolve, reject) => {
    let done = false;
    let buffer = "";
    const timeout = setTimeout(() => {
      if (done) {
        return;
      }
      done = true;
      client.destroy();
      reject(new Error("timeout"));
    }, 650);

    const finishOk = (payload: IpcResponsePayload): void => {
      if (done) {
        return;
      }
      done = true;
      clearTimeout(timeout);
      resolve(payload);
    };

    const finishErr = (err: string): void => {
      if (done) {
        return;
      }
      done = true;
      clearTimeout(timeout);
      reject(new Error(err));
    };

    const requestPayload: Record<string, unknown> = {
      cmd,
      ...(extraPayload || {}),
    };

    const client = net.createConnection({ path: ipcPath }, () => {
      publishTraffic("tx", trafficLabel);
      client.write(JSON.stringify(requestPayload) + "\n");
    });

    client.setEncoding("utf8");

    client.on("data", (chunk: string) => {
      buffer += chunk;
      const idx = buffer.indexOf("\n");
      if (idx === -1) {
        return;
      }
      const line = buffer.slice(0, idx).trim();
      client.end();
      publishTraffic("rx", trafficLabel);
      try {
        const parsed = parseIpcResponse(line);
        finishOk(parsed);
      } catch (err) {
        const detail = err instanceof Error ? err.message : "invalid_response";
        finishErr(detail);
      }
    });

    client.on("error", (err: { message: string }) => {
      finishErr(err.message);
    });
  });
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
