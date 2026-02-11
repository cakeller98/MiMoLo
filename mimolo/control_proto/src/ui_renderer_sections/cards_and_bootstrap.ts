export function buildCardsAndBootstrapSection(): string {
  return `
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
          updateCardControlInteractivity(card, state);
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
        applyOpsDisconnectedCardState();
      }

      async function refreshInitialState() {
        if (!ipcRenderer) {
          setStatus("disconnected - ipc_renderer_unavailable");
          return;
        }
        try {
          await prepareRuntimeIfNeeded();
          const state = await ipcRenderer.invoke("mml:initial-state");
          ipcPathEl.textContent = state.ipcPath || "(unset)";
          opsLogPathEl.textContent = state.opsLogPath || "(unset)";
          setStatus(state.status.state + " - " + state.status.detail);
          applyGlobalBgState(state.status.state, state.status.detail);
          renderOpsProcessState(state.opsControl || {});
          renderMonitorSettings(state.monitorSettings || null);
          renderInstances(state.instances || {});
          const opsState = state && state.opsControl && typeof state.opsControl.state === "string"
            ? state.opsControl.state
            : "";
          const linkState = state && state.status && typeof state.status.state === "string"
            ? state.status.state
            : "";
          if (
            !bootstrapAutoStartAttempted &&
            linkState !== "connected" &&
            opsState === "stopped"
          ) {
            bootstrapAutoStartAttempted = true;
            append("[ops] auto-start after runtime prepare");
            await runOpsControl("start");
          }
        } catch (err) {
          const detail = err instanceof Error ? err.message : "initial_state_failed";
          setStatus("disconnected - " + detail);
        }
      }

      let runtimePrepareInFlight = false;
      async function prepareRuntimeIfNeeded() {
        if (!ipcRenderer || runtimePrepareInFlight || bootstrapState.failed || bootstrapState.done) {
          return;
        }
        runtimePrepareInFlight = true;
        try {
          const response = await ipcRenderer.invoke("mml:prepare-runtime");
          if (!response || !response.ok) {
            const detail = response && response.error ? String(response.error) : "runtime_prepare_failed";
            setBootstrapFailed("[bootstrap] " + detail);
            append("[bootstrap] prepare failed: " + detail);
            return;
          }
          const portablePython = response && response.portablePython
            ? String(response.portablePython)
            : "";
          const runtimeConfigPath = response && response.runtimeConfigPath
            ? String(response.runtimeConfigPath)
            : "";
          if (portablePython.length > 0) {
            updateBootstrapFromLine("[bootstrap] runtime ready: " + portablePython);
          }
          if (runtimeConfigPath.length > 0) {
            updateBootstrapFromLine("[bootstrap] runtime config: " + runtimeConfigPath);
          }
          if (!bootstrapState.done) {
            setBootstrapProgress(100, "Runtime ready");
            setBootstrapDone();
          }
        } catch (err) {
          const detail = err instanceof Error ? err.message : "runtime_prepare_failed";
          setBootstrapFailed("[bootstrap] " + detail);
          append("[bootstrap] prepare failed: " + detail);
        } finally {
          runtimePrepareInFlight = false;
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
          refreshWidgetsAuto();
        }, WIDGET_AUTO_TICK_MS);
        ipcRenderer.on("ops:status", (_event, payload) => {
          setStatus(payload.state + " - " + payload.detail);
          applyGlobalBgState(payload.state, payload.detail);
          if (payload.state !== "connected") {
            applyOpsDisconnectedCardState();
          }
        });

        ipcRenderer.on("ops:line", (_event, line) => {
          append(line);
        });

        ipcRenderer.on("ops:bootstrap-line", (_event, line) => {
          updateBootstrapFromLine(String(line));
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
`;
}
