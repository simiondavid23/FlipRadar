"use client";
import { useState, useEffect, useCallback } from "react";
import { autoListingsAPI } from "@/lib/api";
import { modalFooterStyle } from "@/lib/uiStyles";
import DeleteKeywordModal from "@/components/DeleteKeywordModal";
import { Car, Plus, Pencil, Trash2, ToggleLeft, ToggleRight, X, Info } from "lucide-react";

// Prețul de referință e în EUR pentru TOATE platformele (inclusiv Facebook Auto) —
// unitate unică ca să nu compari mere cu pere între platforme RON și EUR.
const AUTO_PLATFORMS = [
  { value: "autovit",            label: "Autovit",            currency: "EUR" },
  { value: "olx_auto",           label: "OLX Auto",           currency: "EUR" },
  { value: "mobile_de",          label: "Mobile.de",          currency: "EUR" },
  { value: "autoscout24",        label: "AutoScout24",        currency: "EUR" },
  { value: "facebook_auto",      label: "Facebook Auto",      currency: "EUR" },
  { value: "kleinanzeigen_auto", label: "eBay Kleinanzeigen", currency: "EUR" },
];

const POLL_OPTIONS = [5, 10, 15, 30, 60];

const EMPTY_FORM = {
  name: "", make: "", model: "", query: "",
  year_from: "", year_to: "", km_max: "", price_max: "",
  category: "", tech: {},
  // Gradare (marja fata de pretul de revanzare, in EUR) — identic cu Radar.
  resale_price: "", min_margin_pct: 10,
  grade_a_min: "", grade_b_min: "", grade_c_min: "",
  is_active: true, notify_email: false, notify_discord: false,
  use_active_hours: false, active_hours_start: 8, active_hours_end: 22,
  polling_interval: 10,
};

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
  fontSize: "0.875rem", outline: "none",
};
const labelStyle = { display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" };
const td = { padding: "0.625rem 0.75rem", fontSize: "0.8125rem", color: "var(--text-primary)", verticalAlign: "middle" };

// Etichete RO pentru campurile tehnice dinamice (fallback pe cheia bruta).
const FIELD_LABELS = {
  fuel_type: "Combustibil", gearbox: "Cutie de viteze", body_type: "Caroserie", condition: "Stare",
  seller_type: "Vânzător", drivetrain: "Tracțiune", door_count: "Număr uși",
  door_count_min: "Nr. uși min", door_count_max: "Nr. uși max", color: "Culoare",
  emission_standard: "Normă poluare", vat_invoice: "Factură TVA",
  engine_capacity_min: "Capacitate motor min (cmc)", engine_capacity_max: "Capacitate motor max (cmc)",
  engine_power_min: "Putere min", engine_power_max: "Putere max", power_unit: "Unitate putere",
  seats_min: "Nr. locuri min", seats_max: "Nr. locuri max",
  year_min: "An min", year_max: "An max", mileage_max: "Km max", make: "Marcă", year: "An", price_min: "Preț min",
};
// Text descriptiv pentru checkbox-urile boolean (o singura valoare cu sens = "1").
const BOOL_LABELS = { seller_type: "Doar dealeri autorizați", vat_invoice: "Cu factură TVA" };
// Filtre "principale" afisate direct; restul intra in sectiunea colapsabila "Filtre avansate".
const MAIN_TECH_FIELDS = new Set(["fuel_type", "gearbox", "body_type"]);
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

// Campuri tehnice ASCUNSE din formular fiindca duplica campurile GENERICE de sus
// (An de la=year_min, An pana la=year_max, Km max=mileage_max) sau nu au sens singure
// (power_unit=kW, fara un camp real de putere). "make" duplica campul generic "Marcă"
// de sus (marca ajunge la autos.marke_s din campul generic — vezi fix-ul Kleinanzeigen).
// Raman conectate in backend (auto_categories.py neatins) — valorile generice ajung la
// scraper prin cheile make / year_min / year_max si aliasul mileage_max->km_max.
const HIDDEN_TECH_FIELDS = new Set(["year_min", "year_max", "mileage_max", "power_unit", "make"]);

export default function AutoKeywordsPage() {
  const [keywords, setKeywords] = useState([]);
  const [catData, setCatData] = useState({ categories: {}, technical_fields: {} });
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [platform, setPlatform] = useState("autovit");
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deleteModal, setDeleteModal] = useState(null);

  const load = useCallback(async () => {
    try { const r = await autoListingsAPI.getKeywords(); setKeywords(r.data || []); }
    catch (e) { console.error("[AutoKeywords]", e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    autoListingsAPI.getCategories()
      .then((r) => setCatData(r.data || { categories: {}, technical_fields: {} }))
      .catch(() => {});
  }, []);

  const openAdd = () => { setEditingId(null); setPlatform("autovit"); setForm(EMPTY_FORM); setShowModal(true); };

  const openEdit = (kw) => {
    setEditingId(kw.id);
    setPlatform(kw.platform || "autovit");
    setForm({
      name: kw.name || "", make: kw.make || "", model: kw.model || "", query: kw.query || "",
      year_from: kw.year_from ?? "", year_to: kw.year_to ?? "", km_max: kw.km_max ?? "", price_max: kw.price_max ?? "",
      category: kw.category || "", tech: kw.tech_filters || {},
      resale_price: kw.resale_price ?? "", min_margin_pct: kw.min_margin_pct ?? 10,
      grade_a_min: kw.grade_a_min ?? "", grade_b_min: kw.grade_b_min ?? "", grade_c_min: kw.grade_c_min ?? "",
      is_active: kw.is_active, notify_email: kw.notify_email, notify_discord: kw.notify_discord,
      use_active_hours: kw.active_hours_start != null && kw.active_hours_end != null,
      active_hours_start: kw.active_hours_start ?? 8, active_hours_end: kw.active_hours_end ?? 22,
      polling_interval: kw.polling_interval_minutes ?? 10,
    });
    setShowModal(true);
  };

  const submit = async () => {
    if (!form.name.trim()) { alert("Numele keyword-ului este obligatoriu."); return; }
    const cleanTech = Object.fromEntries(
      Object.entries(form.tech || {}).filter(([, v]) => v !== "" && v != null)
    );
    const payload = {
      name: form.name, platform,
      make: form.make || null, model: form.model || null, query: form.query || null,
      year_from: form.year_from ? parseInt(form.year_from) : null,
      year_to: form.year_to ? parseInt(form.year_to) : null,
      km_max: form.km_max ? parseInt(form.km_max) : null,
      price_max: form.price_max ? parseFloat(form.price_max) : null,
      price_currency: AUTO_PLATFORMS.find((p) => p.value === platform)?.currency || "RON",
      category: form.category || null,
      tech_filters: Object.keys(cleanTech).length ? cleanTech : null,
      resale_price: form.resale_price === "" || form.resale_price == null ? null : parseFloat(form.resale_price),
      resale_price_currency: "EUR",
      min_margin_pct: form.min_margin_pct === "" || form.min_margin_pct == null ? 10 : parseFloat(form.min_margin_pct),
      grade_a_min: form.grade_a_min === "" || form.grade_a_min == null ? null : parseFloat(form.grade_a_min),
      grade_b_min: form.grade_b_min === "" || form.grade_b_min == null ? null : parseFloat(form.grade_b_min),
      grade_c_min: form.grade_c_min === "" || form.grade_c_min == null ? null : parseFloat(form.grade_c_min),
      is_active: form.is_active, notify_email: form.notify_email, notify_discord: form.notify_discord,
      active_hours_start: form.use_active_hours ? form.active_hours_start : null,
      active_hours_end: form.use_active_hours ? form.active_hours_end : null,
      polling_interval_minutes: parseInt(form.polling_interval) || 10,
    };
    setSaving(true);
    try {
      if (editingId) await autoListingsAPI.updateKeyword(editingId, payload);
      else await autoListingsAPI.createKeyword(payload);
      setShowModal(false); await load();
    } catch (e) { alert(e.response?.data?.detail || "Eroare la salvare."); }
    finally { setSaving(false); }
  };

  const toggle = async (kw) => {
    try {
      await autoListingsAPI.updateKeyword(kw.id, {
        name: kw.name, platform: kw.platform, make: kw.make, model: kw.model, query: kw.query,
        year_from: kw.year_from, year_to: kw.year_to, km_max: kw.km_max,
        price_max: kw.price_max != null ? parseFloat(kw.price_max) : null,
        price_currency: kw.price_currency, category: kw.category, tech_filters: kw.tech_filters,
        fuel_type: kw.fuel_type, transmission: kw.transmission, body_type: kw.body_type, location: kw.location,
        is_active: !kw.is_active, notify_email: kw.notify_email, notify_discord: kw.notify_discord,
        active_hours_start: kw.active_hours_start, active_hours_end: kw.active_hours_end,
        polling_interval_minutes: kw.polling_interval_minutes,
      });
      await load();
    } catch (e) { alert(e.response?.data?.detail || "Eroare la actualizare."); }
  };

  const handleDeleteClick = async (kw) => {
    let impact = { listing_count: 0, seen_count: 0 };
    try { impact = (await autoListingsAPI.getKeywordImpact(kw.id)).data; } catch { /* fallback 0 */ }
    setDeleteModal({ keywordId: kw.id, keywordName: kw.name, listingCount: impact.listing_count ?? 0, seenCount: impact.seen_count ?? 0 });
  };
  const performDelete = async (id) => {
    try { await autoListingsAPI.deleteKeyword(id); await load(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare la ștergere."); }
  };

  const platLabel = (v) => AUTO_PLATFORMS.find((p) => p.value === v)?.label || v;

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#2563eb", display: "flex" }}>
            <Car style={{ width: "20px", height: "20px", color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Keyword-uri Auto</h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", margin: 0 }}>
              Monitorizare anunțuri auto pe {AUTO_PLATFORMS.length} platforme ({keywords.length} keyword-uri)
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
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
            Niciun keyword încă. Apasă „Adaugă Keyword” pentru a începe monitorizarea.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ backgroundColor: "var(--bg-dark)" }}>
                {["Nume", "Platformă", "Mașină", "Preț max", "Interval", "Activ", ""].map((h) => (
                  <th key={h} style={{ ...td, fontWeight: 600, color: "var(--text-secondary)", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.03em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {keywords.map((k) => (
                <tr key={k.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                  <td style={td}>
                    <div style={{ fontWeight: 500 }}>{k.name}</div>
                    {k.category && <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{k.category}</span>}
                    {(k.active_hours_start != null && k.active_hours_end != null) && (
                      <span style={{ fontSize: "0.7rem", color: "var(--text-secondary)", display: "block" }}>
                        {String(k.active_hours_start).padStart(2, "0")}:00 – {String(k.active_hours_end).padStart(2, "0")}:00
                      </span>
                    )}
                  </td>
                  <td style={td}>
                    <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "#60a5fa", backgroundColor: "rgba(37,99,235,0.15)", padding: "0.125rem 0.5rem", borderRadius: "999px" }}>
                      {platLabel(k.platform)}
                    </span>
                  </td>
                  <td style={td}>{[k.make, k.model].filter(Boolean).join(" ") || k.query || "—"}</td>
                  <td style={td}>{k.price_max ? `${Math.round(k.price_max).toLocaleString("ro-RO")} ${k.price_currency}` : "—"}</td>
                  <td style={td}>{k.polling_interval_minutes} min</td>
                  <td style={td}>
                    <button onClick={() => toggle(k)} style={{ background: "none", border: "none", cursor: "pointer", color: k.is_active ? "#4ade80" : "var(--text-muted)" }}>
                      {k.is_active ? <ToggleRight style={{ width: "22px", height: "22px" }} /> : <ToggleLeft style={{ width: "22px", height: "22px" }} />}
                    </button>
                  </td>
                  <td style={td}>
                    <div style={{ display: "flex", gap: "0.375rem" }}>
                      <button onClick={() => openEdit(k)} title="Editează" style={iconBtn}><Pencil style={{ width: "14px", height: "14px" }} /></button>
                      <button onClick={() => handleDeleteClick(k)} title="Șterge" style={{ ...iconBtn, color: "#f87171" }}><Trash2 style={{ width: "14px", height: "14px" }} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showModal && (
        <KeywordModal
          editing={!!editingId} platform={platform} setPlatform={setPlatform}
          form={form} setForm={setForm} catData={catData} saving={saving}
          onClose={() => setShowModal(false)} onSubmit={submit}
        />
      )}

      <DeleteKeywordModal
        data={deleteModal}
        onCancel={() => setDeleteModal(null)}
        onConfirm={() => { performDelete(deleteModal.keywordId); setDeleteModal(null); }}
      />
    </div>
  );
}

const iconBtn = {
  display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "0.375rem",
  backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.375rem",
  color: "var(--text-secondary)", cursor: "pointer",
};

function Field({ label, children }) {
  return (<div><label style={labelStyle}>{label}</label>{children}</div>);
}

function KeywordModal({ editing, platform, setPlatform, form, setForm, catData, saving, onClose, onSubmit }) {
  const set = (patch) => setForm((prev) => ({ ...prev, ...patch }));
  const setTech = (k, v) => set({ tech: { ...(form.tech || {}), [k]: v } });
  const cur = AUTO_PLATFORMS.find((p) => p.value === platform)?.currency || "RON";
  // Dinamic din /categories: doar categoriile cu value confirmat + doar campurile confirmed:true.
  const validCats = ((catData.categories || {})[platform] || []).filter((c) => c.value != null);
  const techFields = Object.entries((catData.technical_fields || {})[platform] || {})
    .filter(([key, spec]) => spec && typeof spec === "object" && spec.confirmed === true
      && !HIDDEN_TECH_FIELDS.has(key));
  // Principale (combustibil/cutie/caroserie) afisate direct; restul in "Filtre avansate".
  const mainTech = techFields.filter(([key]) => MAIN_TECH_FIELDS.has(key));
  const advTech = techFields.filter(([key]) => !MAIN_TECH_FIELDS.has(key));

  // Sectiuni colapsabile — auto-deschise daca keyword-ul editat are deja valori acolo.
  const [showGrades, setShowGrades] = useState(
    form.grade_a_min !== "" || form.grade_b_min !== "" || form.grade_c_min !== ""
  );
  const [showAdvanced, setShowAdvanced] = useState(
    advTech.some(([key]) => (form.tech?.[key] ?? "") !== "")
  );

  // Randare unui camp tehnic: checkbox (boolean), dropdown (are values) sau numeric.
  const renderTech = ([key, spec]) => (
    spec.type === "boolean" ? (
      <label key={key} style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: "0.5rem",
        fontSize: "0.8125rem", color: "var(--text-primary)", cursor: "pointer" }}>
        <input type="checkbox" checked={(form.tech?.[key] || "") === "1"}
          onChange={(e) => setTech(key, e.target.checked ? "1" : "")}
          style={{ width: "1rem", height: "1rem", cursor: "pointer" }} />
        {BOOL_LABELS[key] || FIELD_LABELS[key] || key}
      </label>
    ) : (
      <Field key={key} label={FIELD_LABELS[key] || key}>
        {spec.values ? (
          <select value={form.tech?.[key] || ""} onChange={(e) => setTech(key, e.target.value)} style={inputStyle}>
            <option value="">Toate</option>
            {Object.keys(spec.values).map((k) => <option key={k} value={k}>{cap(k)}</option>)}
          </select>
        ) : (
          <input type="number" value={form.tech?.[key] || ""} onChange={(e) => setTech(key, e.target.value)} placeholder="—" style={inputStyle} />
        )}
      </Field>
    )
  );

  const changePlatform = (v) => { setPlatform(v); set({ category: "", tech: {} }); };

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1.5rem" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.875rem", width: "100%", maxWidth: "640px", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "1.25rem", borderBottom: "1px solid var(--border-color)", position: "sticky", top: 0, backgroundColor: "var(--bg-card)" }}>
          <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            {editing ? "Editează keyword auto" : "Adaugă keyword auto"}
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}><X style={{ width: "20px", height: "20px" }} /></button>
        </div>

        <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <Field label="Nume keyword *">
            <input value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="ex: BMW Seria 3 diesel" style={inputStyle} autoFocus />
          </Field>

          <Field label="Platformă">
            <select value={platform} onChange={(e) => changePlatform(e.target.value)} style={inputStyle}>
              {AUTO_PLATFORMS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </Field>

          {platform === "facebook_auto" && (
            <div style={{ padding: "0.625rem 0.875rem", backgroundColor: "rgba(245,158,11,0.06)", border: "0.5px solid rgba(245,158,11,0.2)", borderRadius: "0.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)", display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
              <Info style={{ width: "16px", height: "16px", flexShrink: 0, marginTop: "0.1rem" }} />
              <span>
                Facebook Auto folosește sesiunea autentificată din{" "}
                <a href="/dashboard/settings" style={{ color: "#fbbf24" }}>Setări → Facebook</a>. Nu suportă filtre tehnice structurate.
              </span>
            </div>
          )}

          {/* Categorie dinamica (doar daca platforma are categorii confirmate) */}
          {validCats.length > 0 && (
            <Field label="Categorie">
              <select value={form.category} onChange={(e) => set({ category: e.target.value })} style={inputStyle}>
                <option value="">Toate (implicit)</option>
                {validCats.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </Field>
          )}

          {/* Campuri de baza (nemodificate) */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <Field label="Marcă"><input value={form.make} onChange={(e) => set({ make: e.target.value })} placeholder="ex: BMW" style={inputStyle} /></Field>
            <Field label="Model"><input value={form.model} onChange={(e) => set({ model: e.target.value })} placeholder="ex: Seria 3" style={inputStyle} /></Field>
            <Field label="Căutare (text liber)"><input value={form.query} onChange={(e) => set({ query: e.target.value })} placeholder="ex: 320d" style={inputStyle} /></Field>
            <Field label={`Preț max ${cur}`}><input type="number" value={form.price_max} onChange={(e) => set({ price_max: e.target.value })} placeholder={cur === "EUR" ? "15000" : "60000"} style={inputStyle} /></Field>
            <Field label="An de la"><input type="number" value={form.year_from} onChange={(e) => set({ year_from: e.target.value })} placeholder="2010" style={inputStyle} /></Field>
            <Field label="An până la"><input type="number" value={form.year_to} onChange={(e) => set({ year_to: e.target.value })} placeholder="2024" style={inputStyle} /></Field>
            <Field label="Km max"><input type="number" value={form.km_max} onChange={(e) => set({ km_max: e.target.value })} placeholder="200000" style={inputStyle} /></Field>
          </div>

          {/* Gradare — marja fata de pretul de revanzare (identic cu Radar) */}
          <div style={{ borderTop: "1px solid var(--border-color)", paddingTop: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.03em" }}>
              Gradare (marjă vs. preț de revânzare)
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <Field label="Preț de revânzare estimat (EUR)">
                <input type="number" value={form.resale_price} onChange={(e) => set({ resale_price: e.target.value })} placeholder="ex: 15000" style={inputStyle} min="0" step="any" />
              </Field>
              <Field label="Marjă minimă (%)">
                <input type="number" value={form.min_margin_pct} onChange={(e) => set({ min_margin_pct: e.target.value })} placeholder="10" style={inputStyle} min="0" step="any" />
              </Field>
            </div>
            <small style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>
              Gol ⇒ anunțurile rămân fără grad. Prețul anunțului și cel de revânzare sunt convertite în RON (curs BNR) înainte de calcul.
            </small>

            {/* Praguri de grad (opțional) — colapsabil; gol ⇒ implicit A≥40% · B≥25% · C≥10% */}
            <div style={{ border: "1px solid var(--border-color)", borderRadius: "0.5rem", overflow: "hidden" }}>
              <button type="button" onClick={() => setShowGrades((v) => !v)}
                style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "0.5rem 0.75rem", backgroundColor: "var(--bg-dark)", border: "none", cursor: "pointer",
                  color: "var(--text-secondary)", fontSize: "0.8125rem", fontWeight: 600 }}>
                <span>Praguri de grad (opțional)</span>
                <span style={{ fontSize: "1rem", lineHeight: 1 }}>{showGrades ? "−" : "+"}</span>
              </button>
              {showGrades && (
                <div style={{ padding: "0.75rem", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem" }}>
                  <Field label="Grad A minim (%)"><input type="number" value={form.grade_a_min} onChange={(e) => set({ grade_a_min: e.target.value })} placeholder="40" style={inputStyle} min="0" step="any" /></Field>
                  <Field label="Grad B minim (%)"><input type="number" value={form.grade_b_min} onChange={(e) => set({ grade_b_min: e.target.value })} placeholder="25" style={inputStyle} min="0" step="any" /></Field>
                  <Field label="Grad C minim (%)"><input type="number" value={form.grade_c_min} onChange={(e) => set({ grade_c_min: e.target.value })} placeholder="10" style={inputStyle} min="0" step="any" /></Field>
                  <small style={{ gridColumn: "1 / -1", color: "var(--text-muted)", fontSize: "0.7rem" }}>
                    Lasă gol pentru valorile implicite (A ≥ 40% · B ≥ 25% · C ≥ 10%).
                  </small>
                </div>
              )}
            </div>
          </div>

          {/* Campuri tehnice confirmate — DOAR daca platforma are (Facebook: nu apare) */}
          {techFields.length > 0 && (
            <div>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "0.5rem" }}>
                Filtre tehnice
              </div>
              {mainTech.length > 0 && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                  {mainTech.map(renderTech)}
                </div>
              )}
              {advTech.length > 0 && (
                <div style={{ border: "1px solid var(--border-color)", borderRadius: "0.5rem", overflow: "hidden", marginTop: mainTech.length > 0 ? "0.75rem" : 0 }}>
                  <button type="button" onClick={() => setShowAdvanced((v) => !v)}
                    style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "0.5rem 0.75rem", backgroundColor: "var(--bg-dark)", border: "none", cursor: "pointer",
                      color: "var(--text-secondary)", fontSize: "0.8125rem", fontWeight: 600 }}>
                    <span>Filtre avansate ({advTech.length})</span>
                    <span style={{ fontSize: "1rem", lineHeight: 1 }}>{showAdvanced ? "−" : "+"}</span>
                  </button>
                  {showAdvanced && (
                    <div style={{ padding: "0.75rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                      {advTech.map(renderTech)}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Interval verificare */}
          <Field label="Interval verificare">
            <select value={form.polling_interval} onChange={(e) => set({ polling_interval: parseInt(e.target.value) })} style={inputStyle}>
              {POLL_OPTIONS.map((m) => <option key={m} value={m}>{m} min</option>)}
            </select>
          </Field>

          {/* Active hours */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
              <input type="checkbox" id="auto-use-hours" checked={form.use_active_hours} onChange={(e) => set({ use_active_hours: e.target.checked })} style={{ width: "15px", height: "15px", cursor: "pointer" }} />
              <label htmlFor="auto-use-hours" style={{ fontSize: "0.875rem", color: "var(--text-primary)", cursor: "pointer" }}>Activ doar în interval orar</label>
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

        <div style={modalFooterStyle}>
          <button onClick={onClose} style={{ padding: "0.5rem 1rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 500, cursor: "pointer" }}>Anulează</button>
          <button onClick={onSubmit} disabled={saving} style={{ padding: "0.5rem 1.25rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: saving ? "wait" : "pointer", opacity: saving ? 0.7 : 1 }}>
            {saving ? "Se salvează..." : editing ? "Salvează" : "Adaugă"}
          </button>
        </div>
      </div>
    </div>
  );
}
