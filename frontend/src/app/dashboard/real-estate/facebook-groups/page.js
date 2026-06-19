"use client";
// FlipRadar — Imobiliare: monitorizare grupuri Facebook (config + cookies + test).
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { facebookGroupsAPI } from "@/lib/api";
import {
  Users, Plus, Trash2, Settings, Play, Eye, X, Loader2,
  ToggleLeft, ToggleRight, CheckCircle2, AlertTriangle, Clock,
} from "lucide-react";

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)", fontSize: "0.875rem", outline: "none",
};
const lbl = { display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" };
const EMPTY = { group_name: "", group_url: "", keywords: [], negative_keywords: [], check_interval_hours: 2 };

function relTime(iso) {
  if (!iso) return "niciodata";
  const min = (Date.now() - new Date(iso).getTime()) / 60000;
  if (min < 1) return "acum cateva secunde";
  if (min < 60) return `acum ${Math.round(min)} minute`;
  if (min < 1440) return `acum ${Math.round(min / 60)} ore`;
  return `acum ${Math.round(min / 1440)} zile`;
}

function cookieStatus(c) {
  if (c.last_run_status === "cookies_expirate") return { label: "Cookies expirate — reinnoire necesara", color: "#f87171", icon: AlertTriangle };
  if (!c.has_cookies || !c.cookies_saved_at) return { label: "Fara cookies", color: "var(--text-muted)", icon: AlertTriangle };
  const days = (Date.now() - new Date(c.cookies_saved_at).getTime()) / 86400000;
  if (days >= 53) return { label: "Cookies expira in curand", color: "#fb923c", icon: Clock };
  return { label: "Cookies active", color: "#4ade80", icon: CheckCircle2 };
}

function cookieDaysLeft(c) {
  if (!c.cookies_saved_at) return null;
  const days = 60 - Math.floor((Date.now() - new Date(c.cookies_saved_at).getTime()) / 86400000);
  return Math.max(0, days);
}

// Editor de pills (keywords / negative_keywords)
function PillEditor({ label, hint, placeholder, pills, color, onAdd, onRemove }) {
  const [val, setVal] = useState("");
  const add = () => { const v = val.trim(); if (v) { onAdd(v); setVal(""); } };
  return (
    <div>
      <label style={lbl}>{label}</label>
      <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", margin: "0 0 0.375rem" }}>{hint}</p>
      <div style={{ display: "flex", gap: "0.375rem" }}>
        <input value={val} onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder} style={inputStyle} />
        <button type="button" onClick={add} style={{ padding: "0.5rem 0.875rem", borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", color: "var(--text-primary)", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600 }}>Adauga</button>
      </div>
      {pills.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", marginTop: "0.5rem" }}>
          {pills.map((p) => (
            <span key={p} style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.75rem", fontWeight: 600, padding: "0.125rem 0.5rem", borderRadius: "0.375rem", backgroundColor: `${color}22`, color }}>
              {p}
              <X style={{ width: "12px", height: "12px", cursor: "pointer" }} onClick={() => onRemove(p)} />
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function FacebookGroupsPage() {
  const router = useRouter();
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  const [expandedId, setExpandedId] = useState(null);
  const [cookiesInput, setCookiesInput] = useState("");
  const [cookieBusy, setCookieBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await facebookGroupsAPI.getConfigs();
      setConfigs(res.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const openCreate = () => { setEditingId(null); setForm(EMPTY); setShowForm(true); };
  const openEdit = (c) => {
    setEditingId(c.id);
    setForm({
      group_name: c.group_name, group_url: c.group_url,
      keywords: c.keywords || [], negative_keywords: c.negative_keywords || [],
      check_interval_hours: c.check_interval_hours,
    });
    setShowForm(true);
  };

  const submit = async () => {
    if (!form.group_name.trim() || (!editingId && !form.group_url.trim())) {
      alert("Numele si URL-ul grupului sunt obligatorii.");
      return;
    }
    setSaving(true);
    try {
      if (editingId) {
        await facebookGroupsAPI.updateConfig(editingId, {
          group_name: form.group_name, keywords: form.keywords,
          negative_keywords: form.negative_keywords, check_interval_hours: form.check_interval_hours,
        });
      } else {
        await facebookGroupsAPI.createConfig(form);
      }
      setShowForm(false);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally { setSaving(false); }
  };

  const toggle = async (c) => {
    try {
      await facebookGroupsAPI.updateConfig(c.id, { is_active: !c.is_active });
      setConfigs((prev) => prev.map((x) => (x.id === c.id ? { ...x, is_active: !x.is_active } : x)));
    } catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };

  const remove = async (c) => {
    if (!confirm(`Stergi grupul "${c.group_name}" si toate postarile asociate?`)) return;
    try {
      await facebookGroupsAPI.deleteConfig(c.id);
      setConfigs((prev) => prev.filter((x) => x.id !== c.id));
    } catch (e) { alert(e.response?.data?.detail || "Eroare la stergere."); }
  };

  const openSettings = (c) => {
    setExpandedId(expandedId === c.id ? null : c.id);
    setCookiesInput("");
    setTestResult(null);
  };

  const saveCookies = async (c) => {
    if (!cookiesInput.trim()) { alert("Lipeste JSON-ul cu cookies."); return; }
    setCookieBusy(true);
    try {
      await facebookGroupsAPI.saveCookies(c.id, cookiesInput.trim());
      setCookiesInput("");
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvarea cookies.");
    } finally { setCookieBusy(false); }
  };

  const deleteCookies = async (c) => {
    if (!confirm("Stergi cookies-urile pentru acest grup?")) return;
    setCookieBusy(true);
    try {
      await facebookGroupsAPI.deleteCookies(c.id);
      await load();
    } catch (e) { alert(e.response?.data?.detail || "Eroare."); }
    finally { setCookieBusy(false); }
  };

  const testRun = async (c) => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await facebookGroupsAPI.testRun(c.id);
      const n = res.data?.new_posts ?? 0;
      setTestResult({ ok: true, text: n > 0 ? `S-au gasit ${n} postari noi.` : "Nicio postare noua." });
      await load();
    } catch (e) {
      setTestResult({ ok: false, text: e.response?.data?.detail || "Eroare la testare." });
    } finally { setTesting(false); }
  };

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", gap: "0.75rem", flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Users style={{ width: "22px", height: "22px", color: "#1877f2" }} /> Grupuri Facebook
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Monitorizeaza automat grupuri imobiliare si primesti notificari la postari noi relevante
          </p>
        </div>
        <button onClick={openCreate} style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.875rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer" }}>
          <Plus style={{ width: "16px", height: "16px" }} /> Adauga grup nou
        </button>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : configs.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)" }}>
          Nu ai grupuri configurate. Apasa „Adauga grup nou” ca sa incepi.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          {configs.map((c) => {
            const cs = cookieStatus(c);
            const CsIcon = cs.icon;
            const expanded = expandedId === c.id;
            return (
              <div key={c.id} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", overflow: "hidden" }}>
                <div style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "0.625rem" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap" }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                        <span style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>{c.group_name}</span>
                        {c.unread_count > 0 && (
                          <span style={{ fontSize: "0.6875rem", fontWeight: 700, color: "white", backgroundColor: "#fb923c", borderRadius: "999px", padding: "0.0625rem 0.5rem" }}>
                            {c.unread_count} noi
                          </span>
                        )}
                      </div>
                      <a href={c.group_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "0.75rem", color: "#60a5fa", textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block", maxWidth: "420px" }}>
                        {c.group_url}
                      </a>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                      <button onClick={() => router.push(`/dashboard/real-estate/facebook-groups/posts?config=${c.id}`)} style={iconBtn("#60a5fa")} title="Vezi postari">
                        <Eye style={{ width: "16px", height: "16px" }} />
                      </button>
                      <button onClick={() => openSettings(c)} style={iconBtn("var(--text-secondary)")} title="Setari">
                        <Settings style={{ width: "16px", height: "16px" }} />
                      </button>
                      <button onClick={() => openEdit(c)} style={iconBtn("var(--text-secondary)")} title="Editeaza">
                        <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>Edit</span>
                      </button>
                      <button onClick={() => toggle(c)} style={iconBtn(c.is_active ? "#4ade80" : "var(--text-muted)")} title={c.is_active ? "Pune pe pauza" : "Activeaza"}>
                        {c.is_active ? <ToggleRight style={{ width: "20px", height: "20px" }} /> : <ToggleLeft style={{ width: "20px", height: "20px" }} />}
                      </button>
                      <button onClick={() => remove(c)} style={iconBtn("#f87171")} title="Sterge">
                        <Trash2 style={{ width: "16px", height: "16px" }} />
                      </button>
                    </div>
                  </div>

                  {(c.keywords?.length > 0 || c.negative_keywords?.length > 0) && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                      {c.keywords.map((k) => (
                        <span key={`k-${k}`} style={pill("#4ade80")}>{k}</span>
                      ))}
                      {c.negative_keywords.map((k) => (
                        <span key={`n-${k}`} style={pill("#f87171")}>− {k}</span>
                      ))}
                    </div>
                  )}

                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.875rem", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    <span>{c.is_active ? `Activ · verifica la fiecare ${c.check_interval_hours}h` : "Pauza"}</span>
                    <span>Ultima verificare: {relTime(c.last_run_at)}</span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", color: cs.color, fontWeight: 600 }}>
                      <CsIcon style={{ width: "13px", height: "13px" }} /> {cs.label}
                    </span>
                  </div>
                </div>

                {/* Sectiunea B — cookies (expandabila) */}
                {expanded && (
                  <div style={{ borderTop: "1px solid var(--border-color)", padding: "1rem", backgroundColor: "var(--bg-dark)" }}>
                    <h3 style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)", margin: "0 0 0.5rem" }}>
                      Cum conectezi contul Facebook dedicat:
                    </h3>
                    <ol style={{ fontSize: "0.75rem", color: "var(--text-secondary)", margin: "0 0 0.875rem", paddingLeft: "1.25rem", lineHeight: 1.7 }}>
                      <li>Instaleaza extensia <strong>Cookie-Editor</strong> in Chrome sau Firefox.</li>
                      <li>Deschide facebook.com si logheaza-te cu contul dedicat FlipRadar.</li>
                      <li>Click pe extensia Cookie-Editor → Export → Export as JSON.</li>
                      <li>Copiaza tot textul JSON si lipeste-l mai jos:</li>
                    </ol>

                    <textarea value={cookiesInput} onChange={(e) => setCookiesInput(e.target.value)}
                      placeholder="Lipeste aici JSON-ul cu cookies..." rows={4}
                      style={{ ...inputStyle, resize: "vertical", fontFamily: "monospace", fontSize: "0.75rem" }} />
                    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
                      <button onClick={() => saveCookies(c)} disabled={cookieBusy} style={primaryBtn}>
                        {cookieBusy ? "Se salveaza..." : "Salveaza cookies"}
                      </button>
                      {c.has_cookies && (
                        <button onClick={() => deleteCookies(c)} disabled={cookieBusy} style={dangerBtn}>
                          <Trash2 style={{ width: "13px", height: "13px" }} /> Sterge cookies
                        </button>
                      )}
                      <button onClick={() => testRun(c)} disabled={testing || !c.has_cookies} style={{ ...secondaryBtn, opacity: c.has_cookies ? 1 : 0.5 }}>
                        <Play style={{ width: "13px", height: "13px" }} /> {testing ? "Se testeaza..." : "Testeaza acum"}
                      </button>
                    </div>

                    {c.has_cookies && c.cookies_saved_at && (
                      <p style={{ fontSize: "0.75rem", color: "#4ade80", margin: "0.625rem 0 0" }}>
                        Cookies active · Salvate pe {new Date(c.cookies_saved_at).toLocaleDateString("ro-RO")} · Valabile ~{cookieDaysLeft(c)} zile
                      </p>
                    )}
                    {testResult && (
                      <p style={{ fontSize: "0.8125rem", margin: "0.625rem 0 0", color: testResult.ok ? "#4ade80" : "#f87171" }}>
                        {testResult.text}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Modal creare/editare */}
      {showForm && (
        <div onClick={() => setShowForm(false)} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", zIndex: 100, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "3rem 1rem", overflowY: "auto" }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: "100%", maxWidth: "600px", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.875rem", padding: "1.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                {editingId ? "Editeaza grup" : "Adauga grup nou"}
              </h2>
              <button onClick={() => setShowForm(false)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}>
                <X style={{ width: "20px", height: "20px" }} />
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <label style={lbl}>Nume grup</label>
                <input value={form.group_name} onChange={(e) => setForm({ ...form, group_name: e.target.value })}
                  placeholder="ex: Imobiliare Bucuresti Sector 4" style={inputStyle} />
              </div>
              <div>
                <label style={lbl}>URL grup Facebook</label>
                <input value={form.group_url} onChange={(e) => setForm({ ...form, group_url: e.target.value })}
                  placeholder="https://www.facebook.com/groups/123456" disabled={!!editingId}
                  style={{ ...inputStyle, opacity: editingId ? 0.6 : 1 }} />
                {editingId && <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", margin: "0.25rem 0 0" }}>URL-ul nu poate fi modificat dupa creare.</p>}
              </div>

              <PillEditor
                label="Cuvinte cheie cautate (cel putin unul trebuie sa apara in postare)"
                hint="ex: garsoniera, 2 camere, sector 4"
                placeholder="garsoniera"
                pills={form.keywords} color="#4ade80"
                onAdd={(v) => setForm((f) => (f.keywords.includes(v) ? f : { ...f, keywords: [...f.keywords, v] }))}
                onRemove={(v) => setForm((f) => ({ ...f, keywords: f.keywords.filter((x) => x !== v) }))}
              />
              <PillEditor
                label="Cuvinte de exclus (daca apare oricare, postarea e ignorata)"
                hint="ex: caut, schimb, ofer"
                placeholder="caut"
                pills={form.negative_keywords} color="#f87171"
                onAdd={(v) => setForm((f) => (f.negative_keywords.includes(v) ? f : { ...f, negative_keywords: [...f.negative_keywords, v] }))}
                onRemove={(v) => setForm((f) => ({ ...f, negative_keywords: f.negative_keywords.filter((x) => x !== v) }))}
              />

              <div>
                <label style={lbl}>Verificare automata</label>
                <select value={form.check_interval_hours} onChange={(e) => setForm({ ...form, check_interval_hours: parseInt(e.target.value) })} style={inputStyle}>
                  <option value={1}>1 ora</option>
                  <option value={2}>2 ore</option>
                  <option value={4}>4 ore</option>
                </select>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1.5rem" }}>
              <button onClick={() => setShowForm(false)} style={secondaryBtn}>Anuleaza</button>
              <button onClick={submit} disabled={saving} style={primaryBtn}>
                {saving ? "Se salveaza..." : "Salveaza configuratia"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const iconBtn = (color) => ({ display: "inline-flex", alignItems: "center", gap: "0.25rem", background: "none", border: "none", cursor: "pointer", color, padding: "0.25rem" });
const pill = (color) => ({ fontSize: "0.7rem", fontWeight: 600, padding: "0.125rem 0.5rem", borderRadius: "0.375rem", backgroundColor: `${color}22`, color });
const primaryBtn = { display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600 };
const secondaryBtn = { display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500 };
const dangerBtn = { display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem", borderRadius: "0.5rem", backgroundColor: "transparent", color: "#f87171", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600 };
