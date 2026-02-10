export const UI_STYLE_CSS = `
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
      .top-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 3px;
      }
      .ops-global {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .ops-btn {
        background: #253047;
        color: var(--text);
        border: 1px solid #33405a;
        border-radius: 6px;
        font-family: inherit;
        font-size: 10px;
        padding: 4px 7px;
        cursor: pointer;
      }
      .ops-btn:hover {
        background: #2d3b55;
      }
      .ops-btn:disabled {
        cursor: default;
        opacity: 0.65;
      }
      .ops-process-state {
        font-size: 11px;
        color: var(--muted);
      }
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
      .controls-actions {
        display: flex;
        align-items: center;
        gap: 6px;
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
      .dev-warning {
        color: #d4b25c;
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
      .install-btn {
        background: #29422f;
        color: var(--text);
        border: 1px solid #3a6643;
        border-radius: 6px;
        font-family: inherit;
        font-size: 11px;
        padding: 5px 8px;
        cursor: pointer;
      }
      .install-btn:hover { background: #35533c; }
      .cards {
        padding: 10px;
        overflow-y: auto;
        min-height: 0;
      }
      .drop-hint {
        position: fixed;
        inset: 0;
        z-index: 2100;
        background: rgba(8, 11, 16, 0.72);
        border: 2px dashed #4d6f56;
        color: #b5dfc1;
        font-size: 14px;
        font-weight: 700;
        display: flex;
        align-items: center;
        justify-content: center;
        letter-spacing: 0.03em;
      }
      .toast-host {
        position: fixed;
        right: 12px;
        bottom: 12px;
        z-index: 2200;
        display: grid;
        gap: 8px;
        pointer-events: none;
      }
      .toast {
        border: 1px solid #33405a;
        border-radius: 8px;
        background: rgba(16, 22, 32, 0.95);
        color: var(--text);
        font-size: 11px;
        line-height: 1.3;
        padding: 8px 10px;
        min-width: 240px;
        max-width: 420px;
      }
      .toast-ok {
        border-color: #3d7a50;
      }
      .toast-warn {
        border-color: #8f7a33;
      }
      .toast-err {
        border-color: #8e4040;
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
      .light-bg-online {
        background: var(--neutral);
        box-shadow: inset 0 0 0 1px rgba(47, 207, 112, 0.9), 0 0 6px rgba(47, 207, 112, 0.35);
      }
      .light-bg-offline {
        background: var(--error);
        box-shadow: 0 0 8px rgba(217, 76, 76, 0.65);
      }
      .light-small {
        width: 7px;
        height: 7px;
      }
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
      .widget-head {
        margin-top: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      .widget-controls {
        display: flex;
        gap: 6px;
      }
      .mini-btn {
        background: #222d42;
        color: var(--text);
        border: 1px solid #33405a;
        border-radius: 6px;
        font-family: inherit;
        font-size: 10px;
        padding: 4px 7px;
        cursor: pointer;
      }
      .mini-btn:hover {
        background: #2b3a55;
      }
      .widget-canvas {
        margin-top: 8px;
        border: 1px solid #31415b;
        border-radius: 6px;
        background: #101722;
        min-height: 72px;
        max-height: 130px;
        overflow: auto;
        padding: 8px;
        font-size: 11px;
        color: #b8c3d6;
        line-height: 1.35;
      }
      .screen-widget-root {
        display: grid;
        gap: 6px;
      }
      .screen-widget-image {
        width: 100%;
        max-height: 180px;
        object-fit: contain;
        border-radius: 4px;
        background: #0c1018;
      }
      .screen-widget-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        font-size: 10px;
        color: #8f9db2;
      }
      .screen-widget-file {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .screen-widget-time {
        white-space: nowrap;
      }
      .widget-muted {
        color: #7f8ca0;
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
`;
