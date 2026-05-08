"use client";
import { useState, useEffect, useMemo } from "react";
import { useAuth } from "@/lib/auth";
import { adminAPI } from "@/lib/api";
import Link from "next/link";
import {
  Users, Package, Eye, Bell, MessageSquare, Shield, LogOut,
  Clock, ChevronRight, Search,
} from "lucide-react";

function StatCard({ title, value, icon: Icon, color, subtitle, href }) {
  const inner = (
    <>
      <div style={{ position: "absolute", top: "-2rem", right: "-2rem", width: "6rem", height: "6rem", borderRadius: "50%", opacity: 0.12, background: color }} />
      <div style={{ position: "relative", zIndex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.75rem" }}>
          <div style={{ padding: "0.4rem", borderRadius: "0.5rem", backgroundColor: color, display: "flex" }}>
            <Icon style={{ width: "16px", height: "16px", color: "white" }} />
          </div>
          <span style={{ fontSize: "0.8125rem", color: "#94a3b8" }}>{title}</span>
        </div>
        <p style={{ fontSize: "1.75rem", fontWeight: 700, color: "white", margin: 0, lineHeight: 1 }}>{value}</p>
        {subtitle && <p style={{ fontSize: "0.6875rem", color: "#64748b", margin: "0.375rem 0 0" }}>{subtitle}</p>}
      </div>
    </>
  );

  const baseStyle = {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border-color)",
    borderRadius: "1rem",
    padding: "1.25rem",
    position: "relative",
    overflow: "hidden",
  };

  if (!href) {
    return <div style={baseStyle}>{inner}</div>;
  }

  return (
    <Link
      href={href}
      style={{
        ...baseStyle,
        display: "block",
        textDecoration: "none",
        color: "inherit",
        cursor: "pointer",
        transition: "border-color 0.15s ease, transform 0.15s ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = color;
        e.currentTarget.style.transform = "translateY(-1px)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--border-color)";
        e.currentTarget.style.transform = "translateY(0)";
      }}
    >
      {inner}
    </Link>
  );
}

export default function AdminDashboard() {
  const { logout } = useAuth();
  const [stats, setStats] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ticketSearch, setTicketSearch] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, ticketsRes] = await Promise.all([
        adminAPI.getStats(),
        adminAPI.getTickets(),
      ]);
      setStats(statsRes.data);
      setTickets(ticketsRes.data);
    } catch (error) {
      console.error("Error loading admin data:", error);
    } finally {
      setLoading(false);
    }
  };

  const visibleTickets = useMemo(() => {
    const openish = tickets.filter((t) => t.status !== "closed");
    const q = ticketSearch.trim().toLowerCase();
    if (!q) return openish;
    return openish.filter((t) => {
      const subject = (t.subject || "").toLowerCase();
      const email = (t.user?.email || "").toLowerCase();
      const name = (t.user?.full_name || t.user?.username || "").toLowerCase();
      return subject.includes(q) || email.includes(q) || name.includes(q);
    });
  }, [tickets, ticketSearch]);

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "4px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  const cardStyle = {
    backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
    borderRadius: "1rem", padding: "1.5rem",
  };

  const getStatusBadge = (status) => {
    const map = {
      open: { bg: "rgba(250,204,21,0.15)", color: "#facc15", label: "Deschis" },
      in_progress: { bg: "rgba(59,130,246,0.15)", color: "#60a5fa", label: "In progres" },
      closed: { bg: "rgba(34,197,94,0.15)", color: "#4ade80", label: "Inchis" },
    };
    const s = map[status] || map.open;
    return (
      <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: s.bg, color: s.color }}>
        {s.label}
      </span>
    );
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "2rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.625rem", borderRadius: "0.75rem", backgroundColor: "#dc2626", display: "flex" }}>
            <Shield style={{ width: "22px", height: "22px", color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>Admin Dashboard</h1>
            <p style={{ fontSize: "0.8125rem", color: "#94a3b8", margin: 0 }}>Panou de administrare FlipRadar</p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Link href="/admin/users" style={{
            display: "flex", alignItems: "center", gap: "0.375rem",
            padding: "0.5rem 1rem", borderRadius: "0.5rem",
            backgroundColor: "#2563eb", border: "1px solid #2563eb",
            color: "white", textDecoration: "none", fontSize: "0.8125rem", fontWeight: 500,
            transition: "all 0.15s ease",
          }}>
            <Users style={{ width: "14px", height: "14px" }} /> Gestionare Utilizatori
          </Link>
          <button onClick={logout} style={{
            display: "flex", alignItems: "center", gap: "0.375rem",
            padding: "0.5rem 1rem", borderRadius: "0.5rem",
            backgroundColor: "transparent", border: "1px solid var(--border-color)",
            color: "#f87171", cursor: "pointer", fontSize: "0.8125rem",
          }}>
            <LogOut style={{ width: "14px", height: "14px" }} /> Deconectare
          </button>
        </div>
      </div>

      {/* Stats Grid (row 1) — every tile links into the matching list page */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <StatCard title="Utilizatori totali" value={stats?.total_users || 0} icon={Users} color="#2563eb" subtitle="Conturi inregistrate" href="/admin/users" />
        <StatCard title="Utilizatori activi" value={stats?.active_users || 0} icon={Users} color="#16a34a" subtitle="Conturi active" href="/admin/users" />
        <StatCard title="Produse" value={stats?.total_products || 0} icon={Package} color="#9333ea" subtitle="In baza de date" href="/admin/products" />
        <StatCard title="Tickete deschise" value={stats?.open_tickets || 0} icon={MessageSquare} color="#dc2626" subtitle={`${stats?.total_tickets || 0} total`} href="/admin/tickets?status=open" />
      </div>

      {/* Stats Grid (row 2) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <StatCard title="Watchlist total" value={stats?.total_watchlist || 0} icon={Eye} color="#ca8a04" href="/admin/watchlist" />
        <StatCard title="Alerte totale" value={stats?.total_alerts || 0} icon={Bell} color="#0891b2" href="/admin/alerts" />
        <StatCard title="Alerte active" value={stats?.active_alerts || 0} icon={Bell} color="#16a34a" href="/admin/alerts?status=active" />
        <StatCard title="Tickete in progres" value={stats?.in_progress_tickets || 0} icon={Clock} color="#f97316" href="/admin/tickets?status=in_progress" />
      </div>

      {/* Two columns: Tickets + Users */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: "1rem" }}>
        {/* Support Tickets — open + in_progress only, with user search */}
        <div style={cardStyle}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem", gap: "0.75rem", flexWrap: "wrap" }}>
            <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "white", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <MessageSquare style={{ width: "16px", height: "16px", color: "#60a5fa" }} /> Tickete Suport
              <span style={{ fontSize: "0.6875rem", color: "#64748b", fontWeight: 400 }}>(deschise si in progres)</span>
            </h2>
            <div style={{ position: "relative", flex: "0 1 220px", minWidth: "160px" }}>
              <Search style={{ width: 14, height: 14, color: "#64748b", position: "absolute", left: "0.625rem", top: "0.5rem" }} />
              <input
                type="text"
                value={ticketSearch}
                onChange={(e) => setTicketSearch(e.target.value)}
                placeholder="Cauta utilizator sau subiect..."
                style={{
                  width: "100%",
                  padding: "0.4rem 0.625rem 0.4rem 2rem",
                  borderRadius: "0.375rem",
                  backgroundColor: "#0f172a",
                  border: "1px solid var(--border-color)",
                  color: "white",
                  fontSize: "0.75rem",
                  outline: "none",
                }}
              />
            </div>
          </div>
          {visibleTickets.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {visibleTickets.slice(0, 8).map((ticket) => (
                <Link key={ticket.id} href={`/admin/tickets/${ticket.id}`}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "0.75rem", borderRadius: "0.625rem",
                    border: "1px solid var(--border-color)", textDecoration: "none",
                    transition: "all 0.15s ease",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem", flexWrap: "wrap" }}>
                      <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "white" }}>{ticket.subject}</span>
                      {getStatusBadge(ticket.status)}
                    </div>
                    <span style={{ fontSize: "0.6875rem", color: "#64748b" }}>
                      {ticket.user.full_name || ticket.user.username} • {ticket.user.email} • {ticket.message_count} mesaje • {new Date(ticket.created_at).toLocaleDateString("ro-RO")}
                    </span>
                  </div>
                  <ChevronRight style={{ width: "16px", height: "16px", color: "#64748b", flexShrink: 0 }} />
                </Link>
              ))}
              {visibleTickets.length > 8 && (
                <p style={{ color: "#64748b", fontSize: "0.75rem", textAlign: "center", margin: "0.25rem 0 0" }}>
                  ...si inca {visibleTickets.length - 8}. Deschide <Link href="/admin/tickets" style={{ color: "#60a5fa", textDecoration: "none" }}>lista completa</Link>.
                </p>
              )}
            </div>
          ) : (
            <p style={{ color: "#64748b", fontSize: "0.8125rem", textAlign: "center", padding: "2rem 0" }}>
              {ticketSearch ? "Niciun ticket gasit pentru cautarea curenta." : "Nu exista tickete deschise sau in progres."}
            </p>
          )}
        </div>

        {/* Recent Users */}
        <div style={cardStyle}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
            <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "white", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Users style={{ width: "16px", height: "16px", color: "#4ade80" }} /> Utilizatori recenti
            </h2>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {stats?.recent_users?.slice(0, 8).map((u) => (
              <Link key={u.id} href={`/admin/users?user=${u.id}`} style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "0.625rem", borderRadius: "0.5rem",
                border: "1px solid var(--border-color)",
                textDecoration: "none",
                transition: "background-color 0.15s ease",
              }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
              >
                <div style={{ minWidth: 0 }}>
                  <p style={{ fontSize: "0.8125rem", fontWeight: 500, color: "white", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {u.full_name || u.username}
                  </p>
                  <p style={{ fontSize: "0.6875rem", color: "#64748b", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.email}</p>
                </div>
                <span style={{ fontSize: "0.6875rem", color: "#64748b", flexShrink: 0, marginLeft: "0.5rem" }}>
                  {u.created_at ? new Date(u.created_at).toLocaleDateString("ro-RO") : ""}
                </span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
