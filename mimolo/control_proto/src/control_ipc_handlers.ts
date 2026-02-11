import type { BrowserWindow, IpcMain } from "electron";
import type {
  AgentInstanceSnapshot,
  AgentTemplateSnapshot,
  ControlCommandPayload,
  ControlTimingSettings,
  IpcResponsePayload,
  MonitorSettingsSnapshot,
  OperationsControlRequest,
  OperationsControlSnapshot,
  OpsStatusPayload,
} from "./types.js";

interface OperationsControlResult {
  error?: string;
  ok: boolean;
  state: OperationsControlSnapshot;
}

interface RegisterIpcHandlersDependencies {
  controlDevMode: boolean;
  controlOperations: (request: OperationsControlRequest) => Promise<OperationsControlResult>;
  prepareRuntime: () => Promise<{ error?: string; ok: boolean; portablePython?: string; runtimeConfigPath?: string }>;
  dialog: typeof import("electron").dialog;
  getControlSettings: () => ControlTimingSettings;
  getInstances: () => Record<string, AgentInstanceSnapshot>;
  getMainWindow: () => BrowserWindow | null;
  getMonitorSettings: () => MonitorSettingsSnapshot;
  getOpsControlState: () => OperationsControlSnapshot;
  getStatus: () => OpsStatusPayload;
  dispatchWidgetAction: (payload: Record<string, unknown>) => Promise<IpcResponsePayload>;
  getWidgetManifest: (payload: Record<string, unknown>) => Promise<IpcResponsePayload>;
  inspectPluginArchive: (payload: Record<string, unknown>) => Promise<IpcResponsePayload>;
  installPluginArchive: (payload: Record<string, unknown>) => Promise<IpcResponsePayload>;
  ipcMain: IpcMain;
  ipcPath: string;
  opsLogPath: string;
  refreshMonitorSettings: () => Promise<void>;
  refreshTemplatesCached: (
    forceRefresh?: boolean,
  ) => Promise<Record<string, AgentTemplateSnapshot>>;
  requestWidgetRender: (payload: Record<string, unknown>) => Promise<IpcResponsePayload>;
  resetReconnectBackoff: () => void;
  runAgentCommand: (payload: ControlCommandPayload) => Promise<IpcResponsePayload>;
  updateMonitorSettings: (updates: Record<string, unknown>) => Promise<IpcResponsePayload>;
}

