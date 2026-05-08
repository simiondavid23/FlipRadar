"use client";
import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { adminAPI } from "@/lib/api";
import {
  ShoppingCart, ArrowLeft, Loader2, Search, User as UserIcon, X,
} from "lucide-react";

const cardStyle = {
  backgroundColor: "var(--bg-card)",
  border: "1px solid var(--border-color)",
  borderRadius: "1rem",
  padding: "1.25rem",
};

function formatMoney(n, currency) {
  if (n == null) return "-";
  const value = Number(n).toLocaleString("ro-RO", { maximumFractionDigits: 2 });
  return currency ? `${value} ${currency}` : value;
}

export default function AdminSalesPage() {
  const searchParams = useSearchParams();
  const userId = searchParams.get("user");

  const [sales, setSales] = useState([]);
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
        const params = userId ? { user_id: Number(userId) } : {};
        const [salesRes, userRes] = await Promise.all([
          adminAPI.getSales(params),
          userId ? adminAPI.getUser(userId).catch(() => null) : Promise.resolve(null),
        ]);
        if (!cancelled) {
          setSales(salesRes.data);
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
  }, [userId]);

  const filtered = useMemo(() => {
    if (!search.trim()) return sales;
    const q = search.toLowerCase();
    return sales.filter((s) => {
      const name = (s.product_name || "").toLowerCase();
      const platform = (s.platform || "").toLowerCase();
      const buyer = (s.buyer || "").toLowerCase();
      const ownerEmail = (s.owner?.email || "").toLowerCase();
      const ownerName = (s.owner?.full_name || s.owner?.username || "").toLowerCase();
      return name.includes(q) || platform.includes(q) || buyer.includes(q)
        || ownerEmail.includes(q) || ownerName.includes(q);
    });
  }, [sales, search]);

  const totals = useMemo(() => {
    let units = 0;
    let revenue = 0;
    let profit = 0;
    for (const s of filtered) {
      const qty = Number(s.quantity) || 0;
      const sale = Number(s.sale_price) || 0;
      units += qty;
      revenue += qty * sale;
      if (s.cost_price != null) {
        profit += qty * (sale - Number(s.cost_price));
      }
    }
    return { units, revenue, profit };
  }, [filtered]);

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.625rem", borderRadius: "0.75rem", backgroundColor: "#16a34a", display: "flex" }}>
            <ShoppingCart style={{ width: 22, height: 22, color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>
              {userInfo ? `Vanzari - ${userInfo.full_name || userInfo.username}` : "Toate vanzarile"}
            </h1>
            <p style={{ fontSize: "0.8125rem", color: "#94a3b8", margin: 0 }}>
              {userInfo ? userInfo.email : "Istoricul vanzarilor raportate de utilizatori"}
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
          <Link href="/admin/sales" style={{
            display: "flex", alignItems: "center", gap: "0.375rem",
            padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
            backgroundColor: "rgba(255,255,255,0.06)", textDecoration: "none",
            fontSize: "0.75rem", color: "#cbd5e1",
          }}>
            <X style={{ width: 12, height: 12 }} /> Vezi toate vanzarile
          </Link>
        </div>
      )}

      <div style={{ ...cardStyle, marginBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", position: "relative" }}>
          <Search style={{ width: 16, height: 16, color: "#64748b", position: "absolute", left: "0.75rem" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cauta dupa produs, platforma, cumparator sau utilizator..."
            style={{
              width: "100%",
              padding: "0.625rem 0.75rem 0.625rem 2.25rem",
              borderRadius: "0.5rem",
              backgroundColor: "#0f172a",
              border: "1px solid var(--border-color)",
              color: "white",
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
          <p style={{ color: "#64748b", fontSize: "0.875rem", textAlign: "center", padding: "2rem 0" }}>
            Nicio vanzare inregistrata.
          </p>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <p style={{ color: "#94a3b8", fontSize: "0.75rem", margin: 0 }}>
                {filtered.length} vanzar{filtered.length === 1 ? "e" : "i"} {search ? "(filtrate)" : "in total"}
                {" · "}
                Bucati: <strong style={{ color: "white" }}>{totals.units}</strong>
              </p>
              <p style={{ color: "#94a3b8", fontSize: "0.75rem", margin: 0 }}>
                Venit: <strong style={{ color: "white" }}>{formatMoney(totals.revenue)}</strong>
                {" · "}
                Profit: <strong style={{ color: totals.profit >= 0 ? "#4ade80" : "#f87171" }}>
                  {formatMoney(totals.profit)}
                </strong>
              </p>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#64748b", fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Produs</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Cantitate</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Pret vanzare</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Cost</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Profit</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Platforma</th>
                    {!userId && <th style={{ padding: "0.5rem 0.5rem" }}>Proprietar</th>}
                    <th style={{ padding: "0.5rem 0.5rem" }}>Vandut</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((s) => {
                    const qty = Number(s.quantity) || 0;
                    const sale = Number(s.sale_price) || 0;
                    const cost = s.cost_price != null ? Number(s.cost_price) : null;
                    const profit = cost != null ? qty * (sale - cost) : null;
                    return (
                      <tr key={s.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                        <td style={{ padding: "0.625rem 0.5rem", color: "white" }}>
                          <div
                            title={s.product_name}
                            style={{ maxWidth: "260px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "help" }}
                          >
                            {s.product_name}
                          </div>
                          {s.buyer && (
                            <div style={{ fontSize: "0.6875rem", color: "#64748b" }}>Cumparator: {s.buyer}</div>
                          )}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "white", fontWeight: 500 }}>
                          {qty}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "#cbd5e1" }}>
                          {formatMoney(sale, s.currency)}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "#cbd5e1" }}>
                          {cost != null ? formatMoney(cost, s.currency) : "-"}
                        </td>
                        <td style={{
                          padding: "0.625rem 0.5rem", textAlign: "right", fontWeight: 500,
                          color: profit == null ? "#64748b" : profit >= 0 ? "#4ade80" : "#f87171",
                        }}>
                          {profit != null ? formatMoney(profit, s.currency) : "-"}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", color: "#cbd5e1" }}>{s.platform || "-"}</td>
                        {!userId && (
                          <td style={{ padding: "0.625rem 0.5rem" }}>
                            <Link href={`/admin/sales?user=${s.owner.id}`} style={{
                              color: "#93c5fd", textDecoration: "none", fontSize: "0.75rem",
                            }}>
                              {s.owner.full_name || s.owner.username}
                            </Link>
                          </td>
                        )}
                        <td style={{ padding: "0.625rem 0.5rem", color: "#64748b", fontSize: "0.6875rem" }}>
                          {s.sold_at ? new Date(s.sold_at).toLocaleDateString("ro-RO") : "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
