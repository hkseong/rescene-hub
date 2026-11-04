const SHELL = "hub-shell-v2";
const ASSETS = ["./", "index.html", "style.css", "app.js", "config.js", "manifest.webmanifest", "icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

// 앱 셸: 네트워크 우선, 실패 시 캐시 / 데이터 JSON: 네트워크 우선, 오프라인이면 마지막 응답
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const isData = url.hostname === "raw.githubusercontent.com" && url.pathname.endsWith(".json");
  const isShell = url.origin === location.origin;
  if (!isData && !isShell) return;
  const key = isData ? url.origin + url.pathname : req;
  e.respondWith(
    fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(SHELL).then((c) => c.put(key, copy)); }
      return res;
    }).catch(() => caches.match(key))
  );
});

self.addEventListener("push", (e) => {
  let p = {};
  try { p = e.data.json(); } catch (err) { p = { title: "RESCENE HUB", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(p.title || "RESCENE HUB", {
    body: p.body || "",
    icon: "icons/icon-192.png",
    badge: "icons/badge-72.png",
    tag: p.tag,
    data: { url: p.url || "./" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = e.notification.data && e.notification.data.url || "./";
  e.waitUntil(self.clients.openWindow(url));
});
