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

interface AgentStateSnapshot {
  detail: string;
  state: AgentLifecycleState;
}

interface ControlCommandPayload {
  action: "start_agent" | "stop_agent" | "restart_agent";
  label: string;
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
let agentTimer: ReturnType<typeof setInterval> | null = null;

let lastStatus: OpsStatusPayload = {
  state: "starting",
  detail: "waiting_for_operations",
  timestamp: new Date().toISOString(),
};

let lastAgentStates: Record<string, AgentStateSnapshot> = {};

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
        grid-template-columns: minmax(0, 1fr) 360px;
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
      .controls-title {
        font-size: 12px;
        font-weight: 700;
        color: var(--text);
      }
      .controls-sub {
        font-size: 11px;
        color: var(--muted);
      }
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
        align-items: center;
      }
      .agent-label {
        font-size: 12px;
        font-weight: 700;
        color: var(--text);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
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
        margin-top: 8px;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .agent-state {
        font-size: 11px;
        color: var(--text);
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
            <div class="controls-title">Agent Control Panel</div>
            <div class="controls-sub">One card per configured instance</div>
          </div>
          <div class="cards" id="cards"></div>
        </div>
      </div>
    </div>
    <script>
      const electronRuntime = typeof require === "function" ? require("electron") : null;
      const ipcRenderer = electronRuntime ? electronRuntime.ipcRenderer : null;
      const statusEl = document.getElementById("status");
      const logEl = document.getElementById("log");
      const ipcPathEl = document.getElementById("ipcPath");
      const opsLogPathEl = document.getElementById("opsLogPath");
      const cardsRoot = document.getElementById("cards");
      const cards = new Map();

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

      function ensureCard(label) {
        if (cards.has(label)) return cards.get(label);
        const el = document.createElement("div");
        el.className = "agent-card";
        el.dataset.label = label;
        el.innerHTML = \`
          <div class="agent-top">
            <div class="agent-label">\${label}</div>
            <div class="signal-group">
              <div class="light light-inactive js-life"></div>
              <div class="signal-text js-state-text">inactive</div>
            </div>
          </div>
          <div class="agent-meta">
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
          button.addEventListener("click", () => {
            const action = button.dataset.action;
            if (!action) return;
            void runAgentCommand(label, action);
          });
        });
        cardsRoot.appendChild(el);
        cards.set(label, el);
        return el;
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

      function renderAgentStates(agentStates) {
        const labels = Object.keys(agentStates).sort();
        for (const label of labels) {
          const card = ensureCard(label);
          const life = card.querySelector(".js-life");
          const stateText = card.querySelector(".js-state-text");
          const detail = card.querySelector(".js-detail");
          const snapshot = agentStates[label];
          const state = snapshot && snapshot.state ? snapshot.state : "inactive";
          const info = snapshot && snapshot.detail ? snapshot.detail : "configured";
          applyLifeClass(life, state);
          stateText.textContent = state;
          detail.textContent = info;
        }

        for (const [label, card] of cards.entries()) {
          if (labels.includes(label)) continue;
          card.remove();
          cards.delete(label);
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
          renderAgentStates(state.agents || {});
        } catch (err) {
          const detail = err instanceof Error ? err.message : "initial_state_failed";
          setStatus("disconnected - " + detail);
        }
      }

      async function runAgentCommand(label, action) {
        if (!ipcRenderer) {
          append("[ui] ipc renderer unavailable");
          return;
        }
        pulseTxRx(label, "tx");
        try {
          const response = await ipcRenderer.invoke("mml:agent-command", { label, action });
          pulseTxRx(label, "rx");
          if (!response.ok) {
            append("[ipc] " + action + " failed for " + label + ": " + (response.error || "unknown_error"));
          }
        } catch (err) {
          pulseTxRx(label, "rx");
          const detail = err instanceof Error ? err.message : "command_failed";
          append("[ipc] command error for " + label + ": " + detail);
        }
      }

      void refreshInitialState();
      setInterval(() => {
        void refreshInitialState();
      }, 1200);

      if (!ipcRenderer) {
        append("[proto] electron ipcRenderer unavailable in renderer");
      } else {
        ipcRenderer.on("ops:status", (_event, payload) => {
          setStatus(payload.state + " - " + payload.detail);
        });

        ipcRenderer.on("ops:line", (_event, line) => {
          append(line);
        });

        ipcRenderer.on("ops:agents", (_event, payload) => {
          renderAgentStates(payload.agents || {});
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

function publishAgentStates(agents: Record<string, AgentStateSnapshot>): void {
  lastAgentStates = agents;
  if (!mainWindow) {
    return;
  }
  mainWindow.webContents.send("ops:agents", { agents });
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
    data: record.data && typeof record.data === "object" ? (record.data as Record<string, unknown>) : undefined,
  };
}

function extractAgentStates(
  response: IpcResponsePayload,
): Record<string, AgentStateSnapshot> {
  const result: Record<string, AgentStateSnapshot> = {};
  const agentStatesRaw = response.data?.agent_states;
  if (!agentStatesRaw || typeof agentStatesRaw !== "object") {
    return result;
  }

  const map = agentStatesRaw as Record<string, unknown>;
  for (const [label, raw] of Object.entries(map)) {
    if (!raw || typeof raw !== "object") {
      continue;
    }
    const entry = raw as Record<string, unknown>;
    const stateRaw = entry.state;
    const detailRaw = entry.detail;
    const state =
      stateRaw === "running" ||
      stateRaw === "shutting-down" ||
      stateRaw === "inactive" ||
      stateRaw === "error"
        ? stateRaw
        : "inactive";
    const detail = typeof detailRaw === "string" ? detailRaw : "configured";
    result[label] = {
      state,
      detail,
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
    }, 600);

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

async function refreshAgentStates(): Promise<void> {
  try {
    const response = await sendIpcCommand("get_agent_states");
    if (!response.ok) {
      return;
    }
    publishAgentStates(extractAgentStates(response));
  } catch {
    // Ignore transient polling failures; status loop reports IPC health.
  }
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
    const response = await sendIpcCommand("get_registered_plugins");
    publishLine(`[ipc] ${JSON.stringify(response)}`);
    if (response.ok) {
      publishAgentStates(extractAgentStates(response));
    }
  } catch (err) {
    const detail = err instanceof Error ? err.message : "plugin_query_failed";
    publishLine(`[ipc] get_registered_plugins failed: ${detail}`);
  }
}

async function runAgentCommand(
  payload: ControlCommandPayload,
): Promise<IpcResponsePayload> {
  const response = await sendIpcCommand(
    payload.action,
    { label: payload.label },
    payload.label,
  );
  await refreshAgentStates();
  return response;
}

function startBackgroundLoops(): void {
  void loadInitialSnapshot();
  void pumpOpsLog();
  void refreshAgentStates();

  statusTimer = setInterval(() => {
    void refreshIpcStatus();
  }, 900);

  logTimer = setInterval(() => {
    void pumpOpsLog();
  }, 320);

  agentTimer = setInterval(() => {
    void refreshAgentStates();
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
  if (agentTimer) {
    clearInterval(agentTimer);
    agentTimer = null;
  }
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 780,
    minWidth: 1020,
    minHeight: 620,
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
    agents: lastAgentStates,
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
  const labelRaw = raw.label;
  if (
    actionRaw !== "start_agent" &&
    actionRaw !== "stop_agent" &&
    actionRaw !== "restart_agent"
  ) {
    return {
      ok: false,
      error: "invalid_action",
    };
  }
  if (typeof labelRaw !== "string" || labelRaw.trim().length === 0) {
    return {
      ok: false,
      error: "invalid_label",
    };
  }

  const command: ControlCommandPayload = {
    action: actionRaw,
    label: labelRaw.trim(),
  };
  return runAgentCommand(command);
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
