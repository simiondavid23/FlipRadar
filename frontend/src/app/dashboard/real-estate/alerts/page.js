"use client";
// FlipRadar — Imobiliare: alerte (monitorizare automata la 30 min).
import { useState, useEffect } from "react";
import { realEstateAPI } from "@/lib/api";
import { RE_PLATFORMS, TIP_ANUNT, TIP_PROPRIETATE, rePlatformLabel } from "@/lib/realEstateConstants";
import { Bell, Plus, Trash2, ToggleLeft, ToggleRight, Loader2, X, Clock } from "lucide-react";

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)", fontSize: "0.875rem", outline: "none",
};
const lbl = { display: "block", fontSize: "0.7rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.25rem" };

// "2,3" sau "2-3" sau "2" -> { camere_min, camere_max }
function parseCamere(text) {
  const nums = String(text || "").match(/\d+/g);
  if (!nums || !nums.length) return {};
  const vals = nums.map(Number);
  return { camere_min: Math.min(...vals), camere_max: Math.max(...vals) };
}

function filtersSummary(a) {
  const f = a.filters || {};
  const parts = [];
  if (f.camere_min != null) parts.push(f.camere_max && f.camere_max !== f.camere_min ? `${f.camere_min}-${f.camere_max} cam` : `${f.camere_min} cam`);
  if (f.pret_min != null || f.pret_max != null) parts.push(`${f.pret_min ?? "?"}-${f.pret_max ?? "?"} EUR`);
  if (f.locatie) parts.push(f.locatie);
  if (Array.isArray(f.keywords) && f.keywords.length) parts.push(`"${f.keywords.join(", ")}"`);
  return parts.join(" · ");
}

const EMPTY = { platform: "olx", tip_anunt: "vanzare", tip_proprietate: "apartament", camere: "", pret_min: "", pret_max: "", locatie: "", keywords: "" };

