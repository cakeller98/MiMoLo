declare module "electron" {
  export interface BrowserWindowConstructorOptions {
    width?: number;
    height?: number;
    backgroundColor?: string;
    webPreferences?: {
      contextIsolation?: boolean;
      nodeIntegration?: boolean;
      sandbox?: boolean;
    };
  }

  export class BrowserWindow {
    constructor(options?: BrowserWindowConstructorOptions);
    loadURL(url: string): Promise<void>;
    static getAllWindows(): BrowserWindow[];
  }

  export interface App {
    whenReady(): Promise<void>;
    on(event: "activate", listener: () => void): void;
    on(event: "window-all-closed", listener: () => void): void;
    quit(): void;
  }

  export const app: App;
}
