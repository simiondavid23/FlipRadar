"use client";
// FlipRadar — Imobiliare: postari extrase din grupuri Facebook.
import { Suspense, useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { facebookGroupsAPI } from "@/lib/api";
import { Users, Loader2, ExternalLink, MapPin } from "lucide-react";

const GROUP_COLORS = ["#1877f2", "#0f9d58", "#7c3aed", "#e11d48", "#f59e0b", "#16a34a", "#0891b2", "#db2777"];
const colorFor = (id) => GROUP_COLORS[(Number(id) || 0) % GROUP_COLORS.length];

const FILTERS = [
  { key: "all", label: "Toate" },
  { key: "vanzare", label: "Vanzare" },
  { key: "inchiriere", label: "Inchiriere" },
  { key: "cu-pret", label: "Cu pret" },
  { key: "garsoniera", label: "Garsoniera" },
  { key: "2 camere", label: "2 camere" },
  { key: "3 camere", label: "3 camere" },
];

function postedRel(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const h = (Date.now() - d.getTime()) / 3600000;
  if (h < 1) return "acum cateva minute";
  if (h < 24) return `acum ${Math.round(h)}h`;
  if (h < 48) return "ieri";
  return d.toLocaleDateString("ro-RO", { day: "numeric", month: "short" });
}

function matchesFilter(p, f) {
  if (f === "all") return true;
  if (f === "vanzare") return p.tip_anunt === "vanzare";
  if (f === "inchiriere") return p.tip_anunt === "inchiriere";
  if (f === "cu-pret") return p.pret != null;
  return p.tip_proprietate === f; // garsoniera / 2 camere / 3 camere
}

function PostsContent() {
  const searchParams = useSearchParams();
  const initialConfig = searchParams.get("config") || "all";

  const [configs, setConfigs] = useState([]);
  const [selected, setSelected] = useState(initialConfig);
  const [filter, setFilter] = useState("all");
  const [posts, setPosts] = useState([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(new Set());

  useEffect(() => {
    facebookGroupsAPI.getConfigs().then((r) => setConfigs(r.data || [])).catch(() => {});
  }, []);

  const fetchPage = useCallback(async (pg, reset) => {
    setLoading(true);
    try {
      const res = selected === "all"
        ? await facebookGroupsAPI.getAllPosts({ page: pg, per_page: 20 })
        : await facebookGroupsAPI.getPosts(selected, { page: pg, per_page: 20 });
      const data = res.data || {};
      setPosts((prev) => (reset ? (data.posts || []) : [...prev, ...(data.posts || [])]));
      setHasMore(!!data.has_more);
      setPage(pg);
    } catch (e) {
      console.error(e);
      if (reset) setPosts([]);
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => { fetchPage(1, true); }, [fetchPage]);

  const shown = posts.filter((p) => matchesFilter(p, filter));
  const selectedName = selected !== "all" ? configs.find((c) => String(c.id) === String(selected))?.group_name : null;
  const toggleExpand = (id) => setExpanded((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto" }}>
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Users style={{ width: "22px", height: "22px", color: "#1877f2" }} /> Postari din grupuri Facebook
        </h1>
        {selectedName && (
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>{selectedName}</p>
        )}
      </div>

      {/* Selector grup */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.875rem", flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>Grup:</span>
        <select value={selected} onChange={(e) => setSelected(e.target.value)}
          style={{ backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", padding: "0.4rem 0.75rem", color: "var(--text-primary)", fontSize: "0.8125rem", outline: "none" }}>
          <option value="all">Toate grupurile</option>
          {configs.map((c) => <option key={c.id} value={c.id}>{c.group_name}</option>)}
        </select>
      </div>

      {/* Filtre rapide */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1.25rem" }}>
        {FILTERS.map((f) => {
          const active = filter === f.key;
          return (
            <button key={f.key} onClick={() => setFilter(f.key)} style={{
              padding: "0.3rem 0.75rem", borderRadius: "999px", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
              border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}`,
              backgroundColor: active ? "var(--blue-primary)" : "transparent",
              color: active ? "white" : "var(--text-secondary)",
            }}>{f.label}</button>
          );
        })}
      </div>

      {loading && posts.length === 0 ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : shown.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)" }}>
          Nicio postare {filter !== "all" ? "pentru acest filtru" : "inca"}. Postarile apar dupa ce grupurile sunt verificate automat.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {shown.map((p) => {
            const accent = colorFor(p.config_id);
            const facils = (p.facilitati || "").split(",").map((s) => s.trim()).filter(Boolean);
            const isExp = expanded.has(p.id);
            const text = p.text || "";
            const short = text.length > 200 && !isExp ? text.slice(0, 200) + "…" : text;
            return (
              <div key={p.id} style={{
                backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
                borderLeft: `3px solid ${p.is_read ? "var(--border-color)" : "#fb923c"}`,
                borderRadius: "0.75rem", padding: "1rem",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
                  <span style={{ fontSize: "0.6875rem", fontWeight: 700, color: "white", backgroundColor: accent, padding: "0.0625rem 0.5rem", borderRadius: "0.375rem" }}>
                    {p.group_name || "Grup"}
                  </span>
                  {!p.is_read && <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#fb923c" }} />}
                  <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{postedRel(p.posted_at || p.created_at)}</span>
                </div>

                {/* Date extrase */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", marginBottom: "0.5rem" }}>
                  {p.pret != null && (
                    <span style={{ fontSize: "1.0625rem", fontWeight: 700, color: "#4ade80" }}>
                      {Number(p.pret).toLocaleString("ro-RO")} {p.moneda || ""}{p.tip_anunt === "inchiriere" ? "/luna" : ""}
                    </span>
                  )}
                  {(p.tip_proprietate || p.suprafata_mp) && (
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-primary)", textTransform: "capitalize" }}>
                      {[p.tip_proprietate, p.suprafata_mp ? `${p.suprafata_mp} mp` : null].filter(Boolean).join(" · ")}
                    </span>
                  )}
                  {(p.zona || p.etaj) && (
                    <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                      <MapPin style={{ width: "12px", height: "12px" }} />
                      {[p.zona, p.etaj].filter(Boolean).join(" · ")}
                    </span>
                  )}
                  {facils.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem", marginTop: "0.125rem" }}>
                      {facils.map((f) => (
                        <span key={f} style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.375rem", padding: "0.0625rem 0.375rem" }}>{f}</span>
                      ))}
                    </div>
                  )}
                </div>

                {text && (
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0 0 0.5rem", whiteSpace: "pre-wrap", lineHeight: 1.55 }}>
                    {short}
                    {text.length > 200 && (
                      <button onClick={() => toggleExpand(p.id)} style={{ marginLeft: "0.375rem", background: "none", border: "none", color: "#60a5fa", cursor: "pointer", fontSize: "0.8125rem", padding: 0 }}>
                        {isExp ? "Mai putin" : "Citeste mai mult"}
                      </button>
                    )}
                  </p>
                )}

                {p.group_url && (
                  <a href={p.group_url} target="_blank" rel="noopener noreferrer"
                    style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", fontSize: "0.75rem", fontWeight: 600, color: "#60a5fa", textDecoration: "none" }}>
                    <ExternalLink style={{ width: "13px", height: "13px" }} /> Deschide pe Facebook
                  </a>
                )}
              </div>
            );
          })}

          {hasMore && (
            <div style={{ display: "flex", justifyContent: "center", paddingTop: "0.5rem" }}>
              <button onClick={() => fetchPage(page + 1, false)} disabled={loading}
                style={{ padding: "0.5rem 1.5rem", borderRadius: "0.5rem", backgroundColor: "transparent", border: "1px solid var(--border-color)", color: "var(--text-secondary)", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600 }}>
                {loading ? "Se incarca..." : "Incarca mai multe"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function FacebookGroupsPostsPage() {
  return (
    <Suspense fallback={<div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}><Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} /></div>}>
      <PostsContent />
    </Suspense>
  );
}
