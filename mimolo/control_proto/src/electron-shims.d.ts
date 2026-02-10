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

  export interface AppEvent {
    preventDefault(): void;
  }

  export interface App {
    whenReady(): Promise<void>;
    on(event: "activate", listener: () => void): void;
    on(event: "before-quit", listener: () => void): void;
    on(event: "window-all-closed", listener: () => void): void;
    on(event: "will-quit", listener: (event: AppEvent) => void): void;
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

  export interface OpenDialogOptions {
    title?: string;
    properties?: string[];
    filters?: Array<{
      name: string;
      extensions: string[];
    }>;
  }

  export interface OpenDialogReturnValue {
    canceled: boolean;
    filePaths: string[];
  }

  export interface MessageBoxOptions {
    type?: "none" | "info" | "error" | "question" | "warning";
    buttons?: string[];
    defaultId?: number;
    cancelId?: number;
    noLink?: boolean;
    title?: string;
    message?: string;
    detail?: string;
  }

  export interface MessageBoxReturnValue {
    response: number;
  }

  export interface Dialog {
    showOpenDialog(
      browserWindow: BrowserWindow,
      options: OpenDialogOptions
    ): Promise<OpenDialogReturnValue>;
    showMessageBox(
      browserWindow: BrowserWindow | undefined,
      options: MessageBoxOptions
    ): Promise<MessageBoxReturnValue>;
  }

  export const app: App;
  export const ipcMain: IpcMain;
  export const ipcRenderer: IpcRenderer;
  export const contextBridge: ContextBridge;
  export const dialog: Dialog;
  const electronDefault: {
    app: App;
    BrowserWindow: typeof BrowserWindow;
    ipcMain: IpcMain;
    ipcRenderer: IpcRenderer;
    contextBridge: ContextBridge;
    dialog: Dialog;
  };
  export default electronDefault;
}

declare module "electron/main" {
  const electronMain: typeof import("electron");
  export default electronMain;
}
