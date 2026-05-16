"use client";
import { useEffect, useState, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { adminAPI } from "@/lib/api";
import {
  MessageCircle, ArrowLeft, Loader2, Search, User as UserIcon,
  X, Bot, Flag,
} from "lucide-react";

const cardStyle = {
  backgroundColor: "var(--bg-card)",
  border: "1px solid var(--border-color)",
  borderRadius: "1rem",
  padding: "1.25rem",
};

const ROLE_TABS = [
  { key: "all",       label: "Toate",     color: "var(--text-muted)" },
  { key: "user",      label: "Utilizator", color: "#2563eb" },
  { key: "assistant", label: "Asistent AI", color: "#9333ea" },
];

const PREVIEW_CHARS = 180;

export default function AdminChatMessagesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const userId = searchParams.get("user");
  const roleParam = searchParams.get("role");
  const role = ROLE_TABS.some((t) => t.key === roleParam) ? roleParam : "all";

  const [messages, setMessages] = useState([]);
  const [userInfo, setUserInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(() => new Set());

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const params = { role };
        if (userId) params.user_id = Number(userId);
        const [msgRes, userRes] = await Promise.all([
          adminAPI.getChatMessages(params),
          userId ? adminAPI.getUser(userId).catch(() => null) : Promise.resolve(null),
        ]);
        if (!cancelled) {
          setMessages(msgRes.data);
          setUserInfo(userRes?.data || null);
          setExpanded(new Set());
        }
      } catch (e) {
        if (!cancelled) setError(e.response?.data?.detail || "Eroare la incarcare.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [userId, role]);

  const setRole = (nextRole) => {
    const qs = new URLSearchParams();
    if (userId) qs.set("user", userId);
    if (nextRole !== "all") qs.set("role", nextRole);
    const query = qs.toString();
    router.push(query ? `/admin/chat-messages?${query}` : "/admin/chat-messages", { scroll: false });
  };

  const toggleExpanded = (id) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return messages;
    const q = search.toLowerCase();
    return messages.filter((m) => {
      const content = (m.content || "").toLowerCase();
      const ownerEmail = (m.owner?.email || "").toLowerCase();
      const ownerName = (m.owner?.full_name || m.owner?.username || "").toLowerCase();
      return content.includes(q) || ownerEmail.includes(q) || ownerName.includes(q);
    });
  }, [messages, search]);

  const flaggedCount = useMemo(
    () => filtered.filter((m) => m.needs_staff).length,
    [filtered]
  );

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.625rem", borderRadius: "0.75rem", backgroundColor: "#2563eb", display: "flex" }}>
            <MessageCircle style={{ width: 22, height: 22, color: "var(--text-primary)" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
              {userInfo ? `Mesaje AI - ${userInfo.full_name || userInfo.username}` : "Mesaje AI"}
            </h1>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>
              {userInfo ? userInfo.email : "Istoricul conversatiilor cu asistentul AI"}
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
            Lista filtrata pentru utilizatorul curent
          </div>
          <Link
            href={role === "all" ? "/admin/chat-messages" : `/admin/chat-messages?role=${role}`}
            style={{
              display: "flex", alignItems: "center", gap: "0.375rem",
              padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
              backgroundColor: "rgba(255,255,255,0.06)", textDecoration: "none",
              fontSize: "0.75rem", color: "var(--text-secondary)",
            }}
          >
            <X style={{ width: 12, height: 12 }} /> Vezi toti utilizatorii
          </Link>
        </div>
      )}

      {/* Role tabs */}
      <div style={{ ...cardStyle, marginBottom: "1rem", padding: "0.5rem" }}>
        <div style={{ display: "flex", gap: "0.25rem" }}>
          {ROLE_TABS.map((t) => {
            const active = t.key === role;
            return (
              <button
                key={t.key}
                onClick={() => setRole(t.key)}
                style={{
                  flex: 1,
                  padding: "0.625rem 1rem",
                  borderRadius: "0.5rem",
                  border: "1px solid " + (active ? t.color : "transparent"),
                  backgroundColor: active ? `${t.color}22` : "transparent",
                  color: active ? "white" : "var(--text-secondary)",
                  fontSize: "0.8125rem",
                  fontWeight: active ? 600 : 400,
                  cursor: "pointer",
                  transition: "all 0.12s ease",
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ ...cardStyle, marginBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", position: "relative" }}>
          <Search style={{ width: 16, height: 16, color: "var(--text-muted)", position: "absolute", left: "0.75rem" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cauta in continutul mesajelor sau dupa utilizator..."
            style={{
              width: "100%",
              padding: "0.625rem 0.75rem 0.625rem 2.25rem",
              borderRadius: "0.5rem",
              backgroundColor: "var(--bg-dark)",
              border: "1px solid var(--border-color)",
              color: "var(--text-primary)",
              fontSize: "0.8125rem",
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
            Niciun mesaj in aceasta categorie.
          </p>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.75rem", margin: 0 }}>
                {filtered.length} mesaj{filtered.length === 1 ? "" : "e"} {search ? "(filtrate)" : "in total"}
              </p>
              {flaggedCount > 0 && (
                <p style={{ color: "#fbbf24", fontSize: "0.75rem", margin: 0, display: "flex", alignItems: "center", gap: "0.25rem" }}>
                  <Flag style={{ width: 12, height: 12 }} />
                  {flaggedCount} semnalat{flaggedCount === 1 ? "" : "e"} spre atentie
                </p>
              )}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {filtered.map((m) => {
                const isUser = m.role === "user";
                const isFlagged = m.needs_staff;
                const isExpanded = expanded.has(m.id);
                const needsToggle = (m.content || "").length > PREVIEW_CHARS;
                const displayContent = isExpanded || !needsToggle
                  ? m.content
                  : m.content.slice(0, PREVIEW_CHARS) + "...";
                const accentColor = isUser ? "#2563eb" : "#9333ea";
                const RoleIcon = isUser ? UserIcon : Bot;
                return (
                  <div
                    key={m.id}
                    style={{
                      border: "1px solid " + (isFlagged ? "#b45309" : "var(--border-color)"),
                      borderRadius: "0.625rem",
                      padding: "0.75rem 0.875rem",
                      backgroundColor: isFlagged ? "rgba(180,83,9,0.08)" : "rgba(255,255,255,0.02)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
                      <span style={{
                        display: "inline-flex", alignItems: "center", gap: "0.25rem",
                        padding: "0.125rem 0.5rem", borderRadius: "0.375rem",
                        fontSize: "0.6875rem", fontWeight: 600,
                        backgroundColor: `${accentColor}22`, color: accentColor,
                      }}>
                        <RoleIcon style={{ width: 10, height: 10 }} />
                        {isUser ? "Utilizator" : "Asistent"}
                      </span>
                      {!userId && m.owner && (
                        <Link href={`/admin/chat-messages?user=${m.owner.id}${role !== "all" ? `&role=${role}` : ""}`} style={{
                          color: "#93c5fd", textDecoration: "none", fontSize: "0.75rem",
                        }}>
                          {m.owner.full_name || m.owner.username}
                        </Link>
                      )}
                      {isFlagged && (
                        <span style={{
                          display: "inline-flex", alignItems: "center", gap: "0.25rem",
                          padding: "0.125rem 0.5rem", borderRadius: "0.375rem",
                          fontSize: "0.6875rem", fontWeight: 600,
                          backgroundColor: "rgba(251,191,36,0.15)", color: "#fbbf24",
                        }}>
                          <Flag style={{ width: 10, height: 10 }} />
                          Semnalat
                        </span>
                      )}
                      <span style={{ color: "var(--text-muted)", fontSize: "0.6875rem", marginLeft: "auto" }}>
                        {m.created_at ? new Date(m.created_at).toLocaleString("ro-RO") : "-"}
                      </span>
                    </div>
                    <p style={{
                      margin: 0, color: "var(--text-primary)", fontSize: "0.8125rem",
                      lineHeight: 1.5, whiteSpace: "pre-wrap", wordBreak: "break-word",
                    }}>
                      {displayContent}
                    </p>
                    {needsToggle && (
                      <button
                        onClick={() => toggleExpanded(m.id)}
                        style={{
                          marginTop: "0.5rem",
                          padding: 0,
                          background: "transparent",
                          border: "none",
                          color: "#60a5fa",
                          fontSize: "0.75rem",
                          cursor: "pointer",
                        }}
                      >
                        {isExpanded ? "Ascunde" : "Afiseaza tot"}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
