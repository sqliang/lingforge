import type { DesktopBridge, PlatformAdapter } from './types';

/**
 * Wrap the preload bridge. Capabilities stay false until the main-process
 * services (SQLite, local agent) are implemented in later phases.
 */
export function createDesktopAdapter(bridge: DesktopBridge): PlatformAdapter {
  return {
    kind: 'desktop',
    capabilities: { localAgent: false, localDatabase: false, fileSystem: false },
    window: bridge.window,
    info: () => bridge.info(),
  };
}
