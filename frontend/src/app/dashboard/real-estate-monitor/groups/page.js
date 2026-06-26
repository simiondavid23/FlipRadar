"use client";
import { useState, useEffect, useCallback } from "react";
import { facebookGroupsAPI, realEstateMonitorAPI } from "@/lib/api";
import { Users, Plus, Pencil, Trash2, ToggleLeft, ToggleRight, RefreshCw, X, ExternalLink } from "lucide-react";

const INTERVAL_OPTIONS = [
  { value: 0.5, label: "30 min" }, { value: 1, label: "1 oră" },
  { value: 2, label: "2 ore" }, { value: 4, label: "4 ore" }, { value: 6, label: "6 ore" },
];

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)", fontSize: "0.875rem", outline: "none",
};
const labelStyle = { display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" };

function toList(v) {
  if (Array.isArray(v)) return v;
  try { const p = JSON.parse(v || "[]"); return Array.isArray(p) ? p : []; } catch { return []; }
}

export default function REGroupsPage() {
  const [tab, setTab] = useState("groups");
  const [configs, setConfigs] = useState([]);
  const [posts, setPosts] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, st] = await Promise.all([
        facebookGroupsAPI.getConfigs().catch(() => ({ data: [] })),
        realEstateMonitorAPI.getStats().catch(() => ({ data: {} })),
      ]);
      setConfigs(c.data || []);
      setStats(st.data || {});
    } finally { setLoading(false); }
  }, []);

  const loadPosts = useCallback(async () => {
    try {
      const r = await realEstateMonitorAPI.getFeed({ platform: "facebook_groups", status: "active", limit: 100 });
      setPosts(r.data?.items || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === "posts") loadPosts(); }, [tab, loadPosts]);

  const toggleActive = async (cfg) => {
    try { await facebookGroupsAPI.updateConfig(cfg.id, { is_active: !cfg.is_active }); await load(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  const verifyNow = async (cfg) => {
    try { await facebookGroupsAPI.testRun(cfg.id); alert("Verificare pornită."); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  const remove = async (cfg) => {
    if (!confirm(`Ștergi grupul „${cfg.group_name}”?`)) return;
    try { await facebookGroupsAPI.deleteConfig(cfg.id); await load(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };

  const fbInvalid = stats.has_facebook_keywords && stats.facebook_session_valid === false;

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#2563eb", display: "flex" }}>
            <Users style={{ width: "20px", height: "20px", color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Grupuri Facebook — Chirii</h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", margin: 0 }}>Monitorizează postări din grupuri de închirieri</p>
          </div>
        </div>
        <button onClick={() => { setEditing(null); setShowModal(true); }} style={{
          display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem",
          backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
        }}><Plus style={{ width: "16px", height: "16px" }} /> Adaugă grup</button>
      </div>

      {fbInvalid && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.75rem 1rem", marginBottom: "1.25rem", backgroundColor: "rgba(245,158,11,0.08)", border: "0.5px solid rgba(245,158,11,0.3)", borderRadius: "0.625rem" }}>
          <span style={{ fontSize: "1.125rem" }}>⚠️</span>
          <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>
            Sesiunea Facebook a expirat. Reautentifică-te din <a href="/dashboard/settings" style={{ color: "#fbbf24", fontWeight: 500 }}>Setări → Facebook</a>.
          </p>
        </div>
      )}

      <div style={{ display: "inline-flex", gap: "0.25rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", padding: "0.25rem", marginBottom: "1.25rem" }}>
        {[{ k: "groups", l: `Grupuri configurate (${configs.length})` }, { k: "posts", l: `Feed posturi noi (${posts.length})` }].map((t) => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{ padding: "0.375rem 0.875rem", borderRadius: "0.375rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer", border: "none", backgroundColor: tab === t.k ? "rgba(37,99,235,0.15)" : "transparent", color: tab === t.k ? "#60a5fa" : "var(--text-secondary)" }}>{t.l}</button>
        ))}
      </div>

      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>Se încarcă...</div>
      ) : tab === "groups" ? (
        configs.length === 0 ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem" }}>
            Niciun grup configurat. Apasă „Adaugă grup”.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
            {configs.map((cfg) => {
              const kws = toList(cfg.keywords); const negs = toList(cfg.negative_keywords);
              return (
                <div key={cfg.id} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.75rem", flexWrap: "wrap" }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)" }}>{cfg.group_name}</div>
                      <a href={cfg.group_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "0.75rem", color: "#60a5fa", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                        {String(cfg.group_url).slice(0, 50)} <ExternalLink style={{ width: "11px", height: "11px" }} />
                      </a>
                    </div>
                    <span style={{ fontSize: "0.6875rem", fontWeight: 600, padding: "0.125rem 0.5rem", borderRadius: "999px", color: cfg.is_active ? "#4ade80" : "var(--text-muted)", backgroundColor: cfg.is_active ? "rgba(34,197,94,0.15)" : "var(--bg-dark)" }}>
                      {cfg.is_active ? "Activ" : "Inactiv"}
                    </span>
                  </div>
                  {(kws.length > 0 || negs.length > 0) && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem", marginTop: "0.5rem" }}>
                      {kws.map((w) => <span key={`k${w}`} style={{ fontSize: "0.6875rem", padding: "0.125rem 0.4rem", borderRadius: "0.25rem", backgroundColor: "rgba(34,197,94,0.12)", color: "#86efac" }}>{w}</span>)}
                      {negs.map((w) => <span key={`n${w}`} style={{ fontSize: "0.6875rem", padding: "0.125rem 0.4rem", borderRadius: "0.25rem", backgroundColor: "rgba(239,68,68,0.12)", color: "#fca5a5" }}>−{w}</span>)}
                    </div>
                  )}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
                    <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                      Interval: {cfg.check_interval_hours}h · Ultima verificare: {cfg.last_run_at ? new Date(cfg.last_run_at).toLocaleString("ro-RO") : "niciodată"}
                      {cfg.last_run_status ? ` · ${cfg.last_run_status}` : ""}
                    </div>
                    <div style={{ display: "flex", gap: "0.375rem" }}>
                      <button onClick={() => { setEditing(cfg); setShowModal(true); }} title="Editează" style={iconBtn}><Pencil style={{ width: "14px", height: "14px" }} /></button>
                      <button onClick={() => verifyNow(cfg)} title="Verifică acum" style={iconBtn}><RefreshCw style={{ width: "14px", height: "14px" }} /></button>
                      <button onClick={() => toggleActive(cfg)} title={cfg.is_active ? "Dezactivează" : "Activează"} style={{ ...iconBtn, color: cfg.is_active ? "#4ade80" : "var(--text-muted)" }}>
                        {cfg.is_active ? <ToggleRight style={{ width: "16px", height: "16px" }} /> : <ToggleLeft style={{ width: "16px", height: "16px" }} />}
                      </button>
                      <button onClick={() => remove(cfg)} title="Șterge" style={{ ...iconBtn, color: "#f87171" }}><Trash2 style={{ width: "14px", height: "14px" }} /></button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )
      ) : (
        posts.length === 0 ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem" }}>
            Niciun post nou din grupuri. Postările apar după scanare.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
            {posts.map((p) => (
              <div key={p.id} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.625rem", padding: "0.875rem 1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                  <div style={{ fontSize: "0.875rem", color: "var(--text-primary)", fontWeight: 600 }}>
                    {p.price ? `${Math.round(p.price).toLocaleString("ro-RO")} ${p.currency}/lună` : "Preț necunoscut"}
                    {p.grade && <span style={{ marginLeft: "0.5rem", fontSize: "0.6875rem", color: "#60a5fa" }}>[{p.grade}]</span>}
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                    {[p.rooms && `${p.rooms} cam`, p.area_sqm && `${p.area_sqm} mp`, p.zone_normalized].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.375rem", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{p.description || p.title}</div>
                {p.url && <a href={p.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "0.75rem", color: "#60a5fa", textDecoration: "none" }}>Deschide grupul →</a>}
              </div>
            ))}
          </div>
        )
      )}

      {showModal && <GroupModal config={editing} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

const iconBtn = {
  display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "0.375rem",
  backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.375rem",
  color: "var(--text-secondary)", cursor: "pointer",
};

function GroupModal({ config, onClose, onSaved }) {
  const [groupUrl, setGroupUrl] = useState(config?.group_url || "");
  const [groupName, setGroupName] = useState(config?.group_name || "");
  const [kw, setKw] = useState(toList(config?.keywords));
  const [neg, setNeg] = useState(toList(config?.negative_keywords));
  const [interval, setInterval] = useState(config?.check_interval_hours ?? 2);
  const [notify, setNotify] = useState(config?.notify_discord ?? false);
  const [kwInput, setKwInput] = useState("");
  const [negInput, setNegInput] = useState("");
  const [saving, setSaving] = useState(false);

  const addChip = (val, list, setList, setInput) => {
    const v = (val || "").trim();
    if (v && !list.includes(v)) setList([...list, v]);
    setInput("");
  };

  const submit = async () => {
    if (!groupUrl.trim() || !groupName.trim()) { alert("URL și nume sunt obligatorii."); return; }
    const payload = {
      group_url: groupUrl, group_name: groupName,
      keywords: kw, negative_keywords: neg,
      check_interval_hours: parseFloat(interval), notify_discord: notify,
    };
    setSaving(true);
    try {
      if (config) await facebookGroupsAPI.updateConfig(config.id, payload);
      else await facebookGroupsAPI.createConfig(payload);
      onSaved();
    } catch (e) { alert(e.response?.data?.detail || "Eroare la salvare."); }
    finally { setSaving(false); }
  };

  const chipBox = (list, setList) => (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem", marginTop: "0.375rem" }}>
      {list.map((w) => (
        <span key={w} style={{ fontSize: "0.6875rem", padding: "0.125rem 0.4rem", borderRadius: "0.25rem", backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
          {w}<button onClick={() => setList(list.filter((x) => x !== w))} style={{ background: "none", border: "none", color: "#f87171", cursor: "pointer", padding: 0 }}>×</button>
        </span>
      ))}
    </div>
  );

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1.5rem" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.875rem", width: "100%", maxWidth: "560px", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "1.25rem", borderBottom: "1px solid var(--border-color)" }}>
          <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>{config ? "Editează grup" : "Adaugă grup"}</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}><X style={{ width: "20px", height: "20px" }} /></button>
        </div>
        <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div><label style={labelStyle}>URL grup *</label><input value={groupUrl} onChange={(e) => setGroupUrl(e.target.value)} placeholder="https://www.facebook.com/groups/..." style={inputStyle} /></div>
          <div><label style={labelStyle}>Nume afișat *</label><input value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="ex: Chirii București" style={inputStyle} /></div>
          <div>
            <label style={labelStyle}>Keyword-uri incluse</label>
            <input value={kwInput} onChange={(e) => setKwInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addChip(kwInput, kw, setKw, setKwInput); } }} placeholder="Scrie și Enter" style={inputStyle} />
            {chipBox(kw, setKw)}
          </div>
          <div>
            <label style={labelStyle}>Keyword-uri excluse</label>
            <input value={negInput} onChange={(e) => setNegInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addChip(negInput, neg, setNeg, setNegInput); } }} placeholder="Scrie și Enter" style={inputStyle} />
            {chipBox(neg, setNeg)}
          </div>
          <div>
            <label style={labelStyle}>Interval verificare</label>
            <select value={interval} onChange={(e) => setInterval(e.target.value)} style={inputStyle}>
              {INTERVAL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-primary)", cursor: "pointer" }}>
            <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} style={{ width: "auto" }} /> Notificări Discord
          </label>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", padding: "1rem 1.25rem", borderTop: "1px solid var(--border-color)" }}>
          <button onClick={onClose} style={{ padding: "0.5rem 1rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 500, cursor: "pointer" }}>Anulează</button>
          <button onClick={submit} disabled={saving} style={{ padding: "0.5rem 1.25rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: saving ? "wait" : "pointer", opacity: saving ? 0.7 : 1 }}>
            {saving ? "Se salvează..." : config ? "Salvează" : "Adaugă"}
          </button>
        </div>
      </div>
    </div>
  );
}
