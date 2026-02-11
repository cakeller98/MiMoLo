export function buildIndicatorsAndWidgetsSection(
  indicatorFadeStepMs: number,
  widgetAutoTickMs: number,
  widgetAutoRefreshDefaultMs: number,
): string {
  return `
      function applyLifeClass(light, state) {
        light.classList.remove("light-running", "light-shutting-down", "light-inactive", "light-error");
        light.classList.add("light-" + state);
      }

      const INDICATOR_FADE_LEVELS = [0.9, 0.6, 0.3, 0.1];
      const INDICATOR_FADE_STEP_MS = ${indicatorFadeStepMs};
      const WIDGET_AUTO_TICK_MS = ${widgetAutoTickMs};
      const DEFAULT_WIDGET_AUTO_REFRESH_MS = ${widgetAutoRefreshDefaultMs};
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
        if (!opsConnected) {
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

          let dispatchWarning = "";
          if (manualRequest) {
            const dispatchResponse = await ipcRenderer.invoke("mml:dispatch-widget-action", {
              ...identity,
              action: "refresh",
              manual: true,
            });
            if (dispatchResponse && dispatchResponse.ok === false) {
              dispatchWarning = dispatchResponse.error
                ? String(dispatchResponse.error)
                : "manual_refresh_dispatch_failed";
            } else {
              const dispatchData = dispatchResponse && dispatchResponse.data
                ? dispatchResponse.data
                : null;
              if (dispatchData && dispatchData.accepted === false) {
                dispatchWarning = dispatchData.status
                  ? String(dispatchData.status)
                  : "manual_refresh_not_accepted";
              }
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
          const statusText = dispatchWarning
            ? warningText + ", dispatch=" + dispatchWarning
            : warningText;
          renderStatusEl.textContent = "render: " + statusText;

          if (render && typeof render.html === "string" && render.html.trim().length > 0) {
            renderWidgetHtml(canvasEl, render.html);
          } else {
            canvasEl.textContent = "widget canvas waiting: " + statusText;
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
        if (!opsConnected) {
          return;
        }
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
`;
}
