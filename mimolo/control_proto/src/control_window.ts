import type { BrowserWindow, BrowserWindowConstructorOptions } from "electron";
import type { ControlTimingSettings } from "./types.js";

type BrowserWindowCtor = new (
  options: BrowserWindowConstructorOptions,
) => BrowserWindow;

type BuildHtml = (
  controlTimingSettings: ControlTimingSettings,
  controlDevMode: boolean,
) => string;

type CreateWindowOptions = {
  BrowserWindow: BrowserWindowCtor;
  controlTimingSettings: ControlTimingSettings;
  controlDevMode: boolean;
  buildHtml: BuildHtml;
  onClosed: () => void;
};

export function createMainWindow(options: CreateWindowOptions): BrowserWindow {
  const window = new options.BrowserWindow({
    width: 1360,
    height: 820,
    minWidth: 1080,
    minHeight: 660,
    backgroundColor: "#0e1014",
    webPreferences: {
      contextIsolation: false,
      nodeIntegration: true,
      sandbox: false,
    },
  });

  const html = options.buildHtml(
    options.controlTimingSettings,
    options.controlDevMode,
  );
  window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
  window.on("closed", options.onClosed);
  return window;
}
