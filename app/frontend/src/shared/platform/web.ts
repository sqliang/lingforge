import type { PlatformAdapter } from './types';

/** Browser host: no desktop capabilities, no native window controls. */
export const webAdapter: PlatformAdapter = {
  kind: 'web',
  capabilities: { localAgent: false, localDatabase: false, fileSystem: false },
  info: async () => ({ appVersion: 'web', platform: 'web' }),
};
