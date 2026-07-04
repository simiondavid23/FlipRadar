"use client";
import { useState, useEffect, useCallback } from "react";
import { autoLotKeywordsAPI } from "@/lib/api";
import { Car, Plus, Pencil, Trash2, ToggleLeft, ToggleRight, X } from "lucide-react";
import { inputStyle, labelStyle } from "@/lib/uiStyles";
import ScanNowButton from "@/components/shared/ScanNowButton";

const LOT_PLATFORMS = [
  { value: "copart", label: "Copart" },
  { value: "iaai", label: "IAAI" },
  { value: "sca", label: "SCA" },
  { value: "openlane", label: "OpenLane" },
];

const POLL_OPTIONS = [15, 30, 60, 120];

const EMPTY_FORM = {
  name: "", platform: "copart", make: "", model: "",
  year_from: "", year_to: "", damage_primary: "", bid_max: "", location_state: "",
  is_active: true, notify_email: false, notify_discord: false,
  use_active_hours: false, active_hours_start: 8, active_hours_end: 22,
  polling_interval: 15,
};

const td = { padding: "0.625rem 0.75rem", fontSize: "0.8125rem", color: "var(--text-primary)", verticalAlign: "middle" };
const iconBtn = {
  display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "0.375rem",
  backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.375rem",
  color: "var(--text-secondary)", cursor: "pointer",
};

