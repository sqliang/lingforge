/**
 * @file Platform types
 *
 * Contract between the renderer and its host (browser tab or Electron shell).
 * Capabilities describe what the host can do; desktop-only services (local
 * database, local agent) will surface here as they land.
 */

export interface PlatformCapabilities {
  localAgent: boolean;
  localDatabase: boolean;
  fileSystem: boolean;
}

export interface WindowControls {
  minimize(): void;
  maximize(): void;
  close(): void;
}

export interface PlatformInfo {
  appVersion: string;
  platform: string;
}

export interface PlatformAdapter {
  readonly kind: 'web' | 'desktop';
  readonly capabilities: PlatformCapabilities;
  /** Present on desktop only. */
  readonly window?: WindowControls;
  info(): Promise<PlatformInfo>;
}

/** Bridge shape exposed by the desktop preload script on `window.liteAtoms`. */
export interface DesktopBridge {
  window: WindowControls;
  info(): Promise<PlatformInfo>;
}
