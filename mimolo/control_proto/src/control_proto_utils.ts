import type {
  AgentInstanceSnapshot,
  AgentTemplateSnapshot,
  ControlTimingSettings,
  IpcResponsePayload,
  MonitorSettingsSnapshot,
  OpsStatusPayload,
} from "./types.js";

export function normalizeDisconnectedStatusDetail(detail: string): string {
  if (detail === "ipc_connect_backoff") {
    return "waiting_for_operations";
  }
  return detail;
}

export function parseIpcResponse(rawLine: string): IpcResponsePayload {
  if (rawLine.length === 0) {
    throw new Error("empty_response");
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(rawLine);
  } catch {
    throw new Error("invalid_json_response");
  }

  if (!parsed || typeof parsed !== "object") {
    throw new Error("invalid_response_shape");
  }

  const record = parsed as Record<string, unknown>;
  return {
    ok: record.ok === true,
    cmd: typeof record.cmd === "string" ? record.cmd : undefined,
    timestamp: typeof record.timestamp === "string" ? record.timestamp : undefined,
    request_id:
      typeof record.request_id === "string" ? record.request_id : undefined,
    error: typeof record.error === "string" ? record.error : undefined,
    data:
      record.data && typeof record.data === "object"
        ? (record.data as Record<string, unknown>)
        : undefined,
  };
}

export function extractAgentInstances(
  response: IpcResponsePayload,
): Record<string, AgentInstanceSnapshot> {
  const result: Record<string, AgentInstanceSnapshot> = {};
  const instancesRaw = response.data?.instances;
  if (!instancesRaw || typeof instancesRaw !== "object") {
    return result;
  }

  const map = instancesRaw as Record<string, unknown>;
  for (const [label, raw] of Object.entries(map)) {
    if (!raw || typeof raw !== "object") {
      continue;
    }
    const entry = raw as Record<string, unknown>;
    const stateRaw = entry.state;
    const detailRaw = entry.detail;
    const configRaw = entry.config;
    const templateRaw = entry.template_id;
    const state =
      stateRaw === "running" ||
      stateRaw === "shutting-down" ||
      stateRaw === "inactive" ||
      stateRaw === "error"
        ? stateRaw
        : "inactive";
    const detail = typeof detailRaw === "string" ? detailRaw : "configured";
    const config =
      configRaw && typeof configRaw === "object"
        ? (configRaw as Record<string, unknown>)
        : {};
    const template_id =
      typeof templateRaw === "string" ? templateRaw : label;
    result[label] = {
      label,
      state,
      detail,
      config,
      template_id,
    };
  }

  return result;
}

export function extractTemplates(
  response: IpcResponsePayload,
): Record<string, AgentTemplateSnapshot> {
  const result: Record<string, AgentTemplateSnapshot> = {};
  const templatesRaw = response.data?.templates;
  if (!templatesRaw || typeof templatesRaw !== "object") {
    return result;
  }

  const map = templatesRaw as Record<string, unknown>;
  for (const [templateId, raw] of Object.entries(map)) {
    if (!raw || typeof raw !== "object") {
      continue;
    }
    const entry = raw as Record<string, unknown>;
    const scriptRaw = entry.script;
    const defaultRaw = entry.default_config;
    const default_config =
      defaultRaw && typeof defaultRaw === "object"
        ? (defaultRaw as Record<string, unknown>)
        : {};
    result[templateId] = {
      template_id: templateId,
      script: typeof scriptRaw === "string" ? scriptRaw : "",
      default_config,
    };
  }

  return result;
}

export function normalizeMonitorSettings(
  raw: unknown,
  defaults: MonitorSettingsSnapshot,
): MonitorSettingsSnapshot {
  if (!raw || typeof raw !== "object") {
    return { ...defaults };
  }
  const record = raw as Record<string, unknown>;

  const cooldownRaw = record.cooldown_seconds;
  const pollTickRaw = record.poll_tick_s;
  const verbosityRaw = record.console_verbosity;

  const cooldownParsed =
    typeof cooldownRaw === "number" && Number.isFinite(cooldownRaw) && cooldownRaw > 0
      ? cooldownRaw
      : defaults.cooldown_seconds;
  const pollTickParsed =
    typeof pollTickRaw === "number" && Number.isFinite(pollTickRaw) && pollTickRaw > 0
      ? pollTickRaw
      : defaults.poll_tick_s;
  const verbosityParsed =
    verbosityRaw === "debug" ||
    verbosityRaw === "info" ||
    verbosityRaw === "warning" ||
    verbosityRaw === "error"
      ? verbosityRaw
      : defaults.console_verbosity;

  return {
    cooldown_seconds: cooldownParsed,
    poll_tick_s: pollTickParsed,
    console_verbosity: verbosityParsed,
  };
}

export function deriveStatusLoopMs(
  settings: MonitorSettingsSnapshot,
  status: OpsStatusPayload["state"],
  timing: ControlTimingSettings,
): number {
  return deriveLoopIntervalMs(
    status,
    settings.poll_tick_s,
    timing.status_poll_connected_s,
    timing.status_poll_disconnected_s,
  );
}

export function deriveInstanceLoopMs(
  settings: MonitorSettingsSnapshot,
  status: OpsStatusPayload["state"],
  timing: ControlTimingSettings,
): number {
  return deriveLoopIntervalMs(
    status,
    settings.poll_tick_s,
    timing.instance_poll_connected_s,
    timing.instance_poll_disconnected_s,
  );
}

export function deriveLogLoopMs(
  settings: MonitorSettingsSnapshot,
  status: OpsStatusPayload["state"],
  timing: ControlTimingSettings,
): number {
  return deriveLoopIntervalMs(
    status,
    settings.poll_tick_s,
    timing.log_poll_connected_s,
    timing.log_poll_disconnected_s,
  );
}

function deriveLoopIntervalMs(
  status: OpsStatusPayload["state"],
  pollTickSeconds: number,
  connectedFloorSeconds: number,
  disconnectedSeconds: number,
): number {
  if (status !== "connected") {
    return Math.max(1, Math.round(disconnectedSeconds * 1000));
  }
  return Math.max(
    Math.round(pollTickSeconds * 1000),
    Math.round(connectedFloorSeconds * 1000),
  );
}

export function coerceNonEmptyString(raw: unknown): string | null {
  if (typeof raw !== "string") {
    return null;
  }
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function coerceBoolean(raw: unknown): boolean {
  if (typeof raw === "boolean") {
    return raw;
  }
  if (typeof raw !== "string") {
    return false;
  }
  const normalized = raw.trim().toLowerCase();
  return (
    normalized === "1" ||
    normalized === "true" ||
    normalized === "yes" ||
    normalized === "on"
  );
}
