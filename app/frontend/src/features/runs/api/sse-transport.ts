/**
 * @file SSE Transport
 * 
 * The only browser entry point for authenticated SSE.
 *
 * It isolates an older third-party dependency, validates response semantics, and keeps
 * bearer tokens out of URLs. Feature code consumes typed events rather than library APIs.
 *
 * Retry design: fetch-event-source freezes request headers for its internal retries,
 * so an expired token cannot be healed inside `onopen`. The single token refresh
 * therefore lives in the outer loop, where every attempt calls `authHeaders()` again.
 */

import { fetchEventSource } from '@microsoft/fetch-event-source';
import { apiBaseUrl } from '@/shared/api/client';
import { supabase } from '@/lib/supabase';
import type { SseConnectionState } from '@/features/workspace/model/workspace-store';

export interface RunEvent {
  schemaVersion: 1;
  runId: string;
  sequence: number;
  at: string;
  payload: Record<string, unknown>;
}

export interface ConnectRunEventsInput {
  projectId: string;
  runId: string;
  lastEventId?: number;
  signal: AbortSignal;
  onEvent: (type: string, event: RunEvent) => void;
  onConnectionState: (state: SseConnectionState) => void;
  onHistoryExpired: () => Promise<number>;
}

class TerminalSseError extends Error {}
class UnauthorizedSseError extends Error {}

/**
 * Get authenticated headers for SSE requests.
 *
 * @param lastEventId Optional last event ID to continue from.
 * @returns Authenticated headers.
 */
async function authHeaders(lastEventId?: number): Promise<Record<string, string>> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session?.access_token) throw new TerminalSseError('Authentication is required');
  return {
    Accept: 'text/event-stream',
    Authorization: `Bearer ${session.access_token}`,
    ...(lastEventId ? { 'Last-Event-ID': String(lastEventId) } : {}),
  };
}

/** 
 * Open one stream attempt with freshly minted headers. Abort always stops retries. 
 * 
 * @param input Connection input.
 * @returns Promise that resolves when the stream is connected or rejected.
 */
async function openRunStream(input: ConnectRunEventsInput): Promise<void> {
  input.onConnectionState('connecting');
  await fetchEventSource(`${apiBaseUrl}/v1/projects/${input.projectId}/runs/${input.runId}/events`, {
    method: 'GET',
    signal: input.signal,
    headers: await authHeaders(input.lastEventId),
    openWhenHidden: false,
    
    async onopen(response) {
      const contentType = response.headers.get('content-type') ?? '';
      if (response.status === 200 && contentType.includes('text/event-stream')) {
        input.onConnectionState('connected');
        return;
      }
      if (response.status === 401) throw new UnauthorizedSseError('SSE unauthorized (401)');
      if (response.status === 410) {
        await input.onHistoryExpired();
        throw new Error('retry_after_snapshot');
      }
      if ([403, 404].includes(response.status)) throw new TerminalSseError(`SSE access denied (${response.status})`);
      throw new Error(`SSE request failed (${response.status})`);
    },

    onmessage(message) {
      if (!message.data || message.data === '[DONE]') return;
      const event = JSON.parse(message.data) as RunEvent;
      const id = Number(message.id);
      if (event.schemaVersion !== 1 || event.runId !== input.runId || event.sequence !== id) {
        throw new TerminalSseError('Received an invalid SSE envelope');
      }
      input.onEvent(message.event || 'message', event);
    },

    
    onclose() {
      input.onConnectionState('closed');
      // The server closes the stream only at a terminal Run state. Without throwing,
      // fetch-event-source would reconnect forever and endlessly replay closed history.
      throw new TerminalSseError('SSE stream closed by the server');
    },

    /**
     * Handle errors from fetch-event-source.
     * 
     * @param error Error object.
     * @returns Retry delay in milliseconds.
     */
    onerror(error) {
      // 401 must reach the outer refresh loop, not the frozen-header internal retry.
      if (input.signal.aborted || error instanceof TerminalSseError || error instanceof UnauthorizedSseError) throw error;
      input.onConnectionState('reconnecting');
      return Math.min(1_000 * 2 ** Math.min(3, Math.floor(Math.random() * 4)), 10_000);
    },
    
  });
}


/**
 * Connect and replay a Run stream; one token refresh is attempted on 401. 
 * 
 * @param input Connection input.
 * @returns Promise that resolves when the stream is connected or rejected.
 */
export async function connectRunEvents(input: ConnectRunEventsInput): Promise<void> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      await openRunStream(input);
      return;
    } catch (error) {
      if (error instanceof UnauthorizedSseError && attempt === 0 && !input.signal.aborted) {
        await supabase.auth.refreshSession();
        continue;
      }
      throw error;
    }
  }
}

