/**
 * Cloudflare Worker — reverse proxy for OpenMemory REST API.
 *
 * ChatGPT (HTTPS) → Worker → HTTP → nginx (port 80) → backend (port 8765)
 *
 * Nginx gates this path with X-CF-Worker header check, so direct HTTP
 * access to /api/ without the header returns 403.
 */

const ORIGIN = "http://47.108.141.20";
const CF_WORKER_SECRET = "openmemory";

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return handleCORS();
    }

    const url = new URL(request.url);

    if (!url.pathname.startsWith("/api/")) {
      return new Response("Not found", { status: 404 });
    }

    const originUrl = ORIGIN + url.pathname + url.search;

    const headers = new Headers(request.headers);
    headers.set("X-CF-Worker", CF_WORKER_SECRET);

    const resp = await fetch(originUrl, {
      method: request.method,
      headers: headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    });

    const respHeaders = new Headers(resp.headers);
    respHeaders.set("Access-Control-Allow-Origin", "*");
    respHeaders.set("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization");
    respHeaders.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");

    return new Response(resp.body, {
      status: resp.status,
      headers: respHeaders,
    });
  },
};

function handleCORS() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Authorization",
      "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
      "Access-Control-Max-Age": "86400",
    },
  });
}