export function registerIpcHandlers(
  deps: RegisterIpcHandlersDependencies,
): void {
  deps.ipcMain.handle("mml:initial-state", () => {
    return {
      ipcPath: deps.ipcPath,
      opsLogPath: deps.opsLogPath,
      status: deps.getStatus(),
      opsControl: deps.getOpsControlState(),
      monitorSettings: deps.getMonitorSettings(),
      controlSettings: deps.getControlSettings(),
      instances: deps.getInstances(),
    };
  });

  deps.ipcMain.handle("mml:reset-reconnect-backoff", () => {
    deps.resetReconnectBackoff();
    return { ok: true };
  });

  deps.ipcMain.handle("mml:ops-control", async (_event, payload: unknown) => {
    if (!payload || typeof payload !== "object") {
      return {
        ok: false,
        error: "invalid_ops_payload",
        state: deps.getOpsControlState(),
      };
    }
    const raw = payload as Record<string, unknown>;
    const actionRaw = raw.action;
    if (
      actionRaw !== "start" &&
      actionRaw !== "stop" &&
      actionRaw !== "restart" &&
      actionRaw !== "status"
    ) {
      return {
        ok: false,
        error: "invalid_ops_action",
        state: deps.getOpsControlState(),
      };
    }
    return deps.controlOperations({
      action: actionRaw,
    });
  });

  deps.ipcMain.handle("mml:prepare-runtime", async () => {
    return deps.prepareRuntime();
  });

  deps.ipcMain.handle("mml:list-agent-templates", async () => {
    try {
      const templates = await deps.refreshTemplatesCached(false);
      return {
        ok: true,
        templates,
      };
    } catch (err) {
      const detail = err instanceof Error ? err.message : "template_query_failed";
      return {
        ok: false,
        error: detail,
        templates: {},
      };
    }
  });

  deps.ipcMain.handle("mml:get-monitor-settings", async () => {
    try {
      await deps.refreshMonitorSettings();
      return {
        ok: true,
        monitor: deps.getMonitorSettings(),
      };
    } catch (err) {
      const detail = err instanceof Error ? err.message : "monitor_query_failed";
      return {
        ok: false,
        error: detail,
      };
    }
  });

  deps.ipcMain.handle("mml:update-monitor-settings", async (_event, payload: unknown) => {
    if (!payload || typeof payload !== "object") {
      return {
        ok: false,
        error: "invalid_monitor_payload",
      };
    }
    const raw = payload as Record<string, unknown>;
    const updatesRaw = raw.updates;
    if (!updatesRaw || typeof updatesRaw !== "object") {
      return {
        ok: false,
        error: "missing_updates",
      };
    }
    try {
      return await deps.updateMonitorSettings(updatesRaw as Record<string, unknown>);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "monitor_update_failed";
      return {
        ok: false,
        error: detail,
      };
    }
  });

  deps.ipcMain.handle("mml:get-widget-manifest", async (_event, payload: unknown) => {
    if (!payload || typeof payload !== "object") {
      return {
        ok: false,
        error: "invalid_widget_payload",
      };
    }
    try {
      return await deps.getWidgetManifest(payload as Record<string, unknown>);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "widget_manifest_failed";
      return {
        ok: false,
        error: detail,
      };
    }
  });

  deps.ipcMain.handle("mml:request-widget-render", async (_event, payload: unknown) => {
    if (!payload || typeof payload !== "object") {
      return {
        ok: false,
        error: "invalid_widget_payload",
      };
    }
    try {
      return await deps.requestWidgetRender(payload as Record<string, unknown>);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "widget_render_failed";
      return {
        ok: false,
        error: detail,
      };
    }
  });

  deps.ipcMain.handle("mml:dispatch-widget-action", async (_event, payload: unknown) => {
    if (!payload || typeof payload !== "object") {
      return {
        ok: false,
        error: "invalid_widget_payload",
      };
    }
    try {
      return await deps.dispatchWidgetAction(payload as Record<string, unknown>);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "widget_action_failed";
      return {
        ok: false,
        error: detail,
      };
    }
  });

  deps.ipcMain.handle("mml:pick-plugin-archive", async () => {
    if (!deps.controlDevMode) {
      return {
        ok: false,
        error: "dev_mode_required",
        detail: "plugin zip install is disabled outside developer mode",
      };
    }
    const mainWindow = deps.getMainWindow();
    if (!mainWindow) {
      return {
        ok: false,
        error: "window_unavailable",
      };
    }
    const result = await deps.dialog.showOpenDialog(mainWindow, {
      title: "Select MiMoLo plugin archive",
      properties: ["openFile"],
      filters: [{ name: "Zip archives", extensions: ["zip"] }],
    });
    if (result.canceled || result.filePaths.length === 0) {
      return {
        ok: true,
        zip_path: null,
      };
    }
    return {
      ok: true,
      zip_path: result.filePaths[0],
    };
  });

  deps.ipcMain.handle("mml:inspect-plugin-archive", (_event, payload: unknown) => {
    if (!payload || typeof payload !== "object") {
      return {
        ok: false,
        error: "invalid_plugin_payload",
      };
    }
    return deps.inspectPluginArchive(payload as Record<string, unknown>);
  });

  deps.ipcMain.handle("mml:install-plugin", (_event, payload: unknown) => {
    if (!payload || typeof payload !== "object") {
      return {
        ok: false,
        error: "invalid_plugin_payload",
      };
    }
    return deps.installPluginArchive(payload as Record<string, unknown>);
  });

  deps.ipcMain.handle("mml:agent-command", (_event, payload: unknown) => {
    if (!payload || typeof payload !== "object") {
      return {
        ok: false,
        error: "invalid_command_payload",
      };
    }

    const raw = payload as Record<string, unknown>;
    const actionRaw = raw.action;
    if (
      actionRaw !== "start_agent" &&
      actionRaw !== "stop_agent" &&
      actionRaw !== "restart_agent" &&
      actionRaw !== "add_agent_instance" &&
      actionRaw !== "duplicate_agent_instance" &&
      actionRaw !== "remove_agent_instance" &&
      actionRaw !== "update_agent_instance"
    ) {
      return {
        ok: false,
        error: "invalid_action",
      };
    }

    const cmd: ControlCommandPayload = {
      action: actionRaw,
    };

    const labelRaw = raw.label;
    if (typeof labelRaw === "string" && labelRaw.trim().length > 0) {
      cmd.label = labelRaw.trim();
    }
    const templateRaw = raw.template_id;
    if (typeof templateRaw === "string" && templateRaw.trim().length > 0) {
      cmd.template_id = templateRaw.trim();
    }
    const requestedLabelRaw = raw.requested_label;
    if (
      typeof requestedLabelRaw === "string" &&
      requestedLabelRaw.trim().length > 0
    ) {
      cmd.requested_label = requestedLabelRaw.trim();
    }
    const updatesRaw = raw.updates;
    if (updatesRaw && typeof updatesRaw === "object") {
      cmd.updates = updatesRaw as Record<string, unknown>;
    }

    return deps.runAgentCommand(cmd).catch((err: unknown) => {
      const detail = err instanceof Error ? err.message : "agent_command_failed";
      return {
        ok: false,
        error: detail,
      };
    });
  });
}
