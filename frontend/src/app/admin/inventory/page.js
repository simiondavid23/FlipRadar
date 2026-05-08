"use client";
import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { adminAPI } from "@/lib/api";
import {
  Boxes, ArrowLeft, Loader2, Search, User as UserIcon, X,
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

export default function AdminInventoryPage() {
  const searchParams = useSearchParams();
  const userId = searchParams.get("user");

  const [items, setItems] = useState([]);
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
        const [itemsRes, userRes] = await Promise.all([
          adminAPI.getInventory(params),
          userId ? adminAPI.getUser(userId).catch(() => null) : Promise.resolve(null),
        ]);
        if (!cancelled) {
          setItems(itemsRes.data);
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
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter((it) => {
      const name = (it.name || "").toLowerCase();
      const sku = (it.sku || "").toLowerCase();
      const category = (it.category || "").toLowerCase();
      const ownerEmail = (it.owner?.email || "").toLowerCase();
      const ownerName = (it.owner?.full_name || it.owner?.username || "").toLowerCase();
      return name.includes(q) || sku.includes(q) || category.includes(q)
        || ownerEmail.includes(q) || ownerName.includes(q);
    });
  }, [items, search]);

  const totals = useMemo(() => {
    let units = 0;
    let value = 0;
    for (const it of filtered) {
      const qty = Number(it.quantity) || 0;
      const price = Number(it.purchase_price) || 0;
      units += qty;
      value += qty * price;
    }
    return { units, value };
  }, [filtered]);

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.625rem", borderRadius: "0.75rem", backgroundColor: "#f97316", display: "flex" }}>
            <Boxes style={{ width: 22, height: 22, color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>
              {userInfo ? `Inventar - ${userInfo.full_name || userInfo.username}` : "Inventar global"}
            </h1>
            <p style={{ fontSize: "0.8125rem", color: "#94a3b8", margin: 0 }}>
              {userInfo ? userInfo.email : "Toate articolele de inventar inregistrate"}
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
          <Link href="/admin/inventory" style={{
            display: "flex", alignItems: "center", gap: "0.375rem",
            padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
            backgroundColor: "rgba(255,255,255,0.06)", textDecoration: "none",
            fontSize: "0.75rem", color: "#cbd5e1",
          }}>
            <X style={{ width: 12, height: 12 }} /> Vezi tot inventarul
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
            placeholder="Cauta dupa nume, SKU, categorie sau utilizator..."
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
            Niciun articol in inventar.
          </p>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <p style={{ color: "#94a3b8", fontSize: "0.75rem", margin: 0 }}>
                {filtered.length} articol{filtered.length === 1 ? "" : "e"} {search ? "(filtrate)" : "in total"}
              </p>
              <p style={{ color: "#94a3b8", fontSize: "0.75rem", margin: 0 }}>
                Total bucati: <strong style={{ color: "white" }}>{totals.units}</strong>
                {" · "}
                Valoare totala: <strong style={{ color: "white" }}>{formatMoney(totals.value)}</strong>
              </p>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#64748b", fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Articol</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>SKU</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Cantitate</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Pret achizitie</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Valoare</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Sursa</th>
                    {!userId && <th style={{ padding: "0.5rem 0.5rem" }}>Proprietar</th>}
                    <th style={{ padding: "0.5rem 0.5rem" }}>Achizitionat</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((it) => {
                    const lineValue = (Number(it.quantity) || 0) * (Number(it.purchase_price) || 0);
                    return (
                      <tr key={it.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                        <td style={{ padding: "0.625rem 0.5rem", color: "white" }}>
                          <div
                            title={it.name}
                            style={{ maxWidth: "260px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "help" }}
                          >
                            {it.name}
                          </div>
                          {it.category && (
                            <div style={{ fontSize: "0.6875rem", color: "#64748b" }}>{it.category}</div>
                          )}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", color: "#cbd5e1", fontFamily: "monospace", fontSize: "0.75rem" }}>
                          {it.sku || "-"}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "white", fontWeight: 500 }}>
                          {it.quantity}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "#cbd5e1" }}>
                          {formatMoney(it.purchase_price, it.currency)}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "white" }}>
                          {formatMoney(lineValue, it.currency)}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", color: "#cbd5e1" }}>{it.source || "-"}</td>
                        {!userId && (
                          <td style={{ padding: "0.625rem 0.5rem" }}>
                            <Link href={`/admin/inventory?user=${it.owner.id}`} style={{
                              color: "#93c5fd", textDecoration: "none", fontSize: "0.75rem",
                            }}>
                              {it.owner.full_name || it.owner.username}
                            </Link>
                          </td>
                        )}
                        <td style={{ padding: "0.625rem 0.5rem", color: "#64748b", fontSize: "0.6875rem" }}>
                          {it.purchased_at ? new Date(it.purchased_at).toLocaleDateString("ro-RO") : "-"}
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
