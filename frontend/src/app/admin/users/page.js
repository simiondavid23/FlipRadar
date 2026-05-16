"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { adminAPI } from "@/lib/api";
import {
  Users, Shield, ArrowLeft, Search, UserCheck, UserX, Loader2, X,
  Package, Eye, Bell, ShoppingCart, Boxes, Heart, MessageCircle,
  Sparkles, Globe, FileSpreadsheet, MessageSquare,
  CheckCircle, XCircle,
} from "lucide-react";

const FEATURE_DEFS = [
  { key: "can_use_ai",            label: "Functii AI",              icon: Sparkles },
  { key: "can_use_scraping",      label: "Web Scraping",            icon: Globe },
  { key: "can_use_alerts",        label: "Creare alerte de pret",   icon: Bell },
  { key: "can_use_import_export", label: "Import / Export date",    icon: FileSpreadsheet },
];

const cardStyle = {
  backgroundColor: "var(--bg-card)",
  border: "1px solid var(--border-color)",
  borderRadius: "1rem",
  padding: "1.25rem",
};

function Badge({ ok, label, labelOn, labelOff }) {
  const on = ok;
  const text = on ? (labelOn ?? label) : (labelOff ?? label);
  return (
    <span style={{
      padding: "0.125rem 0.5rem",
      borderRadius: "0.375rem",
      fontSize: "0.6875rem",
      fontWeight: 600,
      backgroundColor: on ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
      color: on ? "#4ade80" : "#f87171",
      whiteSpace: "nowrap",
    }}>
      {text}
    </span>
  );
}

function StatTile({ icon: Icon, label, value, sublabel, color, href }) {
  const inner = (
    <>
      <div style={{
        padding: "0.4rem", borderRadius: "0.5rem",
        backgroundColor: color, display: "flex", flexShrink: 0,
      }}>
        <Icon style={{ width: 14, height: 14, color: "var(--text-primary)" }} />
      </div>
      <div style={{ minWidth: 0 }}>
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.6875rem" }}>{label}</p>
        <p style={{ margin: 0, color: "var(--text-primary)", fontSize: "1rem", fontWeight: 600 }}>{value}</p>
        {sublabel && <p style={{ margin: "0.125rem 0 0", color: "var(--text-muted)", fontSize: "0.6875rem" }}>{sublabel}</p>}
      </div>
    </>
  );

  const baseStyle = {
    display: "flex",
    gap: "0.75rem",
    alignItems: "flex-start",
    padding: "0.75rem",
    borderRadius: "0.625rem",
    backgroundColor: "rgba(255,255,255,0.03)",
    border: "1px solid var(--border-color)",
  };

  if (!href) {
    return <div style={baseStyle}>{inner}</div>;
  }

  return (
    <Link
      href={href}
      style={{
        ...baseStyle,
        textDecoration: "none",
        color: "inherit",
        cursor: "pointer",
        transition: "border-color 0.12s ease, background-color 0.12s ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = color;
        e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.06)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--border-color)";
        e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)";
      }}
    >
      {inner}
    </Link>
  );
}

function formatDate(s) {
  if (!s) return "-";
  try { return new Date(s).toLocaleString("ro-RO"); }
  catch { return s; }
}

function formatMoney(n) {
  if (n == null) return "0";
  return Number(n).toLocaleString("ro-RO", { maximumFractionDigits: 2 });
}

