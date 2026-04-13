export function buildModalsSection(toastDurationMs: number): string {
  return `
      let quitProgressTracker = null;

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
        }, ${toastDurationMs});
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

      function renderQuitProgressModal(payload) {
        if (!modalHost) {
          return;
        }
        if (!payload || payload.visible !== true) {
          quitProgressTracker = null;
          modalHost.innerHTML = "";
          return;
        }

        const isShutdownFlow = payload.title === "Shutting Down Operations";
        if (isShutdownFlow) {
          const closeStep = Array.isArray(payload.steps)
            ? payload.steps.find((step) => step && step.key === "close")
            : null;
          const opsStep = Array.isArray(payload.steps)
            ? payload.steps.find((step) => step && step.key === "ops")
            : null;
          const labels = Array.from(instancesByLabel.entries())
            .filter((entry) => entry[1] && (entry[1].state === "running" || entry[1].state === "shutting-down"))
            .map((entry) => entry[0])
            .sort();
          if (!quitProgressTracker || quitProgressTracker.mode !== "shutdown") {
            const trackedSteps = [];
            trackedSteps.push({
              key: "ops",
              label: "Operations shutdown requested",
              state: opsStep && opsStep.state ? opsStep.state : "active",
            });
            for (const label of labels) {
              trackedSteps.push({
                key: "agent:" + label,
                label: label,
                state: "pending",
              });
            }
            trackedSteps.push({
              key: "close",
              label: "Close Control",
              state: closeStep && closeStep.state ? closeStep.state : "pending",
            });
            quitProgressTracker = {
              mode: "shutdown",
              title: payload.title,
              detail: payload.detail || "",
              steps: trackedSteps,
            };
          } else {
            quitProgressTracker.title = payload.title;
            quitProgressTracker.detail = payload.detail || "";
            for (const step of quitProgressTracker.steps) {
              if (step.key === "ops" && opsStep && opsStep.state) {
                step.state = opsStep.state;
              }
              if (step.key === "close" && closeStep && closeStep.state) {
                step.state = closeStep.state;
              }
            }
          }
          payload = {
            ...payload,
            steps: quitProgressTracker.steps,
            detail: quitProgressTracker.detail,
          };
        } else {
          quitProgressTracker = null;
        }

        modalHost.innerHTML = "";
        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        const card = document.createElement("div");
        card.className = "modal-card quit-progress-card";

        const title = document.createElement("div");
        title.className = "modal-title";
        title.textContent = payload.title || "Shutting down";

        card.appendChild(title);

        if (typeof payload.detail === "string" && payload.detail.trim().length > 0) {
          const detail = document.createElement("div");
          detail.className = "quit-progress-detail";
          detail.textContent = payload.detail;
          card.appendChild(detail);
        }

        const steps = Array.isArray(payload.steps) ? payload.steps : [];
        const completedCount = steps.filter((step) => step && step.state === "done").length;
        const hasActiveStep = steps.some((step) => step && step.state === "active");
        const totalCount = Math.max(steps.length, 1);
        const progressTrack = document.createElement("div");
        progressTrack.className = "quit-progress-track";
        const progressFill = document.createElement("div");
        progressFill.className =
          "quit-progress-fill" + (hasActiveStep ? " quit-progress-fill-active" : "");
        progressFill.style.width = String(Math.max(8, Math.min(100, (completedCount / totalCount) * 100))) + "%";
        progressTrack.appendChild(progressFill);
        card.appendChild(progressTrack);

        const list = document.createElement("div");
        list.className = "quit-progress-list";
        for (const step of steps) {
          const row = document.createElement("div");
          row.className = "quit-progress-row quit-progress-row-" + String(step && step.state ? step.state : "pending");

          const dot = document.createElement("div");
          dot.className = "quit-progress-dot quit-progress-dot-" + String(step && step.state ? step.state : "pending");

          const label = document.createElement("div");
          label.className = "quit-progress-label";
          const state = step && step.state ? String(step.state) : "pending";
          const suffix = state === "done" ? " [done]" : (state === "error" ? " [failed]" : "");
          label.textContent = String(step && step.label ? step.label : "step") + suffix;

          row.appendChild(dot);
          row.appendChild(label);
          list.appendChild(row);
        }
        card.appendChild(list);
        overlay.appendChild(card);
        modalHost.appendChild(overlay);
      }

      function updateQuitProgressFromLine(line) {
        if (!quitProgressTracker || quitProgressTracker.mode !== "shutdown") {
          return;
        }
        const raw = typeof line === "string" ? line.trim() : "";
        if (!raw) {
          return;
        }

        function findStep(agentLabel) {
          return quitProgressTracker.steps.find((step) => step.key === "agent:" + agentLabel) || null;
        }

        let match = raw.match(/^Sent shutdown SEQUENCE to (.+)$/);
        if (match) {
          const step = findStep(match[1]);
          if (step && step.state !== "done" && step.state !== "error") {
            step.state = "active";
          }
          renderQuitProgressModal({
            visible: true,
            title: quitProgressTracker.title,
            detail: quitProgressTracker.detail,
            steps: quitProgressTracker.steps,
          });
          return;
        }

        match = raw.match(/^Agent (.+) ACK\\(stop\\)$/);
        if (match) {
          const step = findStep(match[1]);
          if (step && step.state !== "done" && step.state !== "error") {
            step.state = "active";
            step.label = match[1] + " - stop acknowledged";
          }
          renderQuitProgressModal({
            visible: true,
            title: quitProgressTracker.title,
            detail: quitProgressTracker.detail,
            steps: quitProgressTracker.steps,
          });
          return;
        }

        match = raw.match(/^\\[.*\\] Shutting down \\(label=(.+?), /);
        if (match) {
          const agentLabel = match[1];
          const step = findStep(agentLabel);
          if (step && step.state !== "error") {
            step.state = "done";
            step.label = agentLabel;
          }
          renderQuitProgressModal({
            visible: true,
            title: quitProgressTracker.title,
            detail: quitProgressTracker.detail,
            steps: quitProgressTracker.steps,
          });
          return;
        }

        match = raw.match(/^Agent (.+) did not ACK STOP \\(timeout\\)$/);
        if (!match) match = raw.match(/^Agent (.+) did not send summary after FLUSH \\(timeout\\)$/);
        if (!match) match = raw.match(/^Agent (.+) did not ACK FLUSH \\(timeout\\)$/);
        if (!match) match = raw.match(/^Agent (.+) did not ACK SHUTDOWN \\(timeout\\)$/);
        if (match) {
          const agentLabel = match[1];
          const step = findStep(agentLabel);
          if (step) {
            step.state = "error";
            step.label = agentLabel + " - timeout";
          }
          renderQuitProgressModal({
            visible: true,
            title: quitProgressTracker.title,
            detail: quitProgressTracker.detail,
            steps: quitProgressTracker.steps,
          });
          return;
        }

        if (raw === "MiMoLo stopped.") {
          for (const step of quitProgressTracker.steps) {
            if (step.key === "ops") {
              step.state = "done";
            } else if (step.key.startsWith("agent:") && step.state !== "error") {
              step.state = "done";
              step.label = step.key.slice("agent:".length);
            }
          }
          renderQuitProgressModal({
            visible: true,
            title: quitProgressTracker.title,
            detail: quitProgressTracker.detail,
            steps: quitProgressTracker.steps,
          });
        }
      }

      function renderQuitPromptModal(payload) {
        if (!payload || payload.visible !== true) {
          return;
        }
        void showModal((card, close) => {
          const title = document.createElement("div");
          title.className = "modal-title";
          title.textContent = payload.title || "Quit";

          const body = document.createElement("div");
          body.className = "modal-body";

          const message = document.createElement("div");
          message.className = "quit-progress-detail";
          message.textContent = payload.message || "";
          body.appendChild(message);

          if (typeof payload.detail === "string" && payload.detail.trim().length > 0) {
            const detail = document.createElement("div");
            detail.className = "quit-progress-detail";
            detail.textContent = payload.detail;
            body.appendChild(detail);
          }

          const actions = document.createElement("div");
          actions.className = "modal-actions";

          const shutdownBtn = document.createElement("button");
          shutdownBtn.textContent = "Shutdown Operations + Agents";
          shutdownBtn.addEventListener("click", () => {
            close(0);
          });

          const leaveBtn = document.createElement("button");
          leaveBtn.textContent = "Leave Operations Running";
          leaveBtn.addEventListener("click", () => {
            close(1);
          });

          const cancelBtn = document.createElement("button");
          cancelBtn.textContent = "Cancel";
          cancelBtn.addEventListener("click", () => {
            close(2);
          });

          actions.appendChild(cancelBtn);
          actions.appendChild(leaveBtn);
          actions.appendChild(shutdownBtn);

          card.appendChild(title);
          card.appendChild(body);
          card.appendChild(actions);
          shutdownBtn.focus();
        }).then((response) => {
          if (!ipcRenderer) {
            return;
          }
          return ipcRenderer.invoke("mml:resolve-quit-prompt", {
            response: typeof response === "number" ? response : 2,
          });
        });
      }

      function renderQuitErrorModal(payload) {
        if (!payload || payload.visible !== true) {
          return;
        }
        void showModal((card, close) => {
          const title = document.createElement("div");
          title.className = "modal-title";
          title.textContent = payload.title || "Error";

          const body = document.createElement("div");
          body.className = "modal-body";

          const message = document.createElement("div");
          message.className = "quit-progress-detail";
          message.textContent = payload.message || "";
          body.appendChild(message);

          const detail = document.createElement("div");
          detail.className = "quit-progress-detail";
          detail.textContent = payload.detail || "";
          body.appendChild(detail);

          const actions = document.createElement("div");
          actions.className = "modal-actions";
          const okBtn = document.createElement("button");
          okBtn.textContent = "OK";
          okBtn.addEventListener("click", () => {
            close(true);
          });
          actions.appendChild(okBtn);

          card.appendChild(title);
          card.appendChild(body);
          card.appendChild(actions);
          okBtn.focus();
        }).then(() => {
          if (!ipcRenderer) {
            return;
          }
          return ipcRenderer.invoke("mml:ack-quit-error");
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
`;
}
