declare module "electron" {
  export interface BrowserWindowConstructorOptions {
    width?: number;
    height?: number;
    minWidth?: number;
    minHeight?: number;
    backgroundColor?: string;
    webPreferences?: {
      contextIsolation?: boolean;
      nodeIntegration?: boolean;
      sandbox?: boolean;
      preload?: string;
    };
  }

  export class BrowserWindow {
    constructor(options?: BrowserWindowConstructorOptions);
    loadURL(url: string): Promise<void>;
    on(event: "closed", listener: () => void): void;
    webContents: {
      send(channel: string, payload: unknown): void;
    };
    static getAllWindows(): BrowserWindow[];
  }

  export interface App {
    whenReady(): Promise<void>;
    on(event: "activate", listener: () => void): void;
    on(event: "before-quit", listener: () => void): void;
    on(event: "window-all-closed", listener: () => void): void;
    quit(): void;
  }

  export interface IpcMain {
    handle(
      channel: string,
      handler: (...args: unknown[]) => unknown | Promise<unknown>
    ): void;
  }

  export interface IpcRenderer {
    on(
      channel: string,
      listener: (event: unknown, payload: unknown) => void
    ): void;
    invoke(channel: string, ...args: unknown[]): Promise<unknown>;
  }

  export interface ContextBridge {
    exposeInMainWorld(key: string, api: unknown): void;
  }

  export const app: App;
  export const ipcMain: IpcMain;
  export const ipcRenderer: IpcRenderer;
  export const contextBridge: ContextBridge;
}
