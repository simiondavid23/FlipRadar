"use client";
import { useState, useEffect, useMemo } from "react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { adminAPI } from "@/lib/api";
import Link from "next/link";
import {
  Users, Package, Eye, Bell, MessageSquare, Shield, LogOut,
  Clock, ChevronRight, Search, FileBarChart, ChevronLeft,
  Sun, Moon,
} from "lucide-react";

function StatCard({ title, value, icon: Icon, color, subtitle, href }) {
  const inner = (
    <>
      <div style={{ position: "absolute", top: "-2rem", right: "-2rem", width: "6rem", height: "6rem", borderRadius: "50%", opacity: 0.12, background: color }} />
      <div style={{ position: "relative", zIndex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.75rem" }}>
          <div style={{ padding: "0.4rem", borderRadius: "0.5rem", backgroundColor: color, display: "flex" }}>
            <Icon style={{ width: "16px", height: "16px", color: "var(--text-primary)" }} />
          </div>
          <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{title}</span>
        </div>
        <p style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, lineHeight: 1 }}>{value}</p>
        {subtitle && <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", margin: "0.375rem 0 0" }}>{subtitle}</p>}
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
  const { theme, toggleTheme } = useTheme();
  const [stats, setStats] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ticketSearch, setTicketSearch] = useState("");

  // Products report state
  const [reportFilters, setReportFilters] = useState({
    price_min: "", price_max: "", date_from: "", date_to: "", category: "",
  });
  const [reportData, setReportData] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState("");
  const [reportPage, setReportPage] = useState(1);
  const [exportLoading, setExportLoading] = useState(false); // FlipRadar — ITEM 17
  const PAGE_SIZE = 25;

  // FlipRadar — ITEM 17: construieste parametrii de filtrare activi (comuni cu raportul).
  const buildReportParams = () => {
    const params = {};
    if (reportFilters.price_min !== "") params.price_min = parseFloat(reportFilters.price_min);
    if (reportFilters.price_max !== "") params.price_max = parseFloat(reportFilters.price_max);
    if (reportFilters.date_from) params.date_from = reportFilters.date_from;
    if (reportFilters.date_to) params.date_to = reportFilters.date_to;
    if (reportFilters.category) params.category = reportFilters.category;
    return params;
  };

  // FlipRadar — ITEM 17: descarca raportul ca PDF cu aceiasi parametri de filtrare.
  const exportReportPdf = async () => {
    setExportLoading(true);
    setReportError("");
    try {
      const res = await adminAPI.exportProductsReportPdf(buildReportParams());
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `raport_admin_${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      setReportError("Nu am putut exporta PDF-ul. Incearca din nou.");
    } finally {
      setExportLoading(false);
    }
  };

  const generateReport = async () => {
    setReportLoading(true);
    setReportError("");
    try {
      const res = await adminAPI.getProductsReport(buildReportParams());
      setReportData(res.data);
      setReportPage(1);
    } catch (e) {
      console.error(e);
      setReportError("Nu am putut genera raportul. Verifica filtrele si incearca din nou.");
    } finally {
      setReportLoading(false);
    }
  };

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
            <Shield style={{ width: "22px", height: "22px", color: "var(--text-primary)" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Panou Administrare</h1>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>Panou de administrare FlipRadar</p>
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
          <button onClick={toggleTheme}
            title={theme === "light" ? "Comuta la tema intunecata" : "Comuta la tema luminoasa"}
            style={{
              display: "flex", alignItems: "center", gap: "0.5rem",
              padding: "0.5rem 1rem", borderRadius: "0.5rem",
              border: "1px solid var(--border-color)",
              backgroundColor: "var(--bg-card)", color: "var(--text-secondary)",
              cursor: "pointer", fontSize: "0.8125rem",
            }}>
            {theme === "light" ? (
              <><Moon style={{ width: "14px", height: "14px" }} /> Tema intunecata</>
            ) : (
              <><Sun style={{ width: "14px", height: "14px" }} /> Tema luminoasa</>
            )}
          </button>
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

      {/* Grilă statistici (rândul 1) — fiecare tile face link la pagina de listă corespunzătoare */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <StatCard title="Utilizatori totali" value={stats?.total_users || 0} icon={Users} color="#2563eb" subtitle="Conturi inregistrate" href="/admin/users" />
        <StatCard title="Utilizatori activi" value={stats?.active_users || 0} icon={Users} color="#16a34a" subtitle="Conturi active" href="/admin/users" />
        <StatCard title="Produse" value={stats?.total_products || 0} icon={Package} color="#9333ea" subtitle="In baza de date" href="/admin/products" />
        <StatCard title="Tickete deschise" value={stats?.open_tickets || 0} icon={MessageSquare} color="#dc2626" subtitle={`${stats?.total_tickets || 0} total`} href="/admin/tickets?status=open" />
      </div>

      {/* Grilă statistici (rândul 2) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <StatCard title="Watchlist total" value={stats?.total_watchlist || 0} icon={Eye} color="#ca8a04" href="/admin/watchlist" />
        <StatCard title="Alerte totale" value={stats?.total_alerts || 0} icon={Bell} color="#0891b2" href="/admin/alerts" />
        <StatCard title="Alerte active" value={stats?.active_alerts || 0} icon={Bell} color="#16a34a" href="/admin/alerts?status=active" />
        <StatCard title="Tickete in progres" value={stats?.in_progress_tickets || 0} icon={Clock} color="#f97316" href="/admin/tickets?status=in_progress" />
      </div>

      {/* Două coloane: Tickete + Utilizatori */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: "1rem" }}>
        {/* Tickete Suport — doar deschise + în progres, cu căutare utilizator */}
        <div style={cardStyle}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem", gap: "0.75rem", flexWrap: "wrap" }}>
            <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <MessageSquare style={{ width: "16px", height: "16px", color: "#60a5fa" }} /> Tickete Suport
              <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", fontWeight: 400 }}>(deschise si in progres)</span>
            </h2>
            <div style={{ position: "relative", flex: "0 1 220px", minWidth: "160px" }}>
              <Search style={{ width: 14, height: 14, color: "var(--text-muted)", position: "absolute", left: "0.625rem", top: "0.5rem" }} />
              <input
                type="text"
                value={ticketSearch}
                onChange={(e) => setTicketSearch(e.target.value)}
                placeholder="Cauta utilizator sau subiect..."
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
                      <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>{ticket.subject}</span>
                      {getStatusBadge(ticket.status)}
                    </div>
                    <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>
                      {ticket.user.full_name || ticket.user.username} • {ticket.user.email} • {ticket.message_count} mesaje • {new Date(ticket.created_at).toLocaleDateString("ro-RO")}
                    </span>
                  </div>
                  <ChevronRight style={{ width: "16px", height: "16px", color: "var(--text-muted)", flexShrink: 0 }} />
                </Link>
              ))}
              {visibleTickets.length > 8 && (
                <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", textAlign: "center", margin: "0.25rem 0 0" }}>
                  ...si inca {visibleTickets.length - 8}. Deschide <Link href="/admin/tickets" style={{ color: "#60a5fa", textDecoration: "none" }}>lista completa</Link>.
                </p>
              )}
            </div>
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem", textAlign: "center", padding: "2rem 0" }}>
              {ticketSearch ? "Niciun ticket gasit pentru cautarea curenta." : "Nu exista tickete deschise sau in progres."}
            </p>
          )}
        </div>

        {/* Utilizatori recenți */}
        <div style={cardStyle}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
            <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
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
                  <p style={{ fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-primary)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {u.full_name || u.username}
                  </p>
                  <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.email}</p>
                </div>
                <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", flexShrink: 0, marginLeft: "0.5rem" }}>
                  {u.created_at ? new Date(u.created_at).toLocaleDateString("ro-RO") : ""}
                </span>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Raport Produse */}
      <div style={{ ...cardStyle, marginTop: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
          <FileBarChart style={{ width: "18px", height: "18px", color: "#a78bfa" }} />
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
            Raport Produse
          </h2>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "0.75rem", marginBottom: "1rem" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.6875rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>Pret minim</label>
            <input type="number" step="0.01" value={reportFilters.price_min}
              onChange={(e) => setReportFilters({...reportFilters, price_min: e.target.value})}
              style={{ width: "100%", padding: "0.4rem 0.625rem", borderRadius: "0.375rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", color: "var(--text-primary)", fontSize: "0.8125rem", outline: "none" }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.6875rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>Pret maxim</label>
            <input type="number" step="0.01" value={reportFilters.price_max}
              onChange={(e) => setReportFilters({...reportFilters, price_max: e.target.value})}
              style={{ width: "100%", padding: "0.4rem 0.625rem", borderRadius: "0.375rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", color: "var(--text-primary)", fontSize: "0.8125rem", outline: "none" }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.6875rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>De la data</label>
            <input type="date" value={reportFilters.date_from}
              onChange={(e) => setReportFilters({...reportFilters, date_from: e.target.value})}
              style={{ width: "100%", padding: "0.4rem 0.625rem", borderRadius: "0.375rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", color: "var(--text-primary)", fontSize: "0.8125rem", outline: "none" }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.6875rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>Pana la data</label>
            <input type="date" value={reportFilters.date_to}
              onChange={(e) => setReportFilters({...reportFilters, date_to: e.target.value})}
              style={{ width: "100%", padding: "0.4rem 0.625rem", borderRadius: "0.375rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", color: "var(--text-primary)", fontSize: "0.8125rem", outline: "none" }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.6875rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>Categorie</label>
            <input type="text" value={reportFilters.category}
              onChange={(e) => setReportFilters({...reportFilters, category: e.target.value})}
              placeholder="ex: electronics"
              style={{ width: "100%", padding: "0.4rem 0.625rem", borderRadius: "0.375rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", color: "var(--text-primary)", fontSize: "0.8125rem", outline: "none" }}
            />
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
          <button onClick={generateReport} disabled={reportLoading}
            style={{
              padding: "0.5rem 1rem", borderRadius: "0.5rem",
              backgroundColor: reportLoading ? "var(--bg-elevated)" : "var(--blue-primary)",
              color: "var(--text-primary)", border: "none", cursor: reportLoading ? "wait" : "pointer",
              fontSize: "0.8125rem", fontWeight: 500,
            }}>
            {reportLoading ? "Se genereaza..." : "Genereaza raport"}
          </button>
          {/* FlipRadar — ITEM 17: export PDF cu aceiasi parametri de filtrare */}
          <button onClick={exportReportPdf} disabled={exportLoading}
            style={{
              display: "flex", alignItems: "center", gap: "0.375rem",
              padding: "0.5rem 1rem", borderRadius: "0.5rem",
              backgroundColor: "transparent", color: "#a78bfa",
              border: "1px solid var(--border-color)", cursor: exportLoading ? "wait" : "pointer",
              fontSize: "0.8125rem", fontWeight: 500,
            }}>
            <FileBarChart style={{ width: "14px", height: "14px" }} />
            {exportLoading ? "Se exporta..." : "Export PDF"}
          </button>
        </div>

        {reportError && (
          <p style={{ color: "#f87171", fontSize: "0.75rem", marginBottom: "1rem" }}>{reportError}</p>
        )}

        {reportData && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", marginBottom: "1rem" }}>
              <div style={{ padding: "0.875rem", borderRadius: "0.625rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)" }}>
                <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0 }}>Total produse</p>
                <p style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)", margin: "0.25rem 0 0" }}>{reportData.summary.count}</p>
              </div>
              <div style={{ padding: "0.875rem", borderRadius: "0.625rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)" }}>
                <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0 }}>Pret mediu</p>
                <p style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--blue-light)", margin: "0.25rem 0 0" }}>{Number(reportData.summary.pret_mediu).toFixed(2)}</p>
              </div>
              <div style={{ padding: "0.875rem", borderRadius: "0.625rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)" }}>
                <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0 }}>ROI mediu</p>
                <p style={{ fontSize: "1.25rem", fontWeight: 700, color: "#a78bfa", margin: "0.25rem 0 0" }}>{Number(reportData.summary.roi_mediu).toFixed(2)}%</p>
              </div>
              <div style={{ padding: "0.875rem", borderRadius: "0.625rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)" }}>
                <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0 }}>Profit estimat total</p>
                <p style={{ fontSize: "1.25rem", fontWeight: 700, color: "#4ade80", margin: "0.25rem 0 0" }}>{Number(reportData.summary.profit_estimat_total).toFixed(2)}</p>
              </div>
            </div>

            {reportData.products.length === 0 ? (
              <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", textAlign: "center", padding: "1.5rem 0" }}>
                Niciun produs in intervalul/filtru selectat.
              </p>
            ) : (
              <>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.75rem" }}>
                    <thead>
                      <tr>
                        {["Produs", "Categorie", "Pret", "Pret revanzare", "ROI", "Sursa", "Data"].map((h) => (
                          <th key={h} style={{ textAlign: "left", padding: "0.5rem 0.5rem", color: "var(--text-secondary)", fontWeight: 600, borderBottom: "1px solid var(--border-color)" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {reportData.products.slice((reportPage - 1) * PAGE_SIZE, reportPage * PAGE_SIZE).map((p) => (
                        <tr key={p.id}>
                          <td style={{ padding: "0.5rem", color: "var(--text-primary)", borderBottom: "1px solid var(--border-color)" }}>{p.name}</td>
                          <td style={{ padding: "0.5rem", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-color)" }}>{p.category || "-"}</td>
                          <td style={{ padding: "0.5rem", color: "var(--text-primary)", borderBottom: "1px solid var(--border-color)" }}>{p.price != null ? `${Number(p.price).toFixed(2)} ${p.currency || ""}` : "-"}</td>
                          <td style={{ padding: "0.5rem", color: "#a78bfa", borderBottom: "1px solid var(--border-color)" }}>{p.resale_price != null ? `${Number(p.resale_price).toFixed(2)} ${p.currency || ""}` : "-"}</td>
                          <td style={{ padding: "0.5rem", color: p.roi == null ? "var(--text-secondary)" : (p.roi >= 0 ? "#4ade80" : "#f87171"), fontWeight: 600, borderBottom: "1px solid var(--border-color)" }}>{p.roi == null ? "-" : `${Number(p.roi).toFixed(2)}%`}</td>
                          <td style={{ padding: "0.5rem", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-color)" }}>{p.source || "-"}</td>
                          <td style={{ padding: "0.5rem", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-color)" }}>{p.created_at ? new Date(p.created_at).toLocaleDateString("ro-RO") : "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Paginare */}
                {reportData.products.length > PAGE_SIZE && (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "0.75rem" }}>
                    <button
                      onClick={() => setReportPage((p) => Math.max(1, p - 1))}
                      disabled={reportPage === 1}
                      style={{
                        display: "flex", alignItems: "center", gap: "0.25rem",
                        padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
                        backgroundColor: "transparent", color: reportPage === 1 ? "var(--text-muted)" : "var(--text-secondary)",
                        border: "1px solid var(--border-color)", cursor: reportPage === 1 ? "not-allowed" : "pointer",
                        fontSize: "0.75rem",
                      }}
                    >
                      <ChevronLeft style={{ width: "12px", height: "12px" }} /> Anterior
                    </button>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                      Pagina {reportPage} din {Math.max(1, Math.ceil(reportData.products.length / PAGE_SIZE))}
                    </span>
                    <button
                      onClick={() => setReportPage((p) => Math.min(Math.ceil(reportData.products.length / PAGE_SIZE), p + 1))}
                      disabled={reportPage >= Math.ceil(reportData.products.length / PAGE_SIZE)}
                      style={{
                        display: "flex", alignItems: "center", gap: "0.25rem",
                        padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
                        backgroundColor: "transparent", color: reportPage >= Math.ceil(reportData.products.length / PAGE_SIZE) ? "var(--text-muted)" : "var(--text-secondary)",
                        border: "1px solid var(--border-color)", cursor: reportPage >= Math.ceil(reportData.products.length / PAGE_SIZE) ? "not-allowed" : "pointer",
                        fontSize: "0.75rem",
                      }}
                    >
                      Urmator <ChevronRight style={{ width: "12px", height: "12px" }} />
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
