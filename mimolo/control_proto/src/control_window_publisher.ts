import type { BrowserWindow } from "electron";
import type {
  AgentInstanceSnapshot,
  IpcTrafficClass,
  MonitorSettingsSnapshot,
  OperationsControlSnapshot,
  OpsStatusPayload,
} from "./types.js";

type GetMainWindow = () => BrowserWindow | null;

export class WindowPublisher {
  private readonly getMainWindow: GetMainWindow;

  constructor(getMainWindow: GetMainWindow) {
    this.getMainWindow = getMainWindow;
  }

  publishLine(line: string): void {
    const window = this.getMainWindow();
    if (!window) {
      return;
    }
    window.webContents.send("ops:line", line);
  }

  publishBootstrapLine(line: string): void {
    const window = this.getMainWindow();
    if (!window) {
      return;
    }
    window.webContents.send("ops:bootstrap-line", line);
  }

  publishTraffic(
    direction: "tx" | "rx",
    kind: IpcTrafficClass,
    label?: string,
  ): void {
    const window = this.getMainWindow();
    if (!window) {
      return;
    }
    window.webContents.send("ops:traffic", {
      direction,
      kind,
      label,
      timestamp: new Date().toISOString(),
    });
  }

  publishStatus(status: OpsStatusPayload): void {
    const window = this.getMainWindow();
    if (!window) {
      return;
    }
    window.webContents.send("ops:status", status);
  }

  publishInstances(instances: Record<string, AgentInstanceSnapshot>): void {
    const window = this.getMainWindow();
    if (!window) {
      return;
    }
    window.webContents.send("ops:instances", { instances });
  }

  publishMonitorSettings(monitor: MonitorSettingsSnapshot): void {
    const window = this.getMainWindow();
    if (!window) {
      return;
    }
    window.webContents.send("ops:monitor-settings", { monitor });
  }

  publishOperationsControlState(state: OperationsControlSnapshot): void {
    const window = this.getMainWindow();
    if (!window) {
      return;
    }
    window.webContents.send("ops:process", state);
  }
}
