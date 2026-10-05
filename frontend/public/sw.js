self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

function isApiRequest(url) {
  return (
    url.pathname === '/api' ||
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/auth/v1/') ||
    url.pathname.startsWith('/rest/v1/') ||
    url.pathname.startsWith('/functions/v1/')
  );
}

function hasTokenHeaders(request) {
  return request.headers.has('authorization') || request.headers.has('cookie');
}

self.addEventListener('fetch', (event) => {
  const { request } = event;

  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);

  if (isApiRequest(url) || hasTokenHeaders(request)) {
    event.respondWith(fetch(new Request(request, { cache: 'no-store' })));
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(fetch(request));
  }
});
