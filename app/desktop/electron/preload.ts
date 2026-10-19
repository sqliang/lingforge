/**
 * @file Preload bridge
 *
 * The only surface between the sandboxed renderer and the main process.
 * Exposes the whitelisted `window.liteAtoms` API and the loopback API base
 * URL that the main process passes via additionalArguments (readable from
 * process.argv in sandboxed preloads).
 */
import { contextBridge, ipcRenderer } from 'electron';

const API_BASE_PREFIX = '--lite-atoms-api-base=';
const apiBaseArg = process.argv.find((arg) => arg.startsWith(API_BASE_PREFIX));
const apiBaseUrl = apiBaseArg ? apiBaseArg.slice(API_BASE_PREFIX.length) : undefined;

contextBridge.exposeInMainWorld('__LITE_ATOMS_API_BASE_URL__', apiBaseUrl);
contextBridge.exposeInMainWorld('liteAtoms', {
  window: {
    minimize: () => ipcRenderer.send('window:minimize'),
    maximize: () => ipcRenderer.send('window:maximize'),
    close: () => ipcRenderer.send('window:close'),
  },
  info: () => ipcRenderer.invoke('app:info'),
});
