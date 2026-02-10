export function buildUiShellHtml(controlDevMode: boolean): string {
  return `
    <div class="shell">
      <div class="top">
        <div class="top-head">
          <div class="row"><strong>MiMoLo Control Proto</strong> - operations stream viewer</div>
          <div class="ops-global">
            <button class="ops-btn" id="opsStartBtn" title="Start Operations">Start Ops</button>
            <button class="ops-btn" id="opsStopBtn" title="Stop Operations">Stop Ops</button>
            <button class="ops-btn" id="opsRestartBtn" title="Restart Operations">Restart Ops</button>
            <div class="light light-inactive light-small" id="globalBgActivity" title="Background polling activity"></div>
            <div class="signal-text">bg</div>
            <div class="light light-inactive" id="globalTxLight" title="Global tx"></div>
            <div class="signal-text">tx</div>
            <div class="light light-inactive" id="globalRxLight" title="Global rx"></div>
            <div class="signal-text">rx</div>
          </div>
        </div>
        <div class="row ops-process-state">Ops process: <span id="opsProcessState">stopped - not_managed</span></div>
        <div class="row">IPC: <span id="ipcPath"></span></div>
        <div class="row">Ops log: <span id="opsLogPath"></span></div>
        <div class="row">Monitor: <span id="monitorSettings">poll_tick_s=?, cooldown_seconds=?</span></div>
        <div class="row">Status: <span id="status">starting</span></div>
        ${
          controlDevMode
            ? `<div class="row dev-warning"><strong>Dev mode:</strong> unsigned zip plugin sideload is enabled (signature allowlist is not implemented yet).</div>`
            : ""
        }
      </div>
      <div class="main">
        <div class="log-pane"><pre id="log"></pre></div>
        <div class="controls">
          <div class="controls-head">
            <div class="controls-row">
              <div class="controls-title">Agent Control Panel</div>
              <div class="controls-actions">
                <button class="add-btn" id="monitorSettingsBtn" title="Edit global monitor settings">Monitor</button>
                ${
                  controlDevMode
                    ? `<button class="install-btn" id="installPluginBtn" title="Install or upgrade plugin zip (developer mode only)">Install (dev)</button>`
                    : ""
                }
                <button class="add-btn" id="addAgentBtn" title="Add agent instance">+ Add</button>
              </div>
            </div>
            <div class="controls-sub">Per-instance controls and configuration from registered templates</div>
          </div>
          <div class="cards" id="cards"></div>
        </div>
      </div>
    </div>
    ${
      controlDevMode
        ? `<div id="dropHint" class="drop-hint" hidden>Drop plugin zip to install (developer mode)</div>`
        : ""
    }
    <div id="modalHost"></div>
    <div id="toastHost" class="toast-host"></div>
`;
}
