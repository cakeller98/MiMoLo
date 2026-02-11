import type {
  ControlCommandPayload,
  IpcResponsePayload,
  IpcTrafficClass,
} from "./types.js";
import { coerceBoolean, coerceNonEmptyString } from "./control_proto_utils.js";

type SendIpcCommandFn = (
  cmd: string,
  extraPayload?: Record<string, unknown>,
  trafficLabel?: string,
  trafficClass?: IpcTrafficClass,
) => Promise<IpcResponsePayload>;

type RefreshAgentInstancesFn = () => Promise<void>;

export async function runAgentCommandWrapper(
  payload: ControlCommandPayload,
  sendIpcCommand: SendIpcCommandFn,
  refreshAgentInstances: RefreshAgentInstancesFn,
): Promise<IpcResponsePayload> {
  const extra: Record<string, unknown> = {};
  if (payload.label) {
    extra.label = payload.label;
  }
  if (payload.template_id) {
    extra.template_id = payload.template_id;
  }
  if (payload.requested_label) {
    extra.requested_label = payload.requested_label;
  }
  if (payload.updates) {
    extra.updates = payload.updates;
  }
  const trafficLabel = payload.label;
  const response = await sendIpcCommand(payload.action, extra, trafficLabel);
  await refreshAgentInstances();
  return response;
}

export async function getWidgetManifestWrapper(
  payload: Record<string, unknown>,
  sendIpcCommand: SendIpcCommandFn,
): Promise<IpcResponsePayload> {
  const pluginId = coerceNonEmptyString(payload.plugin_id);
  const instanceId = coerceNonEmptyString(payload.instance_id);
  if (!pluginId || !instanceId) {
    return {
      ok: false,
      error: !pluginId ? "missing_plugin_id" : "missing_instance_id",
    };
  }
  const isManual = coerceBoolean(payload.manual);
  const trafficClass: IpcTrafficClass = isManual ? "interactive" : "background";
  return sendIpcCommand(
    "get_widget_manifest",
    {
      plugin_id: pluginId,
      instance_id: instanceId,
    },
    instanceId,
    trafficClass,
  );
}

export async function requestWidgetRenderWrapper(
  payload: Record<string, unknown>,
  sendIpcCommand: SendIpcCommandFn,
): Promise<IpcResponsePayload> {
  const pluginId = coerceNonEmptyString(payload.plugin_id);
  const instanceId = coerceNonEmptyString(payload.instance_id);
  if (!pluginId || !instanceId) {
    return {
      ok: false,
      error: !pluginId ? "missing_plugin_id" : "missing_instance_id",
    };
  }

  const requestId = coerceNonEmptyString(payload.request_id);
  const mode = coerceNonEmptyString(payload.mode) || "html_fragment_v1";
  const isManual = coerceBoolean(payload.manual);
  const canvasRaw = payload.canvas;
  const canvas =
    canvasRaw && typeof canvasRaw === "object"
      ? (canvasRaw as Record<string, unknown>)
      : {};
  const trafficClass: IpcTrafficClass = isManual ? "interactive" : "background";
  return sendIpcCommand(
    "request_widget_render",
    {
      plugin_id: pluginId,
      instance_id: instanceId,
      request_id: requestId || `${instanceId}-${Date.now()}`,
      mode,
      canvas,
    },
    instanceId,
    trafficClass,
  );
}

export async function dispatchWidgetActionWrapper(
  payload: Record<string, unknown>,
  sendIpcCommand: SendIpcCommandFn,
): Promise<IpcResponsePayload> {
  const pluginId = coerceNonEmptyString(payload.plugin_id);
  const instanceId = coerceNonEmptyString(payload.instance_id);
  if (!pluginId || !instanceId) {
    return {
      ok: false,
      error: !pluginId ? "missing_plugin_id" : "missing_instance_id",
    };
  }

  const action = coerceNonEmptyString(payload.action) || "refresh";
  const isManual = coerceBoolean(payload.manual);
  const trafficClass: IpcTrafficClass = isManual ? "interactive" : "background";
  const actionPayloadRaw = payload.payload;
  const actionPayload =
    actionPayloadRaw && typeof actionPayloadRaw === "object"
      ? (actionPayloadRaw as Record<string, unknown>)
      : {};

  return sendIpcCommand(
    "dispatch_widget_action",
    {
      plugin_id: pluginId,
      instance_id: instanceId,
      action,
      payload: actionPayload,
    },
    instanceId,
    trafficClass,
  );
}

export async function inspectPluginArchiveWrapper(
  payload: Record<string, unknown>,
  sendIpcCommand: SendIpcCommandFn,
  controlDevMode: boolean,
): Promise<IpcResponsePayload> {
  if (!controlDevMode) {
    return {
      ok: false,
      error: "dev_mode_required",
      data: {
        detail:
          "plugin zip inspection/install is disabled outside developer mode",
      },
    };
  }
  const zipPath = coerceNonEmptyString(payload.zip_path);
  if (!zipPath) {
    return {
      ok: false,
      error: "missing_zip_path",
    };
  }
  return sendIpcCommand("inspect_plugin_archive", {
    zip_path: zipPath,
  });
}

export async function installPluginArchiveWrapper(
  payload: Record<string, unknown>,
  sendIpcCommand: SendIpcCommandFn,
  controlDevMode: boolean,
): Promise<IpcResponsePayload> {
  if (!controlDevMode) {
    return {
      ok: false,
      error: "dev_mode_required",
      data: {
        detail:
          "plugin zip inspection/install is disabled outside developer mode",
      },
    };
  }
  const zipPath = coerceNonEmptyString(payload.zip_path);
  if (!zipPath) {
    return {
      ok: false,
      error: "missing_zip_path",
    };
  }

  const actionRaw = coerceNonEmptyString(payload.action);
  const cmd = actionRaw === "upgrade" ? "upgrade_plugin" : "install_plugin";
  const pluginClassRaw = coerceNonEmptyString(payload.plugin_class) || "agents";
  const pluginClass = pluginClassRaw.toLowerCase();
  if (!pluginClass) {
    return {
      ok: false,
      error: "invalid_plugin_class",
    };
  }
  if (
    pluginClass !== "agents" &&
    pluginClass !== "reporters" &&
    pluginClass !== "widgets"
  ) {
    return {
      ok: false,
      error: "invalid_plugin_class",
    };
  }

  return sendIpcCommand(cmd, {
    zip_path: zipPath,
    plugin_class: pluginClass,
  });
}
