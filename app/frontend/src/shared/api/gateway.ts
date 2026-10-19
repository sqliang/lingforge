/**
 * @file BackendGateway
 *
 * Tier-2 seam for the local-first roadmap: every control-plane call is shaped by
 * this interface. Today the only implementation is HTTP (wrapping client.ts);
 * the desktop shell will add a LocalGateway backed by the main-process SQLite /
 * agent runtime, and the swap happens only here — feature code never changes.
 */
import { apiBaseUrl, apiRequest } from './client';

export interface BackendGateway {
  readonly baseUrl: string;
  request<T>(path: string, init?: RequestInit): Promise<T>;
}

/** HTTP implementation: identical behavior to the existing client. */
export const httpGateway: BackendGateway = {
  baseUrl: apiBaseUrl,
  request: <T>(path: string, init: RequestInit = {}) => apiRequest<T>(path, init),
};
