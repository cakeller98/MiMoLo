import type { ControlTimingSettings } from "./types.js";

function coercePositiveNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed > 0) {
      return parsed;
    }
  }
  return fallback;
}

function coercePositiveInteger(value: unknown, fallback: number): number {
  const numeric = coercePositiveNumber(value, fallback);
  if (!Number.isFinite(numeric) || numeric < 1) {
    return fallback;
  }
  return Math.max(1, Math.floor(numeric));
}

export function normalizeControlTimingSettings(
  raw: unknown,
  defaults: ControlTimingSettings,
): ControlTimingSettings {
  const record = raw && typeof raw === "object"
    ? (raw as Record<string, unknown>)
    : {};
  return {
    indicator_fade_step_s: coercePositiveNumber(
      record.indicator_fade_step_s,
      defaults.indicator_fade_step_s,
    ),
    status_poll_connected_s: coercePositiveNumber(
      record.status_poll_connected_s,
      defaults.status_poll_connected_s,
    ),
    status_poll_disconnected_s: coercePositiveNumber(
      record.status_poll_disconnected_s,
      defaults.status_poll_disconnected_s,
    ),
    instance_poll_connected_s: coercePositiveNumber(
      record.instance_poll_connected_s,
      defaults.instance_poll_connected_s,
    ),
    instance_poll_disconnected_s: coercePositiveNumber(
      record.instance_poll_disconnected_s,
      defaults.instance_poll_disconnected_s,
    ),
    log_poll_connected_s: coercePositiveNumber(
      record.log_poll_connected_s,
      defaults.log_poll_connected_s,
    ),
    log_poll_disconnected_s: coercePositiveNumber(
      record.log_poll_disconnected_s,
      defaults.log_poll_disconnected_s,
    ),
    ipc_request_timeout_s: coercePositiveNumber(
      record.ipc_request_timeout_s,
      defaults.ipc_request_timeout_s,
    ),
    ipc_connect_backoff_initial_s: coercePositiveNumber(
      record.ipc_connect_backoff_initial_s,
      defaults.ipc_connect_backoff_initial_s,
    ),
    ipc_connect_backoff_extended_s: coercePositiveNumber(
      record.ipc_connect_backoff_extended_s,
      defaults.ipc_connect_backoff_extended_s,
    ),
    ipc_connect_backoff_escalate_after: coercePositiveInteger(
      record.ipc_connect_backoff_escalate_after,
      defaults.ipc_connect_backoff_escalate_after,
    ),
    status_repeat_throttle_connected_s: coercePositiveNumber(
      record.status_repeat_throttle_connected_s,
      defaults.status_repeat_throttle_connected_s,
    ),
    status_repeat_throttle_disconnected_s: coercePositiveNumber(
      record.status_repeat_throttle_disconnected_s,
      defaults.status_repeat_throttle_disconnected_s,
    ),
    stop_wait_disconnect_poll_s: coercePositiveNumber(
      record.stop_wait_disconnect_poll_s,
      defaults.stop_wait_disconnect_poll_s,
    ),
    stop_wait_disconnect_timeout_s: coercePositiveNumber(
      record.stop_wait_disconnect_timeout_s,
      defaults.stop_wait_disconnect_timeout_s,
    ),
    stop_wait_managed_exit_s: coercePositiveNumber(
      record.stop_wait_managed_exit_s,
      defaults.stop_wait_managed_exit_s,
    ),
    stop_wait_graceful_exit_s: coercePositiveNumber(
      record.stop_wait_graceful_exit_s,
      defaults.stop_wait_graceful_exit_s,
    ),
    stop_wait_forced_exit_s: coercePositiveNumber(
      record.stop_wait_forced_exit_s,
      defaults.stop_wait_forced_exit_s,
    ),
    template_cache_ttl_s: coercePositiveNumber(
      record.template_cache_ttl_s,
      defaults.template_cache_ttl_s,
    ),
    toast_duration_s: coercePositiveNumber(
      record.toast_duration_s,
      defaults.toast_duration_s,
    ),
    widget_auto_tick_s: coercePositiveNumber(
      record.widget_auto_tick_s,
      defaults.widget_auto_tick_s,
    ),
    widget_auto_refresh_default_s: coercePositiveNumber(
      record.widget_auto_refresh_default_s,
      defaults.widget_auto_refresh_default_s,
    ),
  };
}

export function parseControlSettingsFromToml(
  tomlText: string,
): Partial<ControlTimingSettings> {
  const parsed: Partial<ControlTimingSettings> = {};
  const lines = tomlText.split(/\r?\n/);
  let inControlSection = false;

  for (const rawLine of lines) {
    const noComment = rawLine.split("#", 2)[0]?.trim() ?? "";
    if (noComment.length === 0) {
      continue;
    }
    if (noComment.startsWith("[") && noComment.endsWith("]")) {
      inControlSection = noComment === "[control]";
      continue;
    }
    if (!inControlSection) {
      continue;
    }

    const sepIndex = noComment.indexOf("=");
    if (sepIndex < 1) {
      continue;
    }
    const key = noComment.slice(0, sepIndex).trim();
    const rawValue = noComment.slice(sepIndex + 1).trim();
    const numericValue = Number(rawValue.replace(/^"|"$/g, ""));
    if (!Number.isFinite(numericValue)) {
      continue;
    }

    switch (key) {
      case "indicator_fade_step_s":
      case "status_poll_connected_s":
      case "status_poll_disconnected_s":
      case "instance_poll_connected_s":
      case "instance_poll_disconnected_s":
      case "log_poll_connected_s":
      case "log_poll_disconnected_s":
      case "ipc_request_timeout_s":
      case "ipc_connect_backoff_initial_s":
      case "ipc_connect_backoff_extended_s":
      case "status_repeat_throttle_connected_s":
      case "status_repeat_throttle_disconnected_s":
      case "stop_wait_disconnect_poll_s":
      case "stop_wait_disconnect_timeout_s":
      case "stop_wait_managed_exit_s":
      case "stop_wait_graceful_exit_s":
      case "stop_wait_forced_exit_s":
      case "template_cache_ttl_s":
      case "toast_duration_s":
      case "widget_auto_tick_s":
      case "widget_auto_refresh_default_s":
        parsed[key] = numericValue;
        break;
      case "ipc_connect_backoff_escalate_after":
        parsed[key] = Math.max(1, Math.floor(numericValue));
        break;
      default:
        break;
    }
  }

  return parsed;
}
