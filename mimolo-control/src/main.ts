import { app, BrowserWindow } from "electron";

interface RuntimeProcess {
  platform?: string;
}

const runtimeProcess = (globalThis as { process?: RuntimeProcess }).process;

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1000,
    height: 700,
    backgroundColor: "#111111",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.loadURL("data:text/html,<h1>MiMoLo Control Placeholder</h1>");
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (runtimeProcess?.platform !== "darwin") {
    app.quit();
  }
});
