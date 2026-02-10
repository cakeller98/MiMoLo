export function buildModalsSection(toastDurationMs: number): string {
  return `
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
