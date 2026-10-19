import http from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { startApiProxy, type ApiProxy } from '../electron/proxy';

describe('startApiProxy', () => {
  let upstream: http.Server;
  let proxy: ApiProxy;

  beforeEach(async () => {
    upstream = http.createServer((req, res) => {
      if (req.url === '/events') {
        res.writeHead(200, { 'content-type': 'text/event-stream' });
        res.write('data: one\n\n');
        res.write('data: two\n\n');
        res.end();
        return;
      }
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(
        JSON.stringify({ method: req.method, path: req.url, auth: req.headers.authorization ?? null }),
      );
    });
    await new Promise<void>((resolve) => upstream.listen(0, '127.0.0.1', resolve));
    const { port } = upstream.address() as AddressInfo;
    proxy = await startApiProxy(`http://127.0.0.1:${port}`);
  });

  afterEach(() => {
    proxy.close();
    upstream.close();
  });

  it('forwards method, path and authorization header', async () => {
    const res = await fetch(`${proxy.baseUrl}/v1/projects?x=1`, {
      headers: { authorization: 'Bearer token-123' },
    });
    expect(res.status).toBe(200);
    expect(res.headers.get('access-control-allow-origin')).toBe('*');
    expect(await res.json()).toEqual({
      method: 'GET',
      path: '/v1/projects?x=1',
      auth: 'Bearer token-123',
    });
  });

  it('answers CORS preflight without hitting upstream', async () => {
    const res = await fetch(`${proxy.baseUrl}/anything`, { method: 'OPTIONS' });
    expect(res.status).toBe(204);
    expect(res.headers.get('access-control-allow-headers')).toContain('authorization');
  });

  it('streams SSE bodies without buffering', async () => {
    const res = await fetch(`${proxy.baseUrl}/events`);
    expect(res.headers.get('content-type')).toBe('text/event-stream');
    expect(await res.text()).toBe('data: one\n\ndata: two\n\n');
  });
});
