export interface RuntimeProcess {
  env: Record<string, string | undefined>;
  cwd?: () => string;
  platform?: string;
}

export interface OpsStatusPayload {
  detail: string;
  state: "connected" | "disconnected" | "starting";
  timestamp: string;
}

export interface MonitorSettingsSnapshot {
  console_verbosity: "debug" | "info" | "warning" | "error";
  cooldown_seconds: number;
  poll_tick_s: number;
}

export interface RuntimePerfSnapshot {
  agents?: {
    top_by_drain_avg_ms?: Array<{
      drain_avg_ms?: number;
      label?: string;
      messages_total?: number;
    }>;
  };
  process?: {
    cpu_percent_lifetime?: number;
    cpu_percent_recent?: number;
    rss_bytes?: number | null;
  };
  tick?: {
    avg_ms?: number;
    p95_ms?: number;
  };
}

export interface ControlTimingSettings {
  indicator_fade_step_s: number;
  instance_poll_connected_s: number;
  instance_poll_disconnected_s: number;
  ipc_request_timeout_s: number;
  ipc_connect_backoff_escalate_after: number;
  ipc_connect_backoff_extended_s: number;
  ipc_connect_backoff_initial_s: number;
  log_poll_connected_s: number;
  log_poll_disconnected_s: number;
  status_poll_connected_s: number;
  status_poll_disconnected_s: number;
  status_repeat_throttle_connected_s: number;
  status_repeat_throttle_disconnected_s: number;
  stop_wait_disconnect_poll_s: number;
  stop_wait_disconnect_timeout_s: number;
  stop_wait_forced_exit_s: number;
  stop_wait_graceful_exit_s: number;
  stop_wait_managed_exit_s: number;
  template_cache_ttl_s: number;
  toast_duration_s: number;
  widget_auto_refresh_default_s: number;
  widget_auto_tick_s: number;
}

export type AgentLifecycleState = "running" | "shutting-down" | "inactive" | "error";
export type AgentCommandAction =
  | "start_agent"
  | "stop_agent"
  | "restart_agent"
  | "add_agent_instance"
  | "duplicate_agent_instance"
  | "remove_agent_instance"
  | "update_agent_instance";

export interface AgentInstanceSnapshot {
  config: Record<string, unknown>;
  detail: string;
  label: string;
  state: AgentLifecycleState;
  template_id: string;
}

export interface AgentTemplateSnapshot {
  default_config: Record<string, unknown>;
  script: string;
  template_id: string;
}

export interface ControlCommandPayload {
  action: AgentCommandAction;
  label?: string;
  requested_label?: string;
  template_id?: string;
  updates?: Record<string, unknown>;
}

export interface IpcResponsePayload {
  cmd?: string;
  data?: Record<string, unknown>;
  error?: string;
  ok: boolean;
  request_id?: string;
  timestamp?: string;
}

export interface IpcTrafficPayload {
  direction: "tx" | "rx";
  kind: IpcTrafficClass;
  label?: string;
  timestamp: string;
}

export type IpcTrafficClass = "interactive" | "background";

export interface PendingIpcRequest {
  id: string;
  payload: Record<string, unknown>;
  reject: (reason: Error) => void;
  resolve: (value: IpcResponsePayload) => void;
  timeoutHandle: ReturnType<typeof setTimeout> | null;
  trafficClass: IpcTrafficClass;
  trafficLabel?: string;
}

export type OperationsProcessState = "running" | "stopped" | "starting" | "stopping" | "error";

export interface OperationsControlSnapshot {
  detail: string;
  managed: boolean;
  pid: number | null;
  state: OperationsProcessState;
  timestamp: string;
}

export interface OperationsControlRequest {
  action: "start" | "stop" | "restart" | "status";
}