export default function AdminUsersPage() {
  const { user: currentAdmin } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectUserId = searchParams.get("user");
  const selectedId = preselectUserId && Number.isFinite(Number(preselectUserId))
    ? Number(preselectUserId)
    : null;

  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminAPI.getUsers();
      setUsers(res.data);
    } catch (e) {
      setErrorMsg(e.response?.data?.detail || "Eroare la incarcarea utilizatorilor.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    setDetailLoading(true);
    setErrorMsg("");
    adminAPI.getUser(selectedId)
      .then((res) => { if (!cancelled) setDetail(res.data); })
      .catch((e) => { if (!cancelled) setErrorMsg(e.response?.data?.detail || "Eroare la incarcarea detaliilor."); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [selectedId]);

  const openDetail = (id) => {
    router.push(`/admin/users?user=${id}`, { scroll: false });
  };

  const closeDetail = () => {
    router.push("/admin/users", { scroll: false });
  };

  const flash = (msg, isError = false) => {
    if (isError) setErrorMsg(msg); else setSuccessMsg(msg);
    setTimeout(() => {
      setErrorMsg(""); setSuccessMsg("");
    }, 3500);
  };

  const toggleFeature = async (key) => {
    if (!detail) return;
    setSaving(true);
    const next = !detail[key];
    try {
      const res = await adminAPI.updateUserFeatures(detail.id, { [key]: next });
      setDetail({ ...detail, [key]: next });
      setUsers((list) => list.map((u) => (u.id === detail.id ? { ...u, ...res.data } : u)));
      flash(`Permisiunea a fost ${next ? "activata" : "dezactivata"}.`);
    } catch (e) {
      flash(e.response?.data?.detail || "Eroare la actualizare.", true);
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async () => {
    if (!detail) return;
    setSaving(true);
    const next = !detail.is_active;
    try {
      const res = await adminAPI.setUserActive(detail.id, next);
      setDetail({ ...detail, is_active: next });
      setUsers((list) => list.map((u) => (u.id === detail.id ? { ...u, ...res.data } : u)));
      flash(next ? "Contul a fost reactivat." : "Contul a fost dezactivat. Utilizatorul nu mai poate accesa platforma.");
    } catch (e) {
      flash(e.response?.data?.detail || "Eroare la actualizare.", true);
    } finally {
      setSaving(false);
    }
  };

  const filtered = users.filter((u) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      (u.email || "").toLowerCase().includes(q) ||
      (u.username || "").toLowerCase().includes(q) ||
      (u.full_name || "").toLowerCase().includes(q)
    );
  });

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.625rem", borderRadius: "0.75rem", backgroundColor: "#2563eb", display: "flex" }}>
            <Users style={{ width: 22, height: 22, color: "var(--text-primary)" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Gestionare Utilizatori</h1>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>
              Vizualizeaza activitatea conturilor si controleaza accesul la functionalitati
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

      {/* Flash messages */}
      {(errorMsg || successMsg) && (
        <div style={{
          marginBottom: "1rem",
          padding: "0.75rem 1rem",
          borderRadius: "0.625rem",
          border: `1px solid ${errorMsg ? "#7f1d1d" : "#14532d"}`,
          backgroundColor: errorMsg ? "rgba(127,29,29,0.2)" : "rgba(20,83,45,0.2)",
          color: errorMsg ? "#fca5a5" : "#86efac",
          fontSize: "0.8125rem",
          display: "flex", alignItems: "center", gap: "0.5rem",
        }}>
          {errorMsg ? <XCircle style={{ width: 16, height: 16 }} /> : <CheckCircle style={{ width: 16, height: 16 }} />}
          <span>{errorMsg || successMsg}</span>
        </div>
      )}

      {/* Search */}
      <div style={{ ...cardStyle, marginBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", position: "relative" }}>
          <Search style={{ width: 16, height: 16, color: "var(--text-muted)", position: "absolute", left: "0.75rem" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cauta dupa email, username sau nume complet..."
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

      <div style={{ display: "grid", gridTemplateColumns: selectedId ? "1.1fr 0.9fr" : "1fr", gap: "1rem" }}>
        {/* Users table */}
        <div style={cardStyle}>
          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
              <Loader2 style={{ width: 28, height: 28, color: "#60a5fa", animation: "spin 1s linear infinite" }} />
            </div>
          ) : filtered.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", textAlign: "center", padding: "2rem 0" }}>
              Nu au fost gasiti utilizatori.
            </p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--text-muted)", fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Utilizator</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Status</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Produse</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Watchlist</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Alerte</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Vanzari</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Creat</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((u) => {
                    const isSelected = selectedId === u.id;
                    return (
                      <tr
                        key={u.id}
                        onClick={() => openDetail(u.id)}
                        style={{
                          borderTop: "1px solid var(--border-color)",
                          cursor: "pointer",
                          backgroundColor: isSelected ? "rgba(37,99,235,0.15)" : "transparent",
                          transition: "background-color 0.12s ease",
                        }}
                        onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
                        onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = "transparent"; }}
                      >
                        <td style={{ padding: "0.625rem 0.5rem" }}>
                          <div style={{ display: "flex", flexDirection: "column" }}>
                            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>{u.full_name || u.username}</span>
                            <span style={{ color: "var(--text-muted)", fontSize: "0.6875rem" }}>{u.email}</span>
                          </div>
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem" }}>
                          <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                            <Badge ok={u.is_active} labelOn="Activ" labelOff="Dezactivat" />
                            {u.is_admin && (
                              <span style={{
                                padding: "0.125rem 0.5rem", borderRadius: "0.375rem",
                                fontSize: "0.6875rem", fontWeight: 600,
                                backgroundColor: "rgba(220,38,38,0.15)", color: "#fca5a5",
                              }}>Admin</span>
                            )}
                          </div>
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "var(--text-secondary)" }}>{u.products_count}</td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "var(--text-secondary)" }}>{u.watchlist_count}</td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "var(--text-secondary)" }}>{u.active_alerts_count}</td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "var(--text-secondary)" }}>{u.sales_count}</td>
                        <td style={{ padding: "0.625rem 0.5rem", color: "var(--text-muted)", fontSize: "0.6875rem" }}>
                          {u.created_at ? new Date(u.created_at).toLocaleDateString("ro-RO") : "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selectedId && (
          <div style={{ ...cardStyle, position: "relative", minHeight: "300px" }}>
            <button
              onClick={closeDetail}
              aria-label="Inchide"
              style={{
                position: "absolute", top: "0.75rem", right: "0.75rem",
                padding: "0.375rem", borderRadius: "0.5rem",
                background: "transparent", border: "1px solid var(--border-color)",
                color: "var(--text-secondary)", cursor: "pointer", display: "flex",
              }}
            >
              <X style={{ width: 14, height: 14 }} />
            </button>

            {detailLoading ? (
              <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
                <Loader2 style={{ width: 28, height: 28, color: "#60a5fa", animation: "spin 1s linear infinite" }} />
              </div>
            ) : detail ? (
              <>
                {/* Identity */}
                <div style={{ marginBottom: "1.25rem", paddingRight: "2rem" }}>
                  <h2 style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                    {detail.full_name || detail.username}
                  </h2>
                  <p style={{ margin: "0.125rem 0 0", color: "var(--text-secondary)", fontSize: "0.8125rem" }}>{detail.email}</p>
                  <div style={{ display: "flex", gap: "0.375rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
                    <Badge ok={detail.is_active} labelOn="Activ" labelOff="Dezactivat" />
                    {detail.is_admin && (
                      <span style={{
                        padding: "0.125rem 0.5rem", borderRadius: "0.375rem",
                        fontSize: "0.6875rem", fontWeight: 600,
                        backgroundColor: "rgba(220,38,38,0.15)", color: "#fca5a5",
                      }}>
                        <Shield style={{ width: 10, height: 10, marginRight: "0.25rem", verticalAlign: "middle" }} />
                        Admin
                      </span>
                    )}
                    <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", alignSelf: "center" }}>
                      Cont creat: {formatDate(detail.created_at)}
                    </span>
                  </div>
                </div>

                {/* Stats */}
                <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 0.5rem" }}>
                  Statistici activitate
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.5rem", marginBottom: "1rem" }}>
                  <StatTile icon={Package}        label="Produse"       value={detail.products_count} color="#9333ea" href={`/admin/products?user=${detail.id}`} />
                  <StatTile icon={Eye}            label="Watchlist"     value={detail.watchlist_count} color="#ca8a04" href={`/admin/watchlist?user=${detail.id}`} />
                  <StatTile icon={Bell}           label="Alerte active" value={`${detail.active_alerts}/${detail.total_alerts}`} sublabel={`${detail.triggered_alerts} declansate`} color="#0891b2" href={`/admin/alerts?user=${detail.id}`} />
                  <StatTile icon={ShoppingCart}   label="Vanzari"       value={detail.sales_count} sublabel={`Venit: ${formatMoney(detail.sales_revenue)}`} color="#16a34a" href={`/admin/sales?user=${detail.id}`} />
                  <StatTile icon={Boxes}          label="Inventar"      value={detail.inventory_count} sublabel={`Valoare: ${formatMoney(detail.inventory_value)}`} color="#f97316" href={`/admin/inventory?user=${detail.id}`} />
                  <StatTile icon={Heart}          label="Favorite"      value={detail.favorites_count} sublabel={`${detail.blacklist_count} pe blacklist`} color="#ec4899" href={`/admin/favorites?user=${detail.id}`} />
                  <StatTile icon={MessageSquare}  label="Tickete"       value={detail.tickets_count} sublabel={`${detail.open_tickets} deschise`} color="#dc2626" href={`/admin/tickets?user=${detail.id}`} />
                  <StatTile icon={MessageCircle}  label="Mesaje AI"     value={detail.chat_messages_count} sublabel={detail.last_chat_at ? `Ultim: ${new Date(detail.last_chat_at).toLocaleDateString("ro-RO")}` : "Fara activitate"} color="#2563eb" href={`/admin/chat-messages?user=${detail.id}`} />
                </div>

                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                  {detail.sales_count > 0 && (
                    <span>Profit total: <strong style={{ color: "var(--text-primary)" }}>{formatMoney(detail.sales_profit)}</strong> · </span>
                  )}
                  <span>Notificari necitite: <strong style={{ color: "var(--text-primary)" }}>{detail.unread_notifications}</strong></span>
                </div>

                {/* Feature flags */}
                <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 0.5rem" }}>
                  Permisiuni functionalitati
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", marginBottom: "1rem" }}>
                  {FEATURE_DEFS.map(({ key, label, icon: Icon }) => {
                    const on = !!detail[key];
                    const disabled = saving || detail.id === currentAdmin?.id;
                    return (
                      <label
                        key={key}
                        style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "0.625rem 0.75rem",
                          borderRadius: "0.5rem",
                          border: "1px solid var(--border-color)",
                          backgroundColor: on ? "rgba(34,197,94,0.06)" : "rgba(239,68,68,0.06)",
                          cursor: disabled ? "not-allowed" : "pointer",
                          opacity: disabled ? 0.6 : 1,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-primary)", fontSize: "0.8125rem" }}>
                          <Icon style={{ width: 14, height: 14, color: on ? "#4ade80" : "#f87171" }} />
                          {label}
                        </div>
                        <input
                          type="checkbox"
                          checked={on}
                          disabled={disabled}
                          onChange={() => toggleFeature(key)}
                          style={{ width: 16, height: 16, accentColor: "#2563eb" }}
                        />
                      </label>
                    );
                  })}
                </div>

                {/* Account active toggle */}
                <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 0.5rem" }}>
                  Stare cont
                </p>
                <button
                  onClick={toggleActive}
                  disabled={saving || detail.id === currentAdmin?.id}
                  style={{
                    width: "100%",
                    padding: "0.75rem",
                    borderRadius: "0.5rem",
                    border: "1px solid " + (detail.is_active ? "rgba(239,68,68,0.4)" : "rgba(34,197,94,0.4)"),
                    backgroundColor: detail.is_active ? "rgba(239,68,68,0.1)" : "rgba(34,197,94,0.1)",
                    color: detail.is_active ? "#fca5a5" : "#86efac",
                    cursor: (saving || detail.id === currentAdmin?.id) ? "not-allowed" : "pointer",
                    opacity: (saving || detail.id === currentAdmin?.id) ? 0.5 : 1,
                    fontSize: "0.8125rem", fontWeight: 600,
                    display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem",
                  }}
                >
                  {saving ? (
                    <Loader2 style={{ width: 14, height: 14, animation: "spin 1s linear infinite" }} />
                  ) : detail.is_active ? (
                    <><UserX style={{ width: 14, height: 14 }} /> Dezactiveaza contul</>
                  ) : (
                    <><UserCheck style={{ width: 14, height: 14 }} /> Reactiveaza contul</>
                  )}
                </button>
                {detail.id === currentAdmin?.id && (
                  <p style={{ marginTop: "0.5rem", fontSize: "0.6875rem", color: "#fbbf24", textAlign: "center" }}>
                    Nu iti poti modifica propriul cont.
                  </p>
                )}
              </>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem", textAlign: "center", padding: "2rem 0" }}>
                Nu am putut incarca detaliile.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
