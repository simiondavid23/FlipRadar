"use client";
import { useEffect, useState, useMemo } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { adminAPI } from "@/lib/api";
import {
  Bell, ArrowLeft, Loader2, Search, User as UserIcon, X,
  CheckCircle, XCircle, Zap,
} from "lucide-react";

const cardStyle = {
  backgroundColor: "var(--bg-card)",
  border: "1px solid var(--border-color)",
  borderRadius: "1rem",
  padding: "1.25rem",
};

const STATUS_OPTIONS = [
  { value: "all",        label: "Toate" },
  { value: "active",     label: "Active" },
  { value: "triggered",  label: "Declansate" },
  { value: "inactive",   label: "Inactive" },
];

export default function AdminAlertsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const userId = searchParams.get("user");
  const status = searchParams.get("status") || "all";

  const [alerts, setAlerts] = useState([]);
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
        const [alertsRes, userRes] = await Promise.all([
          adminAPI.getAlerts(params),
          userId ? adminAPI.getUser(userId).catch(() => null) : Promise.resolve(null),
        ]);
        if (!cancelled) {
          setAlerts(alertsRes.data);
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
    if (!search.trim()) return alerts;
    const q = search.toLowerCase();
    return alerts.filter((a) => {
      const name = (a.product?.name || "").toLowerCase();
      const ownerEmail = (a.owner?.email || "").toLowerCase();
      const ownerName = (a.owner?.full_name || a.owner?.username || "").toLowerCase();
      return name.includes(q) || ownerEmail.includes(q) || ownerName.includes(q);
    });
  }, [alerts, search]);

  const setStatus = (next) => {
    const p = new URLSearchParams(searchParams.toString());
    if (next === "all") p.delete("status"); else p.set("status", next);
    router.replace(`${pathname}?${p.toString()}`);
  };

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.625rem", borderRadius: "0.75rem", backgroundColor: "#0891b2", display: "flex" }}>
            <Bell style={{ width: 22, height: 22, color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>
              {userInfo ? `Alerte - ${userInfo.full_name || userInfo.username}` : "Alerte de pret"}
            </h1>
            <p style={{ fontSize: "0.8125rem", color: "#94a3b8", margin: 0 }}>
              {userInfo ? userInfo.email : "Toate alertele configurate de utilizatori"}
            </p>
          </div>
        </div>
        <Link href="/admin" style={{
          display: "flex", alignItems: "center", gap: "0.375rem",
          padding: "0.5rem 1rem", borderRadius: "0.5rem",
          border: "1px solid var(--border-color)", textDecoration: "none",
          fontSize: "0.8125rem", color: "#94a3b8",
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
            href={`/admin/alerts${status && status !== "all" ? `?status=${status}` : ""}`}
            style={{
              display: "flex", alignItems: "center", gap: "0.375rem",
              padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
              backgroundColor: "rgba(255,255,255,0.06)", textDecoration: "none",
              fontSize: "0.75rem", color: "#cbd5e1",
            }}>
            <X style={{ width: 12, height: 12 }} /> Vezi toate alertele
          </Link>
        </div>
      )}

      {/* Status pills */}
      <div style={{ ...cardStyle, marginBottom: "1rem", display: "flex", flexWrap: "wrap", gap: "0.375rem", alignItems: "center" }}>
        <span style={{ color: "#94a3b8", fontSize: "0.75rem", marginRight: "0.5rem" }}>Status:</span>
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
                color: active ? "white" : "#94a3b8",
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
        {/* Search within loaded set */}
        <div style={{ position: "relative", minWidth: "200px", flex: "0 1 300px" }}>
          <Search style={{ width: 14, height: 14, color: "#64748b", position: "absolute", left: "0.625rem", top: "0.5rem" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cauta produs sau utilizator..."
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

      <div style={cardStyle}>
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
            <Loader2 style={{ width: 28, height: 28, color: "#60a5fa", animation: "spin 1s linear infinite" }} />
          </div>
        ) : error ? (
          <p style={{ color: "#fca5a5", fontSize: "0.875rem", textAlign: "center", padding: "2rem 0" }}>{error}</p>
        ) : filtered.length === 0 ? (
          <p style={{ color: "#64748b", fontSize: "0.875rem", textAlign: "center", padding: "2rem 0" }}>
            Nicio alerta gasita.
          </p>
        ) : (
          <>
            <p style={{ color: "#94a3b8", fontSize: "0.75rem", margin: "0 0 0.75rem" }}>
              {filtered.length} alert{filtered.length === 1 ? "a" : "e"} {search ? "(filtrate)" : ""}
            </p>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#64748b", fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Produs</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Prag</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Tip</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Stare</th>
                    {!userId && <th style={{ padding: "0.5rem 0.5rem" }}>Proprietar</th>}
                    <th style={{ padding: "0.5rem 0.5rem" }}>Creata</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((a) => (
                    <tr key={a.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                      <td style={{ padding: "0.625rem 0.5rem", color: "white" }}>
                        <div
                          title={a.product?.name || "(produs sters)"}
                          style={{ maxWidth: "280px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "help" }}
                        >
                          {a.product?.name || "(produs sters)"}
                        </div>
                      </td>
                      <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "white", fontWeight: 500 }}>
                        {a.target_price} {a.currency}
                      </td>
                      <td style={{ padding: "0.625rem 0.5rem", color: "#cbd5e1", fontSize: "0.75rem" }}>
                        {a.alert_type === "price_rise" ? "Crestere pret" : "Scadere pret"}
                      </td>
                      <td style={{ padding: "0.625rem 0.5rem" }}>
                        <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                          <span style={{
                            display: "inline-flex", alignItems: "center", gap: "0.25rem",
                            padding: "0.125rem 0.5rem", borderRadius: "0.375rem",
                            fontSize: "0.6875rem", fontWeight: 600,
                            backgroundColor: a.is_active ? "rgba(34,197,94,0.15)" : "rgba(100,116,139,0.15)",
                            color: a.is_active ? "#4ade80" : "#94a3b8",
                          }}>
                            {a.is_active ? <CheckCircle style={{ width: 10, height: 10 }} /> : <XCircle style={{ width: 10, height: 10 }} />}
                            {a.is_active ? "Activa" : "Inactiva"}
                          </span>
                          {a.is_triggered && (
                            <span style={{
                              display: "inline-flex", alignItems: "center", gap: "0.25rem",
                              padding: "0.125rem 0.5rem", borderRadius: "0.375rem",
                              fontSize: "0.6875rem", fontWeight: 600,
                              backgroundColor: "rgba(249,115,22,0.15)", color: "#fb923c",
                            }}>
                              <Zap style={{ width: 10, height: 10 }} /> Declansata
                            </span>
                          )}
                        </div>
                      </td>
                      {!userId && (
                        <td style={{ padding: "0.625rem 0.5rem" }}>
                          <Link href={`/admin/alerts?user=${a.owner.id}`} style={{
                            color: "#93c5fd", textDecoration: "none", fontSize: "0.75rem",
                          }}>
                            {a.owner.full_name || a.owner.username}
                          </Link>
                        </td>
                      )}
                      <td style={{ padding: "0.625rem 0.5rem", color: "#64748b", fontSize: "0.6875rem" }}>
                        {a.created_at ? new Date(a.created_at).toLocaleDateString("ro-RO") : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
