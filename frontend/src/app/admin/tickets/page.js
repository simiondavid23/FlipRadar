"use client";
import { useEffect, useState, useMemo } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { adminAPI } from "@/lib/api";
import {
  MessageSquare, ArrowLeft, Loader2, Search, User as UserIcon, X,
  ChevronRight,
} from "lucide-react";

const cardStyle = {
  backgroundColor: "var(--bg-card)",
  border: "1px solid var(--border-color)",
  borderRadius: "1rem",
  padding: "1.25rem",
};

const STATUS_OPTIONS = [
  { value: "all",         label: "Toate" },
  { value: "open",        label: "Deschise" },
  { value: "in_progress", label: "In progres" },
  { value: "closed",      label: "Inchise" },
];

const STATUS_BADGE = {
  open:        { bg: "rgba(250,204,21,0.15)", color: "#facc15", label: "Deschis" },
  in_progress: { bg: "rgba(59,130,246,0.15)", color: "#60a5fa", label: "In progres" },
  closed:      { bg: "rgba(34,197,94,0.15)",  color: "#4ade80", label: "Inchis" },
};

export default function AdminTicketsListPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const userId = searchParams.get("user");
  const status = searchParams.get("status") || "all";

  const [tickets, setTickets] = useState([]);
  const [userInfo, setUserInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const params = {};
        if (userId) params.user_id = Number(userId);
        if (status && status !== "all") params.status = status;
        const [ticketsRes, userRes] = await Promise.all([
          adminAPI.getTickets(params),
          userId ? adminAPI.getUser(userId).catch(() => null) : Promise.resolve(null),
        ]);
        if (!cancelled) {
          setTickets(ticketsRes.data);
          setUserInfo(userRes?.data || null);
        }
      } catch (e) {
        if (!cancelled) setError(e.response?.data?.detail || "Eroare la incarcare.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [userId, status]);

  const filtered = useMemo(() => {
    if (!search.trim()) return tickets;
    const q = search.toLowerCase();
    return tickets.filter((t) => {
      const subject = (t.subject || "").toLowerCase();
      const email = (t.user?.email || "").toLowerCase();
      const name = (t.user?.full_name || t.user?.username || "").toLowerCase();
      return subject.includes(q) || email.includes(q) || name.includes(q);
    });
  }, [tickets, search]);

  const setStatus = (next) => {
    const p = new URLSearchParams(searchParams.toString());
    if (next === "all") p.delete("status"); else p.set("status", next);
    router.replace(`${pathname}?${p.toString()}`);
  };

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.625rem", borderRadius: "0.75rem", backgroundColor: "#dc2626", display: "flex" }}>
            <MessageSquare style={{ width: 22, height: 22, color: "var(--text-primary)" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
              {userInfo ? `Tickete - ${userInfo.full_name || userInfo.username}` : "Tickete suport"}
            </h1>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>
              {userInfo ? userInfo.email : "Istoric complet tickete de suport"}
            </p>
          </div>
        </div>
        <Link href="/admin" style={{
          display: "flex", alignItems: "center", gap: "0.375rem",
          padding: "0.5rem 1rem", borderRadius: "0.5rem",
          border: "1px solid var(--border-color)", textDecoration: "none",
          fontSize: "0.8125rem", color: "var(--text-secondary)",
        }}>
          <ArrowLeft style={{ width: 14, height: 14 }} />
          Inapoi la pagina principala
        </Link>
      </div>

      {userId && (
        <div style={{
          ...cardStyle,
          marginBottom: "1rem",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexWrap: "wrap", gap: "0.5rem",
          borderColor: "#2563eb", backgroundColor: "rgba(37,99,235,0.08)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "#93c5fd", fontSize: "0.8125rem" }}>
            <UserIcon style={{ width: 16, height: 16 }} />
            Istoric complet - toate ticketele acestui utilizator (indiferent de status)
          </div>
          <Link
            href={`/admin/tickets${status && status !== "all" ? `?status=${status}` : ""}`}
            style={{
              display: "flex", alignItems: "center", gap: "0.375rem",
              padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
              backgroundColor: "rgba(255,255,255,0.06)", textDecoration: "none",
              fontSize: "0.75rem", color: "var(--text-secondary)",
            }}>
            <X style={{ width: 12, height: 12 }} /> Vezi toate ticketele
          </Link>
        </div>
      )}

      {/* Status pills */}
      <div style={{ ...cardStyle, marginBottom: "1rem", display: "flex", flexWrap: "wrap", gap: "0.375rem", alignItems: "center" }}>
        <span style={{ color: "var(--text-secondary)", fontSize: "0.75rem", marginRight: "0.5rem" }}>Status:</span>
        {STATUS_OPTIONS.map((opt) => {
          const active = status === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => setStatus(opt.value)}
              style={{
                padding: "0.375rem 0.75rem",
                borderRadius: "0.375rem",
                border: `1px solid ${active ? "#2563eb" : "var(--border-color)"}`,
                backgroundColor: active ? "rgba(37,99,235,0.2)" : "transparent",
                color: active ? "white" : "var(--text-secondary)",
                fontSize: "0.75rem",
                cursor: "pointer",
                fontWeight: active ? 600 : 400,
              }}
            >
              {opt.label}
            </button>
          );
        })}
        <div style={{ flex: 1 }} />
        <div style={{ position: "relative", minWidth: "200px", flex: "0 1 300px" }}>
          <Search style={{ width: 14, height: 14, color: "var(--text-muted)", position: "absolute", left: "0.625rem", top: "0.5rem" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cauta subiect sau utilizator..."
            style={{
              width: "100%",
              padding: "0.4rem 0.625rem 0.4rem 2rem",
              borderRadius: "0.375rem",
              backgroundColor: "var(--bg-dark)",
              border: "1px solid var(--border-color)",
              color: "var(--text-primary)",
              fontSize: "0.75rem",
              outline: "none",
            }}
          />
        </div>
      </div>

      <div style={cardStyle}>
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
            <Loader2 style={{ width: 28, height: 28, color: "#60a5fa", animation: "spin 1s linear infinite" }} />
          </div>
        ) : error ? (
          <p style={{ color: "#fca5a5", fontSize: "0.875rem", textAlign: "center", padding: "2rem 0" }}>{error}</p>
        ) : filtered.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", textAlign: "center", padding: "2rem 0" }}>
            Niciun ticket gasit.
          </p>
        ) : (
          <>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.75rem", margin: "0 0 0.75rem" }}>
              {filtered.length} ticket{filtered.length === 1 ? "" : "e"} {search ? "(filtrate)" : ""}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {filtered.map((t) => {
                const badge = STATUS_BADGE[t.status] || STATUS_BADGE.open;
                return (
                  <Link key={t.id} href={`/admin/tickets/${t.id}`}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "0.75rem 1rem", borderRadius: "0.625rem",
                      border: "1px solid var(--border-color)", textDecoration: "none",
                      transition: "background-color 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem", flexWrap: "wrap" }}>
                        <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>{t.subject}</span>
                        <span style={{
                          padding: "0.125rem 0.5rem", borderRadius: "0.25rem",
                          fontSize: "0.6875rem", fontWeight: 600,
                          backgroundColor: badge.bg, color: badge.color,
                        }}>{badge.label}</span>
                      </div>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        {t.user.full_name || t.user.username} • {t.user.email} • {t.message_count} mesaje • creat {new Date(t.created_at).toLocaleDateString("ro-RO")}
                      </span>
                    </div>
                    <ChevronRight style={{ width: 16, height: 16, color: "var(--text-muted)", flexShrink: 0 }} />
                  </Link>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
