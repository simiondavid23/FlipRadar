"use client";
import { useEffect, useState, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { adminAPI } from "@/lib/api";
import {
  Heart, Ban, ArrowLeft, Loader2, Search, User as UserIcon, X,
} from "lucide-react";

const cardStyle = {
  backgroundColor: "var(--bg-card)",
  border: "1px solid var(--border-color)",
  borderRadius: "1rem",
  padding: "1.25rem",
};

const KIND_TABS = [
  { key: "all",       label: "Toate",      color: "#64748b" },
  { key: "favorite",  label: "Favorite",   color: "#ec4899" },
  { key: "blacklist", label: "Blacklist",  color: "#dc2626" },
];

export default function AdminFavoritesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const userId = searchParams.get("user");
  const kindParam = searchParams.get("kind");
  const kind = KIND_TABS.some((t) => t.key === kindParam) ? kindParam : "all";

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
        const params = { kind };
        if (userId) params.user_id = Number(userId);
        const [itemsRes, userRes] = await Promise.all([
          adminAPI.getFavorites(params),
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
  }, [userId, kind]);

  const setKind = (nextKind) => {
    const qs = new URLSearchParams();
    if (userId) qs.set("user", userId);
    if (nextKind !== "all") qs.set("kind", nextKind);
    const query = qs.toString();
    router.push(query ? `/admin/favorites?${query}` : "/admin/favorites", { scroll: false });
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter((it) => {
      const name = (it.product?.name || "").toLowerCase();
      const sku = (it.product?.sku || "").toLowerCase();
      const ownerEmail = (it.owner?.email || "").toLowerCase();
      const ownerName = (it.owner?.full_name || it.owner?.username || "").toLowerCase();
      return name.includes(q) || sku.includes(q) || ownerEmail.includes(q) || ownerName.includes(q);
    });
  }, [items, search]);

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.625rem", borderRadius: "0.75rem", backgroundColor: "#ec4899", display: "flex" }}>
            <Heart style={{ width: 22, height: 22, color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>
              {userInfo ? `Favorite & Blacklist - ${userInfo.full_name || userInfo.username}` : "Favorite & Blacklist"}
            </h1>
            <p style={{ fontSize: "0.8125rem", color: "#94a3b8", margin: 0 }}>
              {userInfo ? userInfo.email : "Produsele marcate ca favorite sau puse pe blacklist"}
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
            href={kind === "all" ? "/admin/favorites" : `/admin/favorites?kind=${kind}`}
            style={{
              display: "flex", alignItems: "center", gap: "0.375rem",
              padding: "0.375rem 0.75rem", borderRadius: "0.375rem",
              backgroundColor: "rgba(255,255,255,0.06)", textDecoration: "none",
              fontSize: "0.75rem", color: "#cbd5e1",
            }}
          >
            <X style={{ width: 12, height: 12 }} /> Vezi toti utilizatorii
          </Link>
        </div>
      )}

      {/* Kind tabs */}
      <div style={{ ...cardStyle, marginBottom: "1rem", padding: "0.5rem" }}>
        <div style={{ display: "flex", gap: "0.25rem" }}>
          {KIND_TABS.map((t) => {
            const active = t.key === kind;
            return (
              <button
                key={t.key}
                onClick={() => setKind(t.key)}
                style={{
                  flex: 1,
                  padding: "0.625rem 1rem",
                  borderRadius: "0.5rem",
                  border: "1px solid " + (active ? t.color : "transparent"),
                  backgroundColor: active ? `${t.color}22` : "transparent",
                  color: active ? "white" : "#94a3b8",
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
          <Search style={{ width: 16, height: 16, color: "#64748b", position: "absolute", left: "0.75rem" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cauta dupa nume produs, SKU sau utilizator..."
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
            Niciun produs in aceasta categorie.
          </p>
        ) : (
          <>
            <p style={{ color: "#94a3b8", fontSize: "0.75rem", margin: "0 0 0.75rem" }}>
              {filtered.length} {filtered.length === 1 ? "produs" : "produse"} {search ? "(filtrate)" : "in total"}
            </p>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#64748b", fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Tip</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Produs</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>SKU / EAN</th>
                    <th style={{ padding: "0.5rem 0.5rem", textAlign: "right" }}>Pret</th>
                    {!userId && <th style={{ padding: "0.5rem 0.5rem" }}>Proprietar</th>}
                    <th style={{ padding: "0.5rem 0.5rem" }}>Note</th>
                    <th style={{ padding: "0.5rem 0.5rem" }}>Adaugat</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((it) => {
                    const isBlack = it.is_blacklisted;
                    const tagColor = isBlack ? "#dc2626" : "#ec4899";
                    const tagLabel = isBlack ? "Blacklist" : "Favorit";
                    const TagIcon = isBlack ? Ban : Heart;
                    return (
                      <tr key={it.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                        <td style={{ padding: "0.625rem 0.5rem" }}>
                          <span style={{
                            display: "inline-flex", alignItems: "center", gap: "0.25rem",
                            padding: "0.125rem 0.5rem", borderRadius: "0.375rem",
                            fontSize: "0.6875rem", fontWeight: 600,
                            backgroundColor: `${tagColor}22`, color: tagColor,
                          }}>
                            <TagIcon style={{ width: 10, height: 10 }} />
                            {tagLabel}
                          </span>
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", color: "white" }}>
                          <div
                            title={it.product?.name || "(produs sters)"}
                            style={{ maxWidth: "260px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "help" }}
                          >
                            {it.product?.name || "(produs sters)"}
                          </div>
                          {it.product?.source && (
                            <div style={{ fontSize: "0.6875rem", color: "#64748b" }}>{it.product.source}</div>
                          )}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", color: "#cbd5e1", fontFamily: "monospace", fontSize: "0.75rem" }}>
                          {it.product?.sku || it.product?.ean || "-"}
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", textAlign: "right", color: "white", fontWeight: 500 }}>
                          {it.product?.current_price != null
                            ? `${it.product.current_price} ${it.product.currency || ""}`
                            : "-"}
                        </td>
                        {!userId && (
                          <td style={{ padding: "0.625rem 0.5rem" }}>
                            <Link href={`/admin/favorites?user=${it.owner.id}${kind !== "all" ? `&kind=${kind}` : ""}`} style={{
                              color: "#93c5fd", textDecoration: "none", fontSize: "0.75rem",
                            }}>
                              {it.owner.full_name || it.owner.username}
                            </Link>
                          </td>
                        )}
                        <td style={{ padding: "0.625rem 0.5rem", color: "#94a3b8", fontSize: "0.75rem", maxWidth: "200px" }}>
                          <div
                            title={it.notes || ""}
                            style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: it.notes ? "help" : "default" }}
                          >
                            {it.notes || "-"}
                          </div>
                        </td>
                        <td style={{ padding: "0.625rem 0.5rem", color: "#64748b", fontSize: "0.6875rem" }}>
                          {it.added_at ? new Date(it.added_at).toLocaleDateString("ro-RO") : "-"}
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
