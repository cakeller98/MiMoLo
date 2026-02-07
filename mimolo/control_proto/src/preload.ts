import { contextBridge, ipcRenderer } from "electron";

interface OpsStatusPayload {
  detail: string;
  state: "connected" | "disconnected" | "starting";
  timestamp: string;
}

interface InitialStatePayload {
  ipcPath: string;
  opsLogPath: string;
  status: OpsStatusPayload;
}

contextBridge.exposeInMainWorld("mmlProto", {
  getInitialState: (): Promise<InitialStatePayload> => {
    return ipcRenderer.invoke("mml:initial-state") as Promise<InitialStatePayload>;
  },
  onOpsLine: (callback: (line: string) => void): void => {
    ipcRenderer.on("ops:line", (_event, line: unknown) => {
      callback(String(line));
    });
  },
  onOpsStatus: (callback: (payload: OpsStatusPayload) => void): void => {
    ipcRenderer.on("ops:status", (_event, payload: unknown) => {
      const typed = payload as OpsStatusPayload;
      callback(typed);
    });
  },
});
