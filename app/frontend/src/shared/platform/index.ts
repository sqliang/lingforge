import type { DesktopBridge, PlatformAdapter } from './types';
import { createDesktopAdapter } from './desktop';
import { webAdapter } from './web';

declare global {
  interface Window {
    liteAtoms?: DesktopBridge;
  }
}

/**
 * Detected platform adapter for this runtime. The preload script runs before
 * any renderer module, so the bridge is visible at module scope here.
 */
export const platform: PlatformAdapter =
  typeof window !== 'undefined' && window.liteAtoms
    ? createDesktopAdapter(window.liteAtoms)
    : webAdapter;

export type {
  DesktopBridge,
  PlatformAdapter,
  PlatformCapabilities,
  PlatformInfo,
  WindowControls,
} from './types';
