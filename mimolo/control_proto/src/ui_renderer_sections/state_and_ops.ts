export function buildStateAndOpsSection(controlDevMode: boolean): string {
  return `
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
      const bootstrapOverlayEl = document.getElementById("bootstrapOverlay");
      const bootstrapStageEl = document.getElementById("bootstrapStage");
      const bootstrapPathEl = document.getElementById("bootstrapPath");
      const bootstrapProgressFillEl = document.getElementById("bootstrapProgressFill");
      const bootstrapProgressLabelEl = document.getElementById("bootstrapProgressLabel");
      const bootstrapLogEl = document.getElementById("bootstrapLog");
      const bootstrapAcknowledgeBtn = document.getElementById("bootstrapAcknowledgeBtn");
      const cards = new Map();
      const instancesByLabel = new Map();
      const templatesById = new Map();
      const widgetPausedLabels = new Set();
      const widgetInFlight = new Set();
      const widgetManifestLoaded = new Set();
      const widgetNextAutoRefreshAt = new Map();
      let opsConnected = false;
      let monitorSettingsState = {
        cooldown_seconds: 600,
        poll_tick_s: 0.2,
        console_verbosity: "info",
      };

      const lines = [];
      const maxLines = 1800;
      const bootstrapLines = [];
      const maxBootstrapLines = 220;
      const bootstrapState = {
        done: false,
        failed: false,
        hidden: false,
        progress: 0,
      };
      let bootstrapAutoStartAttempted = false;

      function append(line) {
        lines.push(line);
        if (lines.length > maxLines) lines.shift();
        logEl.textContent = lines.join("\\n");
        logEl.scrollTop = logEl.scrollHeight;
        updateBootstrapFromLine(line);
      }

      function setStatus(text) {
        statusEl.textContent = text;
        if (text.startsWith("connected -") && !bootstrapState.done && !bootstrapState.failed) {
          setBootstrapProgress(100, "Runtime ready");
          setBootstrapDone();
          setTimeout(() => {
            maybeHideBootstrapOverlay();
          }, 350);
        }
      }

      function renderBootstrapLog() {
        if (!bootstrapLogEl) {
          return;
        }
        bootstrapLogEl.textContent = bootstrapLines.join("\\n");
        bootstrapLogEl.scrollTop = bootstrapLogEl.scrollHeight;
      }

      function appendBootstrapLine(line) {
        bootstrapLines.push(line);
        if (bootstrapLines.length > maxBootstrapLines) {
          bootstrapLines.shift();
        }
        renderBootstrapLog();
      }

      function setBootstrapPath(pathText) {
        if (!bootstrapPathEl) {
          return;
        }
        bootstrapPathEl.textContent = pathText || "";
      }

      function setBootstrapProgress(progress, stage) {
        const clamped = Math.max(0, Math.min(100, Math.round(progress)));
        bootstrapState.progress = clamped;
        if (bootstrapStageEl) {
          bootstrapStageEl.textContent = stage;
        }
        if (bootstrapProgressFillEl) {
          bootstrapProgressFillEl.style.width = String(clamped) + "%";
        }
        if (bootstrapProgressLabelEl) {
          bootstrapProgressLabelEl.textContent = String(clamped) + "%";
        }
      }

      function setBootstrapDone() {
        bootstrapState.done = true;
        bootstrapState.failed = false;
        if (bootstrapAcknowledgeBtn) {
          bootstrapAcknowledgeBtn.disabled = false;
        }
      }

      function setBootstrapFailed(detail) {
        bootstrapState.failed = true;
        if (bootstrapStageEl) {
          bootstrapStageEl.textContent = "Runtime bootstrap failed";
        }
        appendBootstrapLine(detail);
        if (bootstrapAcknowledgeBtn) {
          bootstrapAcknowledgeBtn.disabled = false;
        }
      }

      function maybeHideBootstrapOverlay() {
        if (!bootstrapOverlayEl || bootstrapState.hidden !== false) {
          return;
        }
        bootstrapOverlayEl.hidden = true;
        bootstrapState.hidden = true;
      }

      if (bootstrapAcknowledgeBtn) {
        bootstrapAcknowledgeBtn.addEventListener("click", () => {
          if (!bootstrapState.done && !bootstrapState.failed) {
            return;
          }
          maybeHideBootstrapOverlay();
        });
      }

      function parseBootstrapPath(line, marker) {
        const idx = line.indexOf(marker);
        if (idx < 0) {
          return "";
        }
        return line.slice(idx + marker.length).trim();
      }

      function updateBootstrapFromLine(line) {
        const raw = typeof line === "string" ? line.trim() : "";
        if (!raw) {
          return;
        }
        if (!raw.includes("[bootstrap]") && !raw.includes("[ops]") && !raw.includes("[control]")) {
          return;
        }
        appendBootstrapLine(raw);

        if (raw.includes("[ops] preparing portable runtime")) {
          setBootstrapProgress(Math.max(bootstrapState.progress, 5), "Preparing runtime");
          return;
        }
        if (raw.includes("[control] preparing portable runtime")) {
          setBootstrapProgress(Math.max(bootstrapState.progress, 8), "Preparing runtime");
          return;
        }
        if (raw.includes("[bootstrap] creating runtime venv at")) {
          setBootstrapProgress(Math.max(bootstrapState.progress, 20), "Creating runtime virtual environment");
          const pathText = parseBootstrapPath(raw, "[bootstrap] creating runtime venv at");
          setBootstrapPath(pathText);
          return;
        }
        if (raw.includes("[bootstrap] hydrating runtime packages from")) {
          setBootstrapProgress(Math.max(bootstrapState.progress, 50), "Hydrating runtime packages");
          const pathText = parseBootstrapPath(raw, "[bootstrap] hydrating runtime packages from");
          setBootstrapPath(pathText);
          return;
        }
        if (raw.includes("[bootstrap] syncing mimolo package source from")) {
          setBootstrapProgress(Math.max(bootstrapState.progress, 68), "Syncing MiMoLo package source");
          const pathText = parseBootstrapPath(raw, "[bootstrap] syncing mimolo package source from");
          setBootstrapPath(pathText);
          return;
        }
        if (raw.includes("[bootstrap] seeded runtime config:")) {
          setBootstrapProgress(Math.max(bootstrapState.progress, 85), "Seeding runtime config");
          const pathText = parseBootstrapPath(raw, "[bootstrap] seeded runtime config:");
          setBootstrapPath(pathText);
          return;
        }
        if (raw.includes("[bootstrap] runtime ready:")) {
          setBootstrapProgress(100, "Runtime ready");
          const pathText = parseBootstrapPath(raw, "[bootstrap] runtime ready:");
          setBootstrapPath(pathText);
          setBootstrapDone();
          return;
        }
        if (raw.includes("[bootstrap] runtime config:")) {
          const pathText = parseBootstrapPath(raw, "[bootstrap] runtime config:");
          setBootstrapPath(pathText);
          return;
        }
        if (
          raw.includes("runtime_prepare_failed") ||
          raw.includes("runtime_prepare_missing_python") ||
          raw.includes("runtime hydration failed") ||
          raw.includes("[ops] start failed:")
        ) {
          setBootstrapFailed(raw);
        }
      }

      setBootstrapProgress(1, "Waiting for runtime bootstrap");
      appendBootstrapLine("[bootstrap] waiting for runtime bootstrap events");

      function setOpsConnectedState(connected) {
        opsConnected = connected === true;
        if (addAgentBtn) {
          addAgentBtn.disabled = !opsConnected;
        }
        if (monitorSettingsBtn) {
          monitorSettingsBtn.disabled = !opsConnected;
        }
        if (installPluginBtn) {
          installPluginBtn.disabled = !opsConnected;
        }
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
        setOpsConnectedState(opsState === "connected");
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

      function updateCardControlInteractivity(card, state) {
        const cardState = typeof state === "string" ? state : "inactive";
        const startBtn = card.querySelector('button[data-action="start_agent"]');
        const stopBtn = card.querySelector('button[data-action="stop_agent"]');
        const restartBtn = card.querySelector('button[data-action="restart_agent"]');
        const widgetRefresh = card.querySelector(".js-widget-refresh");
        const widgetToggle = card.querySelector(".js-widget-toggle");
        const dupBtn = card.querySelector(".js-dup");
        const delBtn = card.querySelector(".js-del");
        const cfgBtn = card.querySelector(".js-cfg");

        if (!opsConnected) {
          for (const btn of [
            startBtn,
            stopBtn,
            restartBtn,
            widgetRefresh,
            widgetToggle,
            dupBtn,
            delBtn,
            cfgBtn,
          ]) {
            if (btn) {
              btn.disabled = true;
            }
          }
          return;
        }

        if (startBtn) {
          startBtn.disabled = cardState === "running" || cardState === "shutting-down";
        }
        if (stopBtn) {
          stopBtn.disabled = cardState !== "running";
        }
        if (restartBtn) {
          restartBtn.disabled = cardState !== "running";
        }
        if (widgetRefresh) {
          widgetRefresh.disabled = cardState !== "running";
        }
        if (widgetToggle) {
          widgetToggle.disabled = cardState !== "running";
        }
        if (dupBtn) {
          dupBtn.disabled = false;
        }
        if (delBtn) {
          delBtn.disabled = false;
        }
        if (cfgBtn) {
          cfgBtn.disabled = false;
        }
      }

      function applyOpsDisconnectedCardState() {
        if (opsConnected) {
          return;
        }
        for (const [label, card] of cards.entries()) {
          const life = card.querySelector(".js-life");
          const stateText = card.querySelector(".js-state-text");
          const detail = card.querySelector(".js-detail");
          const bgLight = card.querySelector(".js-bg");
          if (life) {
            applyLifeClass(life, "inactive");
          }
          if (stateText) {
            stateText.textContent = "inactive";
          }
          if (detail) {
            detail.textContent = "operations unavailable";
          }
          setBgLightState(bgLight, "neutral");
          updateCardControlInteractivity(card, "inactive");
          widgetNextAutoRefreshAt.delete(label);
        }
      }

      async function runOpsControl(action) {
        if (!ipcRenderer) {
          append("[ops] control failed: ipc renderer unavailable");
          return;
        }
        // Manual operator intent should bypass passive reconnect backoff.
        void ipcRenderer
          .invoke("mml:reset-reconnect-backoff")
          .catch((error) => {
            const detail = error instanceof Error ? error.message : String(error);
            append("[ops] warning: unable to reset reconnect backoff: " + detail);
          });
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
`;
}