export default function AutoLotKeywordsPage() {
  const [keywords, setKeywords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await autoLotKeywordsAPI.getKeywords();
      setKeywords(r.data || []);
    } catch (e) {
      console.error("[AutoLotKeywords]", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleScanNow = async () => {
    setScanning(true);
    try {
      await autoLotKeywordsAPI.scanNow();
      setTimeout(() => setScanning(false), 3000);
    } catch {
      setScanning(false);
    }
  };

  const openAdd = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowModal(true);
  };

  const openEdit = (kw) => {
    setEditingId(kw.id);
    setForm({
      name: kw.name || "", platform: kw.platform || "copart",
      make: kw.make || "", model: kw.model || "",
      year_from: kw.year_from ?? "", year_to: kw.year_to ?? "",
      damage_primary: kw.damage_primary || "", bid_max: kw.bid_max ?? "",
      location_state: kw.location_state || "",
      is_active: kw.is_active, notify_email: kw.notify_email, notify_discord: kw.notify_discord,
      use_active_hours: kw.active_hours_start != null && kw.active_hours_end != null,
      active_hours_start: kw.active_hours_start ?? 8, active_hours_end: kw.active_hours_end ?? 22,
      polling_interval: kw.polling_interval_minutes ?? 15,
    });
    setShowModal(true);
  };

  const submit = async () => {
    if (!form.name.trim()) { alert("Numele keyword-ului este obligatoriu."); return; }
    const payload = {
      name: form.name,
      platform: form.platform,
      make: form.make || null,
      model: form.model || null,
      year_from: form.year_from ? parseInt(form.year_from) : null,
      year_to: form.year_to ? parseInt(form.year_to) : null,
      damage_primary: form.damage_primary || null,
      bid_max: form.bid_max ? parseFloat(form.bid_max) : null,
      location_state: form.location_state || null,
      is_active: form.is_active,
      notify_email: form.notify_email,
      notify_discord: form.notify_discord,
      active_hours_start: form.use_active_hours ? form.active_hours_start : null,
      active_hours_end: form.use_active_hours ? form.active_hours_end : null,
      polling_interval_minutes: parseInt(form.polling_interval) || 15,
    };
    setSaving(true);
    try {
      if (editingId) await autoLotKeywordsAPI.updateKeyword(editingId, payload);
      else await autoLotKeywordsAPI.createKeyword(payload);
      setShowModal(false);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (kw) => {
    try {
      await autoLotKeywordsAPI.updateKeyword(kw.id, {
        name: kw.name, platform: kw.platform, make: kw.make, model: kw.model,
        year_from: kw.year_from, year_to: kw.year_to, damage_primary: kw.damage_primary,
        bid_max: kw.bid_max != null ? parseFloat(kw.bid_max) : null,
        location_state: kw.location_state, is_active: !kw.is_active,
        notify_email: kw.notify_email, notify_discord: kw.notify_discord,
        active_hours_start: kw.active_hours_start, active_hours_end: kw.active_hours_end,
        polling_interval_minutes: kw.polling_interval_minutes,
      });
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la actualizare.");
    }
  };

  const remove = async (kw) => {
    if (!confirm(`Ștergi keyword-ul „${kw.name}”? Loturile deja găsite rămân în feed.`)) return;
    try { await autoLotKeywordsAPI.deleteKeyword(kw.id); await load(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare la ștergere."); }
  };

  const platLabel = (v) => LOT_PLATFORMS.find((p) => p.value === v)?.label || v;

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#2563eb", display: "flex" }}>
            <Car style={{ width: "20px", height: "20px", color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Keyword-uri Loturi</h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", margin: 0 }}>
              Monitorizare loturi din licitații pe {LOT_PLATFORMS.length} platforme ({keywords.length} keyword-uri)
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <ScanNowButton onScan={handleScanNow} scanning={scanning} label="Scanează acum" />
          <button onClick={openAdd} style={{
            display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem",
            backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem",
            fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
          }}>
            <Plus style={{ width: "16px", height: "16px" }} /> Adaugă Keyword
          </button>
        </div>
      </div>

      {/* Table */}
      <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>Se încarcă...</div>
        ) : keywords.length === 0 ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Niciun keyword încă. Apasă „Adaugă Keyword” pentru a începe monitorizarea loturilor.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ backgroundColor: "var(--bg-dark)" }}>
                {["Nume", "Platformă", "Mașină", "Bid max", "Interval", "Activ", ""].map((h) => (
                  <th key={h} style={{ ...td, fontWeight: 600, color: "var(--text-secondary)", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.03em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {keywords.map((k) => (
                <tr key={k.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                  <td style={td}><div style={{ fontWeight: 500 }}>{k.name}</div></td>
                  <td style={td}>
                    <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "#60a5fa", backgroundColor: "rgba(37,99,235,0.15)", padding: "0.125rem 0.5rem", borderRadius: "999px" }}>
                      {platLabel(k.platform)}
                    </span>
                  </td>
                  <td style={td}>{[k.make, k.model].filter(Boolean).join(" ") || "—"}</td>
                  <td style={td}>{k.bid_max ? `$${Math.round(k.bid_max).toLocaleString("en-US")}` : "—"}</td>
                  <td style={td}>{k.polling_interval_minutes} min</td>
                  <td style={td}>
                    <button onClick={() => toggle(k)} style={{ background: "none", border: "none", cursor: "pointer", color: k.is_active ? "#4ade80" : "var(--text-muted)" }}>
                      {k.is_active ? <ToggleRight style={{ width: "22px", height: "22px" }} /> : <ToggleLeft style={{ width: "22px", height: "22px" }} />}
                    </button>
                  </td>
                  <td style={td}>
                    <div style={{ display: "flex", gap: "0.375rem" }}>
                      <button onClick={() => openEdit(k)} title="Editează" style={iconBtn}><Pencil style={{ width: "14px", height: "14px" }} /></button>
                      <button onClick={() => remove(k)} title="Șterge" style={{ ...iconBtn, color: "#f87171" }}><Trash2 style={{ width: "14px", height: "14px" }} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showModal && (
        <LotKeywordModal
          editing={!!editingId}
          form={form}
          setForm={setForm}
          saving={saving}
          onClose={() => setShowModal(false)}
          onSubmit={submit}
        />
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      {children}
    </div>
  );
}

function LotKeywordModal({ editing, form, setForm, saving, onClose, onSubmit }) {
  const set = (patch) => setForm((prev) => ({ ...prev, ...patch }));

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1.5rem" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.875rem", width: "100%", maxWidth: "640px", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "1.25rem", borderBottom: "1px solid var(--border-color)", position: "sticky", top: 0, backgroundColor: "var(--bg-card)" }}>
          <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            {editing ? "Editează keyword lot" : "Adaugă keyword lot"}
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}><X style={{ width: "20px", height: "20px" }} /></button>
        </div>

        <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <Field label="Nume keyword *">
            <input value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="ex: BMW daune frontale Copart" style={inputStyle} autoFocus />
          </Field>

          <Field label="Platformă">
            <select value={form.platform} onChange={(e) => set({ platform: e.target.value })} style={inputStyle}>
              {LOT_PLATFORMS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </Field>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <Field label="Marcă"><input value={form.make} onChange={(e) => set({ make: e.target.value })} placeholder="ex: BMW" style={inputStyle} /></Field>
            <Field label="Model"><input value={form.model} onChange={(e) => set({ model: e.target.value })} placeholder="ex: 320i" style={inputStyle} /></Field>
            <Field label="An de la"><input type="number" value={form.year_from} onChange={(e) => set({ year_from: e.target.value })} placeholder="2010" style={inputStyle} /></Field>
            <Field label="An până la"><input type="number" value={form.year_to} onChange={(e) => set({ year_to: e.target.value })} placeholder="2024" style={inputStyle} /></Field>
            <Field label="Daună primară"><input value={form.damage_primary} onChange={(e) => set({ damage_primary: e.target.value })} placeholder="ex: Front End" style={inputStyle} /></Field>
            <Field label="Bid maxim ($)"><input type="number" value={form.bid_max} onChange={(e) => set({ bid_max: e.target.value })} placeholder="ex: 8000" style={inputStyle} /></Field>
            <Field label="Stat / Locație"><input value={form.location_state} onChange={(e) => set({ location_state: e.target.value })} placeholder="ex: CA" style={inputStyle} /></Field>
            <Field label="Interval verificare">
              <select value={form.polling_interval} onChange={(e) => set({ polling_interval: parseInt(e.target.value) })} style={inputStyle}>
                {POLL_OPTIONS.map((m) => <option key={m} value={m}>{m} min</option>)}
              </select>
            </Field>
          </div>

          {/* Active hours */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
              <input type="checkbox" id="lot-use-hours" checked={form.use_active_hours} onChange={(e) => set({ use_active_hours: e.target.checked })} style={{ width: "15px", height: "15px", cursor: "pointer" }} />
              <label htmlFor="lot-use-hours" style={{ fontSize: "0.875rem", color: "var(--text-primary)", cursor: "pointer" }}>Activ doar în interval orar</label>
            </div>
            {form.use_active_hours && (
              <div style={{ marginTop: "0.625rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Field label="De la (ora)">
                  <select value={form.active_hours_start} onChange={(e) => set({ active_hours_start: parseInt(e.target.value) })} style={inputStyle}>
                    {Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>)}
                  </select>
                </Field>
                <Field label="Până la (ora)">
                  <select value={form.active_hours_end} onChange={(e) => set({ active_hours_end: parseInt(e.target.value) })} style={inputStyle}>
                    {Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>)}
                  </select>
                </Field>
              </div>
            )}
          </div>

          {/* Toggles */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-primary)", cursor: "pointer" }}>
              <input type="checkbox" checked={form.notify_email} onChange={(e) => set({ notify_email: e.target.checked })} style={{ width: "auto" }} /> Notificare email
            </label>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-primary)", cursor: "pointer" }}>
              <input type="checkbox" checked={form.notify_discord} onChange={(e) => set({ notify_discord: e.target.checked })} style={{ width: "auto" }} /> Notificare Discord
            </label>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-primary)", cursor: "pointer" }}>
              <input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} style={{ width: "auto" }} /> Activ
            </label>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", padding: "1rem 1.25rem", borderTop: "1px solid var(--border-color)", position: "sticky", bottom: 0, backgroundColor: "var(--bg-card)" }}>
          <button onClick={onClose} style={{ padding: "0.5rem 1rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 500, cursor: "pointer" }}>Anulează</button>
          <button onClick={onSubmit} disabled={saving} style={{ padding: "0.5rem 1.25rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: saving ? "wait" : "pointer", opacity: saving ? 0.7 : 1 }}>
            {saving ? "Se salvează..." : editing ? "Salvează" : "Adaugă"}
          </button>
        </div>
      </div>
    </div>
  );
}
