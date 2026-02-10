export function buildCommandsAndInstallSection(): string {
  return `
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
            if (refresh && refresh.error) {
              const errText = String(refresh.error);
              if (
                errText !== "ipc_connect_backoff" &&
                !errText.includes("ENOENT") &&
                !errText.includes("ipc_socket_closed")
              ) {
                append("[ui] template refresh failed: " + errText);
              }
            }
            return;
          }
          templatesById.clear();
          for (const [k, v] of Object.entries(refresh.templates)) {
            templatesById.set(k, v);
          }
        } catch (err) {
          const detail = err instanceof Error ? err.message : "template_refresh_failed";
          if (
            detail !== "ipc_connect_backoff" &&
            !detail.includes("ENOENT") &&
            !detail.includes("ipc_socket_closed")
          ) {
            append("[ui] template refresh failed: " + detail);
          }
        }
      }
`;
}
