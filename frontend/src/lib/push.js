import { radarAPI } from "@/lib/api";

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

export function isPushSupported() {
  if (typeof window === "undefined") return false;
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function registerPushNotifications() {
  if (!isPushSupported()) {
    throw new Error("Browserul tău nu suportă notificări push.");
  }
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  let permission = Notification.permission;
  if (permission !== "granted") {
    permission = await Notification.requestPermission();
  }
  if (permission !== "granted") {
    throw new Error("Permisiunea pentru notificări a fost refuzată din browser.");
  }

  const keyResp = await radarAPI.getVapidKey();
  const publicKey = keyResp.data?.public_key;
  if (!publicKey) {
    throw new Error("Backend-ul nu are VAPID configurat. Setează VAPID_PUBLIC_KEY în .env.");
  }

  const existing = await reg.pushManager.getSubscription();
  if (existing) {
    await existing.unsubscribe();
  }
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  });
  const json = sub.toJSON();
  await radarAPI.pushSubscribe({
    endpoint: json.endpoint,
    p256dh: json.keys.p256dh,
    auth: json.keys.auth,
    user_agent: typeof navigator !== "undefined" ? navigator.userAgent : null,
  });
  return true;
}

export async function unregisterPushNotifications() {
  if (!isPushSupported()) return false;
  const reg = await navigator.serviceWorker.getRegistration("/sw.js");
  if (!reg) return false;
  const sub = await reg.pushManager.getSubscription();
  if (sub) {
    const endpoint = sub.endpoint;
    await sub.unsubscribe();
    try {
      await radarAPI.pushUnsubscribe(endpoint);
    } catch (e) {
      // dacă fails, oricum subscription locală a fost ștearsă
    }
  }
  return true;
}
