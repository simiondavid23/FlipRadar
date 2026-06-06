/* FlipRadar Radar — Service Worker pentru notificări push.
   Înregistrat din src/lib/push.js când utilizatorul activează push în Setări. */
self.addEventListener("push", function (event) {
  if (!event.data) return;
  let data;
  try {
    data = event.data.json();
  } catch (e) {
    data = { title: "FlipRadar", body: event.data.text() };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "FlipRadar", {
      body: data.body || "",
      icon: data.icon || "/flipradar-logo.svg",
      badge: "/flipradar-logo.svg",
      data: { url: data.url || "/dashboard/radar" },
      vibrate: [200, 100, 200],
      tag: "flipradar-radar",
      renotify: true,
    })
  );
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/dashboard/radar";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clients) {
      for (const client of clients) {
        if (client.url.includes(targetUrl) && "focus" in client) {
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
