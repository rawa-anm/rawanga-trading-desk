/*
 * Copyright 2026 Andrei Maltsev (Rawanga)
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* sw.js — Rawanga Trading Desk PWA service worker.
 *
 * Purpose: the window must still OPEN when the local server is not reachable
 * (engine restarting, port not yet up) instead of showing a browser error.
 *
 * Cache policy is deliberately conservative — this is a trading terminal:
 *   1) /api/*  — NEVER cached. Prices, signals and trades always come from the
 *                server; a stale price must never be used for a decision.
 *                Offline we answer 503, we do not replay an old response.
 *   2) "/" and the shell — network-first, a copy is kept for offline opening.
 *   3) /static/* — cache-first (assets are versioned: app.js carries ?v=<hash>).
 *   4) everything else, GET, same origin — network-first, cache fallback.
 */
const VER = "rtd-v2";   // bumped: shell assets changed (mobile layout)
const SHELL = [
  "/",
  "/static/js/app.js",
  "/static/js/i18n.js",
  "/static/js/lightweight-charts.standalone.production.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(VER).then(async (c) => {
      // one by one: a single failed asset must not abort the whole install
      await Promise.all(
        SHELL.map((u) => c.add(new Request(u, { cache: "reload" })).catch(() => null))
      );
      await self.skipWaiting();
    })
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VER).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (e) => {
  if (e.data === "skipWaiting") self.skipWaiting();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // never touch third parties

  // 1) API — network only. No stale prices, ever.
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(req).catch(() =>
        new Response(
          JSON.stringify({ error: "offline", detail: "server is not reachable" }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    return;
  }

  // 2) Service endpoints — bypass the cache.
  if (url.pathname === "/health" || url.pathname === "/sw.js" ||
      url.pathname === "/manifest.webmanifest") {
    return;
  }

  // 3) Static assets — cache-first (versioned).
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(req).then((hit) =>
        hit ||
        fetch(req).then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(VER).then((c) => c.put(req, copy)).catch(() => {});
          }
          return res;
        })
      )
    );
    return;
  }

  // 4) Shell and the rest — network, cache as a fallback.
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(VER).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(async () => {
        const hit = await caches.match(req);
        if (hit) return hit;
        const shell = await caches.match("/");
        if (shell) return shell;
        return new Response("Server is not reachable", {
          status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" },
        });
      })
  );
});
