// dock-sw.js — Service Worker for Broadcast Playroom OBS Dock Offline Fallback
const CACHE_NAME = 'bp-dock-offline-v1';
const OFFLINE_URL = '/dock-offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll([OFFLINE_URL, '/dock']);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((k) => {
          if (k !== CACHE_NAME) return caches.delete(k);
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // Intercept navigation requests to /dock or /
  if (event.request.mode === 'navigate' || url.pathname === '/dock') {
    event.respondWith(
      fetch(event.request).catch(async () => {
        const cache = await caches.open(CACHE_NAME);
        const cached = await cache.match(OFFLINE_URL);
        return cached || new Response('Broadcast Playroom is offline', {
          headers: { 'Content-Type': 'text/html; charset=utf-8' }
        });
      })
    );
  }
});
