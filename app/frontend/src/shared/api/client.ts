/**
 * Authenticated control-plane client.
 *
 * Supabase remains the browser's identity provider only. Every product read/write goes
 * through FastAPI with a freshly obtained bearer token, so tables and service keys are
 * never part of browser business logic.
 */
import { supabase } from '@/lib/supabase';

declare global {
  interface Window {
    /** Injected by the desktop preload; the loopback proxy base URL. */
    __LITE_ATOMS_API_BASE_URL__?: string;
  }
}

const apiBaseUrl =
  (typeof window !== 'undefined' ? window.__LITE_ATOMS_API_BASE_URL__ : undefined) ??
  import.meta.env.VITE_API_BASE_URL ??
  'http://localhost:8000';

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

/** Make an authorized JSON request and normalize API error bodies for feature UI. */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session?.access_token) throw new ApiError(401, 'Authentication is required');
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      Authorization: `Bearer ${session.access_token}`,
      ...init.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export { apiBaseUrl };
