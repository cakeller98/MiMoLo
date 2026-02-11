import type {
  AgentInstanceSnapshot,
  AgentTemplateSnapshot,
  ControlTimingSettings,
  IpcResponsePayload,
  IpcTrafficClass,
  MonitorSettingsSnapshot,
  OperationsControlSnapshot,
  OperationsProcessState,
  OpsStatusPayload,
} from "./types.js";
import {
  extractAgentInstances,
  extractTemplates,
  normalizeDisconnectedStatusDetail,
  normalizeMonitorSettings,
} from "./control_proto_utils.js";
import type { TemplateCache } from "./control_template_cache.js";

type SendIpcCommandFn = (
  cmd: string,
  extraPayload?: Record<string, unknown>,
  trafficLabel?: string,
  trafficClass?: IpcTrafficClass,
) => Promise<IpcResponsePayload>;

type SnapshotRefresherDeps = {
  applyControlTimingSettings: (raw: unknown) => void;
  defaultMonitorSettings: MonitorSettingsSnapshot;
  getControlTimingSettings: () => ControlTimingSettings;
  getOperationsControlState: () => OperationsControlSnapshot;
  hasManagedOperationsProcess: () => boolean;
  initializeOpsLogFile: () => Promise<void>;
  publishInstances: (instances: Record<string, AgentInstanceSnapshot>) => void;
  publishLine: (line: string) => void;
  publishMonitorSettings: (monitor: MonitorSettingsSnapshot) => void;
  publishRuntimePerf: (runtimePerf: Record<string, unknown>) => void;
  publishStatus: (status: OpsStatusPayload) => void;
  restartBackgroundTimers: () => void;
  sendIpcCommand: SendIpcCommandFn;
  setOperationsControlState: (
    state: OperationsProcessState,
    detail: string,
    managed: boolean,
    pid: number | null,
  ) => void;
  templateCache: TemplateCache;
};

export class ControlSnapshotRefresher {
  private readonly deps: SnapshotRefresherDeps;
  private lastStatus: OpsStatusPayload = {
    state: "starting",
    detail: "waiting_for_operations",
    timestamp: new Date().toISOString(),
  };
  private lastMonitorSettings: MonitorSettingsSnapshot;
  private lastAgentInstances: Record<string, AgentInstanceSnapshot> = {};

  constructor(deps: SnapshotRefresherDeps) {
    this.deps = deps;
    this.lastMonitorSettings = { ...deps.defaultMonitorSettings };
  }

  getStatus(): OpsStatusPayload {
    return this.lastStatus;
  }

  getMonitorSettings(): MonitorSettingsSnapshot {
    return this.lastMonitorSettings;
  }

  getAgentInstances(): Record<string, AgentInstanceSnapshot> {
    return this.lastAgentInstances;
  }

  async refreshIpcStatus(): Promise<void> {
    try {
      const response = await this.deps.sendIpcCommand(
        "ping",
        undefined,
        undefined,
        "background",
      );
      if (response.ok) {
        this.setStatus("connected", "ipc_ready");
        if (!this.deps.hasManagedOperationsProcess()) {
          const opsState = this.deps.getOperationsControlState();
          if (
            opsState.state !== "stopping" ||
            opsState.detail !== "external_stop_requested"
          ) {
            this.deps.setOperationsControlState(
              "running",
              "external_unmanaged",
              false,
              null,
            );
          }
        }
        void this.refreshRuntimePerf();
        return;
      }
      this.setStatus("disconnected", response.error || "ipc_unavailable");
      this.updateUnmanagedStoppedState();
    } catch (err) {
      const detail = err instanceof Error ? err.message : "ipc_unavailable";
      this.setStatus("disconnected", detail);
      this.updateUnmanagedStoppedState();
    }
  }

  async refreshAgentInstances(): Promise<void> {
    if (this.lastStatus.state !== "connected") {
      return;
    }
    try {
      const response = await this.deps.sendIpcCommand(
        "get_agent_instances",
        undefined,
        undefined,
        "background",
      );
      if (!response.ok) {
        return;
      }
      this.lastAgentInstances = extractAgentInstances(response);
      this.deps.publishInstances(this.lastAgentInstances);
    } catch {
      // Ignore transient polling failures; status loop reports IPC health.
    }
  }

  async refreshTemplates(): Promise<Record<string, AgentTemplateSnapshot>> {
    const response = await this.deps.sendIpcCommand(
      "list_agent_templates",
      undefined,
      undefined,
      "background",
    );
    if (!response.ok) {
      return {};
    }
    return extractTemplates(response);
  }