export default function RealEstateAlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await realEstateAPI.getAlerts();
      setAlerts(res.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const setF = (k, v) => setForm((prev) => ({ ...prev, [k]: v }));

  const submit = async () => {
    const filters = {};
    Object.assign(filters, parseCamere(form.camere));
    if (form.pret_min) filters.pret_min = parseFloat(form.pret_min);
    if (form.pret_max) filters.pret_max = parseFloat(form.pret_max);
    if (form.locatie.trim()) filters.locatie = form.locatie.trim();
    const kw = form.keywords.split(",").map((k) => k.trim()).filter(Boolean);
    if (kw.length) filters.keywords = kw;

    setSaving(true);
    try {
      await realEstateAPI.createAlert({
        platform: form.platform,
        tip_anunt: form.tip_anunt,
        tip_proprietate: form.tip_proprietate,
        filters,
        is_active: true,
      });
      setShowModal(false);
      setForm(EMPTY);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvarea alertei.");
    } finally { setSaving(false); }
  };

  const toggle = async (a) => {
    try {
      const res = await realEstateAPI.updateAlert(a.id, { is_active: !a.is_active });
      setAlerts((prev) => prev.map((x) => (x.id === a.id ? res.data : x)));
    } catch (e) { alert(e.response?.data?.detail || "Eroare la actualizare."); }
  };

  const remove = async (a) => {
    if (!confirm("Stergi alerta?")) return;
    try {
      await realEstateAPI.deleteAlert(a.id);
      setAlerts((prev) => prev.filter((x) => x.id !== a.id));
    } catch (e) { alert(e.response?.data?.detail || "Eroare la stergere."); }
  };

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", gap: "0.75rem", flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Bell style={{ width: "22px", height: "22px", color: "#fbbf24" }} /> Alerte Imobiliare
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Monitorizare automata la fiecare 30 de minute — primesti notificari cand apar anunturi noi
          </p>
        </div>
        <button onClick={() => { setForm(EMPTY); setShowModal(true); }} style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.875rem",
          backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem",
          fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
        }}>
          <Plus style={{ width: "16px", height: "16px" }} /> Adauga alerta
        </button>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 style={{ width: "2rem", height: "2rem", color: "var(--blue-primary)", animation: "spin 1s linear infinite" }} />
        </div>
      ) : alerts.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", color: "var(--text-secondary)" }}>
          Nu ai alerte imobiliare. Apasa „Adauga alerta” ca sa incepi.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
          {alerts.map((a) => {
            const summary = filtersSummary(a);
            return (
              <div key={a.id} style={{
                backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem",
                padding: "0.875rem 1rem", display: "flex", alignItems: "center", gap: "0.875rem", opacity: a.is_active ? 1 : 0.6,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.25rem" }}>
                    <span style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", textTransform: "capitalize" }}>
                      {a.tip_proprietate || "imobil"} {a.tip_anunt || ""}
                    </span>
                    <span style={{ fontSize: "0.6875rem", fontWeight: 700, color: "var(--blue-light)", backgroundColor: "var(--blue-dim)", padding: "0.0625rem 0.5rem", borderRadius: "0.375rem" }}>
                      {a.platform === "toate" ? "Toate platformele" : rePlatformLabel(a.platform)}
                    </span>
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{summary || "Fara filtre suplimentare"}</div>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: "0.25rem", marginTop: "0.25rem" }}>
                    <Clock style={{ width: "11px", height: "11px" }} /> Verificare automata la 30 min
                  </div>
                </div>
                <button onClick={() => toggle(a)} title={a.is_active ? "Dezactiveaza" : "Activeaza"}
                  style={{ background: "none", border: "none", cursor: "pointer", color: a.is_active ? "#4ade80" : "var(--text-muted)", display: "flex" }}>
                  {a.is_active ? <ToggleRight style={{ width: "28px", height: "28px" }} /> : <ToggleLeft style={{ width: "28px", height: "28px" }} />}
                </button>
                <button onClick={() => remove(a)} title="Sterge" style={{ background: "none", border: "none", cursor: "pointer", color: "#f87171", display: "flex" }}>
                  <Trash2 style={{ width: "18px", height: "18px" }} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal adaugare alerta */}
      {showModal && (
        <div onClick={() => setShowModal(false)} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", zIndex: 100, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "3rem 1rem", overflowY: "auto" }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: "100%", maxWidth: "560px", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.875rem", padding: "1.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
              <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Adauga alerta imobiliara</h2>
              <button onClick={() => setShowModal(false)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}>
                <X style={{ width: "20px", height: "20px" }} />
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              <div>
                <label style={lbl}>Platforma</label>
                <select value={form.platform} onChange={(e) => setF("platform", e.target.value)} style={inputStyle}>
                  <option value="toate">Toate platformele</option>
                  {RE_PLATFORMS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <div>
                  <label style={lbl}>Tip anunt</label>
                  <select value={form.tip_anunt} onChange={(e) => setF("tip_anunt", e.target.value)} style={inputStyle}>
                    {TIP_ANUNT.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
                <div>
                  <label style={lbl}>Tip proprietate</label>
                  <select value={form.tip_proprietate} onChange={(e) => setF("tip_proprietate", e.target.value)} style={inputStyle}>
                    {TIP_PROPRIETATE.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem" }}>
                <div><label style={lbl}>Camere (ex: 2,3)</label><input value={form.camere} onChange={(e) => setF("camere", e.target.value)} placeholder="2,3 sau 2-3" style={inputStyle} /></div>
                <div><label style={lbl}>Pret min (EUR)</label><input type="number" value={form.pret_min} onChange={(e) => setF("pret_min", e.target.value)} style={inputStyle} /></div>
                <div><label style={lbl}>Pret max (EUR)</label><input type="number" value={form.pret_max} onChange={(e) => setF("pret_max", e.target.value)} style={inputStyle} /></div>
              </div>
              <div><label style={lbl}>Locatie</label><input value={form.locatie} onChange={(e) => setF("locatie", e.target.value)} placeholder="ex: Cluj-Napoca" style={inputStyle} /></div>
              <div><label style={lbl}>Keywords (optional, cautate in titlu/descriere)</label><input value={form.keywords} onChange={(e) => setF("keywords", e.target.value)} placeholder="ex: renovat, mobilat" style={inputStyle} /></div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1.5rem" }}>
              <button onClick={() => setShowModal(false)} style={{ padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500 }}>Anuleaza</button>
              <button onClick={submit} disabled={saving} style={{ padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", cursor: saving ? "wait" : "pointer", fontSize: "0.8125rem", fontWeight: 600 }}>
                {saving ? "Se salveaza..." : "Salveaza alerta"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
