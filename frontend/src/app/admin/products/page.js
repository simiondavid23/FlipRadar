"use client";
import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { adminAPI } from "@/lib/api";
import {
  Package, ArrowLeft, Loader2, Search, User as UserIcon, X,
  ExternalLink,
} from "lucide-react";

const cardStyle = {
  backgroundColor: "var(--bg-card)",
  border: "1px solid var(--border-color)",
  borderRadius: "1rem",
  padding: "1.25rem",
};

export default function AdminProductsPage() {
  const searchParams = useSearchParams();
  const userId = searchParams.get("user");

  const [products, setProducts] = useState([]);
  const [userInfo, setUserInfo] = useState(null); // when scoped to one user
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
        const [productsRes, userRes] = await Promise.all([
          adminAPI.getProducts(params),
          userId ? adminAPI.getUser(userId).catch(() => null) : Promise.resolve(null),
        ]);
        if (!cancelled) {
          setProducts(productsRes.data);
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
    if (!search.trim()) return products;
    const q = search.toLowerCase();
    return products.filter((p) => {
      const name = (p.name || "").toLowerCase();
      const asin = (p.asin || "").toLowerCase();
      const ean = (p.ean || "").toLowerCase();
      const ownerEmail = (p.owner?.email || "").toLowerCase();
      return name.includes(q) || asin.includes(q) || ean.includes(q) || ownerEmail.includes(q);
    });
  }, [products, search]);

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.625rem", borderRadius: "0.75rem", backgroundColor: "#9333ea", display: "flex" }}>
            <Package style={{ width: 22, height: 22, color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>
              {userInfo ? `Produse - ${userInfo.full_name || userInfo.username}` : "Toate produsele"}
            </h1>
            <p style={{ fontSize: "0.8125rem", color: "#94a3b8", margin: 0 }}>
              {userInfo ? userInfo.email : "Produse inregistrate in baza de date"}
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

      {/* User-scope banner */}
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
          <Link href="/admin/products" style={{
            display: "flex", alignItems: "center", gap: "0.375rem",
            padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
            backgroundColor: "rgba(255,255,255,0.06)", textDecoration: "none",
            fontSize: "0.75rem", color: "#cbd5e1",
          }}>
            <X style={{ width: 12, height: 12 }} /> Vezi toate produsele
          </Link>
        </div>
      )}

      {/* Search */}
      <div style={{ ...cardStyle, marginBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", position: "relative" }}>
          <Search style={{ width: 16, height: 16, color: "#64748b", position: "absolute", left: "0.75rem" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cauta dupa nume, ASIN, EAN sau email proprietar..."
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

      {/* Table */}
      <div style={cardStyle}>
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
            <Loader2 style={{ width: 28, height: 28, color: "#60a5fa", animation: "spin 1s linear infinite" }} />
          </div>
        ) : error ? (
          <p style={{ color: "#fca5a5", fontSize: "0.875rem", textAlign: "center", padding: "2rem 0" }}>{error}</p>
        ) : filtered.length === 0 ? (
          <p style={{ color: "#64748b", fontSize: "0.875rem", textAlign: "center", padding: "2rem 0" }}>
            Niciun produs gasit.
          </p>
        ) : (
          <>
            <p style={{ color: "#94a3b8", fontSize: "0.75rem", margin: "0 0 0.75rem" }}>
              {filtered.length} produs{filtered.length === 1 ? "" : "e"} {search ? "(filtrate)" : "in total"}
            </p>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#64748b", fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Nume</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Sursa</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>ASIN / EAN</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Pret</th>
                    {!userId && <th style={{ padding: "0.5rem 0.5rem" }}>Proprietar</th>}
                    <th style={{ padding: "0.5rem 0.5rem" }}>Adaugat</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p) => (
                    <tr key={p.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                      <td style={{ padding: "0.625rem 0.5rem", color: "white" }}>
                        <div
                          title={p.name}
                          style={{ maxWidth: "280px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "help" }}
                        >
                          {p.name}
                        </div>
                        {p.category && (
                          <div style={{ fontSize: "0.6875rem", color: "#64748b" }}>{p.category}</div>
                        )}
                      </td>
                      <td style={{ padding: "0.625rem 0.5rem", color: "#cbd5e1" }}>{p.source || "-"}</td>
                      <td style={{ padding: "0.625rem 0.5rem", color: "#cbd5e1", fontFamily: "monospace", fontSize: "0.75rem" }}>
                        {p.asin || p.ean || "-"}
                      </td>
                      <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "white", fontWeight: 500 }}>
                        {p.current_price != null ? `${p.current_price} ${p.currency || ""}` : "-"}
                      </td>
                      {!userId && (
                        <td style={{ padding: "0.625rem 0.5rem" }}>
                          {p.owner ? (
                            <Link href={`/admin/products?user=${p.owner.id}`} style={{
                              color: "#93c5fd", textDecoration: "none", fontSize: "0.75rem",
                            }}>
                              {p.owner.full_name || p.owner.username}
                            </Link>
                          ) : (
                            <span style={{ color: "#64748b", fontSize: "0.75rem" }}>(fara proprietar)</span>
                          )}
                        </td>
                      )}
                      <td style={{ padding: "0.625rem 0.5rem", color: "#64748b", fontSize: "0.6875rem" }}>
                        {p.created_at ? new Date(p.created_at).toLocaleDateString("ro-RO") : "-"}
                      </td>
                      <td style={{ padding: "0.625rem 0.5rem", textAlign: "right" }}>
                        {p.source_url ? (
                          <a
                            href={p.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              color: "#60a5fa", textDecoration: "none", fontSize: "0.75rem",
                              display: "inline-flex", alignItems: "center", gap: "0.25rem",
                            }}
                            title={p.source_url}
                          >
                            Sursa <ExternalLink style={{ width: 12, height: 12 }} />
                          </a>
                        ) : (
                          <span style={{ color: "#64748b", fontSize: "0.75rem" }}>-</span>
                        )}
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
