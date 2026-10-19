/**
 * @file Electron main process
 *
 * Window lifecycle, window-control IPC, and the loopback API proxy. This
 * process is the future host of the local database and local agent runtime;
 * keep renderer-facing surface behind the preload whitelist only.
 */
import path from 'node:path';
import { app, BrowserWindow, ipcMain } from 'electron';
import { startApiProxy } from './proxy';

const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? 'http://localhost:3000';
const API_TARGET = process.env.LITE_ATOMS_API_TARGET ?? 'http://localhost:8000';

async function createWindow(): Promise<void> {
  const proxy = await startApiProxy(API_TARGET);
  app.on('quit', () => proxy.close());

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

  ipcMain.on('window:minimize', () => win.minimize());
  ipcMain.on('window:maximize', () => (win.isMaximized() ? win.unmaximize() : win.maximize()));
  ipcMain.on('window:close', () => win.close());
  ipcMain.handle('app:info', () => ({ appVersion: app.getVersion(), platform: process.platform }));

  if (!app.isPackaged) {
    await win.loadURL(DEV_SERVER_URL);
  } else {
    await win.loadFile(path.join(__dirname, '../../frontend/dist/index.html'));
  }
}

void app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) void createWindow();
});
