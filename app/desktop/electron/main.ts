/**
 * @file Electron main process
 *
 * Window lifecycle, window-control IPC, and the loopback API proxy. This
 * process is the future host of the local database and local agent runtime;
 * keep renderer-facing surface behind the preload whitelist only.
 */
import path from 'node:path';
import { app, BrowserWindow, ipcMain } from 'electron';
import { startApiProxy, type ApiProxy } from './proxy';

const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? 'http://localhost:3000';
const API_TARGET = process.env.LITE_ATOMS_API_TARGET ?? 'http://localhost:8000';

let proxy: ApiProxy | undefined;
let ipcRegistered = false;

/**
 * Register IPC handlers once for the app lifetime. Window commands resolve the
 * sender's window at dispatch time, so macOS dock re-activation (which creates
 * a fresh window) never double-registers or touches a destroyed window.
 */
function registerIpc(): void {
  if (ipcRegistered) return;
  ipcRegistered = true;
  ipcMain.on('window:minimize', (event) => {
    BrowserWindow.fromWebContents(event.sender)?.minimize();
  });
  ipcMain.on('window:maximize', (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return;
    if (win.isMaximized()) win.unmaximize();
    else win.maximize();
  });
  ipcMain.on('window:close', (event) => {
    BrowserWindow.fromWebContents(event.sender)?.close();
  });
  ipcMain.handle('app:info', () => ({ appVersion: app.getVersion(), platform: process.platform }));
}

async function createWindow(): Promise<void> {
  proxy ??= await startApiProxy(API_TARGET);
  registerIpc();

  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--lite-atoms-api-base=${proxy.baseUrl}`],
    },
  });

  if (!app.isPackaged) {
    await win.loadURL(DEV_SERVER_URL);
  } else {
    await win.loadFile(path.join(__dirname, '../../../frontend/dist/index.html'));
  }
}

app.on('quit', () => proxy?.close());

void app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) void createWindow();
});
