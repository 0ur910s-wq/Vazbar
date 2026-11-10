// Πράσινα Νέα – Service Worker
// Αποθηκεύει το "κέλυφος" της εφαρμογής ώστε να ανοίγει και χωρίς δίκτυο.
// Οι ειδήσεις (RSS / proxies / καιρός) ΔΕΝ περνούν από εδώ – πάντα φρέσκες από το δίκτυο.
const VERSION = 'pn-v3';
const SHELL = ['./', './index.html', './manifest.json', './icon-192.png', './icon-512.png'];
const CDN_HOSTS = ['cdn.tailwindcss.com', 'unpkg.com', 'fonts.googleapis.com', 'fonts.gstatic.com'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(VERSION).then((cache) =>
      // Ένα-ένα, ώστε αν λείπει κάποιο αρχείο να μην αποτύχει όλη η εγκατάσταση
      Promise.all(SHELL.map((url) => cache.add(url).catch(() => null)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function staleWhileRevalidate(request) {
  return caches.open(VERSION).then((cache) =>
    cache.match(request).then((cached) => {
      const network = fetch(request).then((res) => {
        if (res && (res.ok || res.type === 'opaque')) cache.put(request, res.clone());
        return res;
      }).catch(() => cached);
      return cached || network;
    })
  );
}

function networkFirst(request) {
  return caches.open(VERSION).then((cache) =>
    fetch(request).then((res) => {
      if (res && res.ok) cache.put(request, res.clone());
      return res;
    }).catch(() =>
      cache.match(request).then((cached) => cached || cache.match('./index.html'))
    )
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  if (url.origin === self.location.origin) {
    if (url.pathname.endsWith('/news.json')) return; // πάντα φρέσκο από το δίκτυο
    if (req.mode === 'navigate') {
      event.respondWith(networkFirst(req));
    } else {
      event.respondWith(staleWhileRevalidate(req));
    }
    return;
  }

  if (CDN_HOSTS.includes(url.hostname)) {
    event.respondWith(staleWhileRevalidate(req));
  }
  // Οτιδήποτε άλλο (rss2json, proxies, open-meteo, εικόνες) → κανονικά από το δίκτυο
});
