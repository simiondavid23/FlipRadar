"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { notificationsAPI } from "@/lib/api";
import { Bell, CheckCheck, Trash2, Info, AlertTriangle, CheckCircle, BellOff, Users, ChevronRight } from "lucide-react";

const PAGE_SIZE = 50;

const typeIcons = {
  info: { icon: Info, color: "#3b82f6" },
  alert: { icon: AlertTriangle, color: "#f59e0b" },
  success: { icon: CheckCircle, color: "#22c55e" },
  warning: { icon: AlertTriangle, color: "#ef4444" },
  facebook_group: { icon: Users, color: "#3b82f6" },
};

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const router = useRouter();

  useEffect(() => {
    loadNotifications(true);
    loadUnread();
  }, []);

  const loadUnread = async () => {
    try {
      const res = await notificationsAPI.getUnreadCount();
      setUnreadCount(res.data.unread_count ?? 0);
    } catch (e) { console.error(e); }
  };

  // reset -> inlocuieste lista (skip 0); altfel apenduieste transa urmatoare.
  const loadNotifications = async (reset = false) => {
    const skip = reset ? 0 : notifications.length;
    if (reset) setLoading(true); else setLoadingMore(true);
    try {
      const res = await notificationsAPI.getNotifications({ skip, limit: PAGE_SIZE });
      const batch = res.data || [];
      setNotifications((prev) => (reset ? batch : [...prev, ...batch]));
      setHasMore(batch.length === PAGE_SIZE);
    } catch (e) { console.error(e); }
    finally { if (reset) setLoading(false); else setLoadingMore(false); }
  };

  const markAsRead = async (id) => {
    try {
      await notificationsAPI.markAsRead(id);
      setNotifications((prev) => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
      loadUnread();
    } catch (e) { console.error(e); }
  };

  const markAllAsRead = async () => {
    try {
      await notificationsAPI.markAllAsRead();
      setNotifications((prev) => prev.map(n => ({ ...n, is_read: true })));
      loadUnread();
    } catch (e) { console.error(e); }
  };

  const clearAll = async () => {
    if (!confirm("Esti sigur ca vrei sa stergi toate notificarile?")) return;
    try {
      await notificationsAPI.clearAll();
      setNotifications([]);
      setHasMore(false);
      loadUnread();
    } catch (e) { console.error(e); }
  };

  // Click: marcheaza citit daca e necitita; navigheaza daca exista link (si pe cele deja citite).
  const handleClick = (notif) => {
    if (!notif.is_read) markAsRead(notif.id);
    if (notif.link) router.push(notif.link);
  };

  const cardStyle = { backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)" };

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "4px solid #3b82f6", borderTop: "4px solid transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem" }}>
        <div>
          <h1 style={{ fontSize: "1.875rem", fontWeight: 700, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <Bell style={{ width: "2rem", height: "2rem", color: "#fbbf24" }} />
            Notificari
            {unreadCount > 0 && (
              <span style={{ fontSize: "0.875rem", padding: "0.125rem 0.625rem", borderRadius: "9999px",
                backgroundColor: "#dc2626", color: "var(--text-primary)" }}>{unreadCount}</span>
            )}
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>{notifications.length} incarcate · {unreadCount} necitite</p>
        </div>
        {notifications.length > 0 && (
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button onClick={markAllAsRead}
              style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 1rem", borderRadius: "0.5rem",
                fontSize: "0.875rem", cursor: "pointer", border: "1px solid var(--border-color)", backgroundColor: "transparent", color: "var(--text-secondary)" }}>
              <CheckCheck style={{ width: "1rem", height: "1rem" }} /> Citeste toate
            </button>
            <button onClick={clearAll}
              style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 1rem", borderRadius: "0.5rem",
                fontSize: "0.875rem", cursor: "pointer", border: "1px solid var(--border-color)", backgroundColor: "transparent", color: "#f87171" }}>
              <Trash2 style={{ width: "1rem", height: "1rem" }} /> Sterge toate
            </button>
          </div>
        )}
      </div>

      {notifications.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {notifications.map((notif) => {
            const typeInfo = typeIcons[notif.notification_type] || typeIcons.info;
            const Icon = typeInfo.icon;
            // FlipRadar — ITEM 16: notificarile Flash Deal au accent portocaliu + eticheta.
            const isFlashDeal = notif.notification_type === "flash_deal";
            const accentColor = isFlashDeal ? "#fb923c" : typeInfo.color;
            return (
              <div key={notif.id} onClick={() => handleClick(notif)}
                style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1rem 1.25rem", cursor: notif.link ? "pointer" : "default",
                  opacity: notif.is_read ? 0.6 : 1, borderLeft: `3px solid ${accentColor}`, position: "relative" }}>
                {isFlashDeal && (
                  <span style={{
                    position: "absolute", top: "0.75rem", right: "1rem",
                    fontWeight: 700, fontSize: "0.7rem", color: "#fb923c", letterSpacing: "0.04em",
                  }}>
                    FLASH DEAL
                  </span>
                )}
                <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
                  <Icon style={{ width: "1.25rem", height: "1.25rem", color: accentColor, flexShrink: 0, marginTop: "0.125rem" }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <h3 style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>{notif.title}</h3>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginRight: isFlashDeal ? "5.5rem" : 0 }}>
                        {new Date(notif.created_at).toLocaleDateString("ro-RO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginTop: "0.25rem" }}>{notif.message}</p>
                  </div>
                  {!notif.is_read && (
                    <div style={{ width: "0.5rem", height: "0.5rem", borderRadius: "50%", backgroundColor: "#3b82f6", flexShrink: 0, marginTop: "0.375rem" }} />
                  )}
                  {notif.link && (
                    <ChevronRight style={{ width: "1rem", height: "1rem", color: "var(--text-secondary)", flexShrink: 0, marginTop: "0.25rem" }} />
                  )}
                </div>
              </div>
            );
          })}
          {hasMore && (
            <button onClick={() => loadNotifications(false)} disabled={loadingMore}
              style={{ alignSelf: "center", marginTop: "0.25rem", padding: "0.625rem 1.25rem", borderRadius: "0.5rem",
                fontSize: "0.875rem", border: "1px solid var(--border-color)", backgroundColor: "transparent",
                color: "var(--text-secondary)", cursor: loadingMore ? "default" : "pointer", opacity: loadingMore ? 0.6 : 1 }}>
              {loadingMore ? "Se incarca..." : "Incarca mai multe"}
            </button>
          )}
        </div>
      ) : (
        <div style={{ ...cardStyle, borderRadius: "1rem", padding: "3rem", textAlign: "center" }}>
          <BellOff style={{ width: "4rem", height: "4rem", margin: "0 auto 1rem", color: "var(--text-secondary)" }} />
          <p style={{ fontSize: "1.125rem", color: "var(--text-primary)", marginBottom: "0.5rem" }}>Nu ai notificari</p>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>Notificarile vor aparea aici cand se declanseaza alerte sau apar update-uri.</p>
        </div>
      )}
    </div>
  );
}
