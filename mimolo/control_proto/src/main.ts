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

let lastStatus: OpsStatusPayload = {
  state: "starting",
  detail: "waiting_for_operations",
  timestamp: new Date().toISOString(),
};

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
        --text: #d9dee9;
        --muted: #8d98aa;
        --accent: #56d8a9;
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
        border-bottom: 1px solid #2a3140;
        padding: 12px 14px;
        background: rgba(23, 26, 33, 0.8);
      }
      .row { margin: 3px 0; font-size: 12px; color: var(--muted); }
      .row strong { color: var(--text); }
      #status { color: var(--accent); }
      #log {
        margin: 0;
        padding: 12px 14px;
        overflow: auto;
        white-space: pre-wrap;
        line-height: 1.4;
        font-size: 12px;
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
      <pre id="log"></pre>
    </div>
    <script>
      const electronRuntime = typeof require === "function" ? require("electron") : null;
      const ipcRenderer = electronRuntime ? electronRuntime.ipcRenderer : null;
      const statusEl = document.getElementById("status");
      const logEl = document.getElementById("log");
      const ipcPathEl = document.getElementById("ipcPath");
      const opsLogPathEl = document.getElementById("opsLogPath");

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
        ipcRenderer.on("ops:status", (_event, payload) => {
          setStatus(payload.state + " - " + payload.detail);
        });

        ipcRenderer.on("ops:line", (_event, line) => {
          append(line);
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

async function sendIpcCommand(cmd: string): Promise<string> {
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
    }, 400);

    const finishOk = (payload: string): void => {
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

    const client = net.createConnection({ path: ipcPath }, () => {
      client.write(JSON.stringify({ cmd }) + "\n");
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
      if (line.length === 0) {
        finishErr("empty_response");
        return;
      }
      finishOk(line);
    });

    client.on("error", (err: { message: string }) => {
      finishErr(err.message);
    });
  });
}

async function refreshIpcStatus(): Promise<void> {
  try {
    await sendIpcCommand("ping");
    setStatus("connected", "ipc_ready");
  } catch (err) {
    const detail = err instanceof Error ? err.message : "ipc_unavailable";
    setStatus("disconnected", detail);
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
    publishLine(`[ipc] ${response}`);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "plugin_query_failed";
    publishLine(`[ipc] get_registered_plugins failed: ${detail}`);
  }
}

function startBackgroundLoops(): void {
  void loadInitialSnapshot();
  void pumpOpsLog();

  statusTimer = setInterval(() => {
    void refreshIpcStatus();
  }, 900);

  logTimer = setInterval(() => {
    void pumpOpsLog();
  }, 320);
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
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 900,
    minHeight: 580,
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
  };
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