  async refreshTemplatesCached(
    forceRefresh = false,
  ): Promise<Record<string, AgentTemplateSnapshot>> {
    return this.deps.templateCache.getTemplates(forceRefresh, () =>
      this.refreshTemplates(),
    );
  }

  async refreshMonitorSettings(): Promise<void> {
    try {
      const response = await this.deps.sendIpcCommand(
        "get_monitor_settings",
        undefined,
        undefined,
        "background",
      );
      if (!response.ok) {
        return;
      }
      const monitorRaw = response.data?.monitor;
      const controlRaw = response.data?.control;
      this.lastMonitorSettings = normalizeMonitorSettings(
        monitorRaw,
        this.deps.defaultMonitorSettings,
      );
      this.deps.applyControlTimingSettings(controlRaw);
      this.deps.publishMonitorSettings(this.lastMonitorSettings);
      this.deps.restartBackgroundTimers();
    } catch {
      // Ignore transient failures; status and loop timers continue with last known settings.
    }
  }

  async refreshRuntimePerf(): Promise<void> {
    if (this.lastStatus.state !== "connected") {
      return;
    }
    try {
      const response = await this.deps.sendIpcCommand(
        "get_runtime_perf",
        undefined,
        undefined,
        "background",
      );
      if (!response.ok) {
        return;
      }
      const runtimePerf = response.data?.runtime_perf;
      if (!runtimePerf || typeof runtimePerf !== "object") {
        return;
      }
      this.deps.publishRuntimePerf(runtimePerf as Record<string, unknown>);
    } catch {
      // Ignore transient polling failures; status loop reports IPC health.
    }
  }

  async updateMonitorSettings(
    updates: Record<string, unknown>,
  ): Promise<IpcResponsePayload> {
    const response = await this.deps.sendIpcCommand("update_monitor_settings", {
      updates,
    });
    if (!response.ok) {
      return response;
    }
    const monitorRaw = response.data?.monitor;
    const controlRaw = response.data?.control;
    this.lastMonitorSettings = normalizeMonitorSettings(
      monitorRaw,
      this.deps.defaultMonitorSettings,
    );
    this.deps.applyControlTimingSettings(controlRaw);
    this.deps.publishMonitorSettings(this.lastMonitorSettings);
    this.deps.restartBackgroundTimers();
    return response;
  }

  async loadInitialSnapshot(): Promise<void> {
    await this.deps.initializeOpsLogFile();
    await this.refreshIpcStatus();
    if (this.lastStatus.state === "connected") {
      await this.refreshMonitorSettings();
    }
    try {
      const registeredResponse = await this.deps.sendIpcCommand(
        "get_registered_plugins",
        undefined,
        undefined,
        "background",
      );
      this.deps.publishLine(`[ipc] ${JSON.stringify(registeredResponse)}`);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "plugin_query_failed";
      this.deps.publishLine(`[ipc] get_registered_plugins failed: ${detail}`);
    }

    await this.refreshAgentInstances();
    await this.refreshTemplates();
  }

  private setStatus(state: OpsStatusPayload["state"], detail: string): void {
    const normalizedDetail =
      state === "disconnected"
        ? normalizeDisconnectedStatusDetail(detail)
        : detail;
    const timing = this.deps.getControlTimingSettings();
    const connectedThrottleMs = Math.max(
      1,
      Math.round(timing.status_repeat_throttle_connected_s * 1000),
    );
    const disconnectedThrottleMs = Math.max(
      1,
      Math.round(timing.status_repeat_throttle_disconnected_s * 1000),
    );
    const throttleMs =
      state === "disconnected" ? disconnectedThrottleMs : connectedThrottleMs;
    const previousTimestampMs = Date.parse(this.lastStatus.timestamp);
    const elapsedMs = Number.isNaN(previousTimestampMs)
      ? Number.POSITIVE_INFINITY
      : Date.now() - previousTimestampMs;
    if (
      this.lastStatus.state === state &&
      this.lastStatus.detail === normalizedDetail &&
      elapsedMs < throttleMs
    ) {
      return;
    }

    this.lastStatus = {
      state,
      detail: normalizedDetail,
      timestamp: new Date().toISOString(),
    };
    this.deps.publishStatus(this.lastStatus);
  }

  private updateUnmanagedStoppedState(): void {
    if (this.deps.hasManagedOperationsProcess()) {
      return;
    }
    const opsState = this.deps.getOperationsControlState();
    if (
      opsState.state === "stopping" &&
      opsState.detail === "external_stop_requested"
    ) {
      this.deps.setOperationsControlState("stopped", "stopped_via_ipc", false, null);
      return;
    }
    this.deps.setOperationsControlState("stopped", "not_managed", false, null);
  }
}
