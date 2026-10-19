/**
 * @file Loopback API proxy
 *
 * The packaged renderer runs from a file:// origin, so direct API calls would
 * fail CORS preflight and complicate SSE. The renderer therefore talks to
 * http://127.0.0.1:<port>; this proxy forwards requests verbatim to the real
 * API and adds permissive CORS headers. It must not buffer response bodies —
 * Run event streams (SSE) flow through it.
 */
import http from 'node:http';
import type { AddressInfo } from 'node:net';

export interface ApiProxy {
  readonly baseUrl: string;
  close(): void;
}

/** Start a loopback proxy forwarding all requests to `target` (e.g. http://localhost:8000). */
export async function startApiProxy(target: string): Promise<ApiProxy> {
  const targetUrl = new URL(target);
  const server = http.createServer((req, res) => {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'access-control-allow-origin': '*',
        'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
        'access-control-allow-headers': 'authorization,content-type,accept,last-event-id',
      });
      res.end();
      return;
    }
    const upstream = http.request(
      {
        hostname: targetUrl.hostname,
        port: targetUrl.port,
        path: req.url,
        method: req.method,
        headers: { ...req.headers, host: targetUrl.host },
      },
      (upstreamRes) => {
        res.writeHead(upstreamRes.statusCode ?? 502, {
          ...upstreamRes.headers,
          'access-control-allow-origin': '*',
        });
        upstreamRes.pipe(res);
      },
    );
    upstream.on('error', () => {
      if (!res.headersSent) res.writeHead(502);
      res.end();
    });
    req.pipe(upstream);
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address() as AddressInfo;
  return { baseUrl: `http://127.0.0.1:${port}`, close: () => server.close() };
}
