"use client";
import { useState, useEffect, useCallback } from "react";
import { realEstateMonitorAPI } from "@/lib/api";
import DeleteKeywordModal from "@/components/DeleteKeywordModal";
import NotifToggle from "@/components/NotifToggle";
import { modalFooterStyle, platformChipStyle } from "@/lib/uiStyles";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import { Home, Plus, Pencil, Trash2, X, RefreshCw, Info } from "lucide-react";

const RE_PLATFORMS = [
  { value: "olx",                  label: "OLX Imobiliare" },
  { value: "storia",               label: "Storia.ro" },
  { value: "imobiliare_ro",        label: "Imobiliare.ro" },
  { value: "facebook_marketplace", label: "Facebook Marketplace" },
  { value: "facebook_groups",      label: "Grupuri Facebook" },
];

const PROPERTY_TYPES = [
  "Apartamente - Garsoniere de vanzare",
  "Apartamente - Garsoniere de inchiriat",
  "Case de vanzare",
  "Case de inchiriat",
  "Terenuri",
  "Birouri - Spatii comerciale",
  "Schimburi Imobiliare",
  "Alte proprietati",
  "Parcari si Garaje",
  "Depozite si Hale",
  "Caut coleg - Camere de inchiriat",
  "Proprietati Internationale",
];

const CITIES = ["București", "Cluj-Napoca", "Iași", "Timișoara", "Brașov",
                "Constanța", "Sibiu", "Oradea", "Arad", "Pitești"];

const POLL_OPTIONS = [15, 30, 60, 120];

const EMPTY_FORM = {
  name: "", property_type: "", tip_anunt: "vanzare", rooms: "", rooms_max: "", area_min: "", area_max: "",
  price_min: "", price_max: "", price_currency: "EUR", zone: "", city: "București",
  floor_min: "", floor_max: "", furnished: "", query: "", exclude_words: [],
  is_active: true, notify_email: false, notify_discord: false,
  use_active_hours: false, active_hours_start: 8, active_hours_end: 22,
  polling_interval: 30,
};

// Platforma (valoarea din form) -> cheia din RE_TECHNICAL_FIELDS (endpoint /categories).
const PLATFORM_TO_RE_KEY = {
  olx: "olx_real_estate", storia: "storia", imobiliare_ro: "imobiliare_ro",
  facebook_marketplace: "facebook_real_estate",
};
// Etichete RO pentru campurile tehnice confirmate (afisate ca "filtre la sursa").
const TECH_LABELS = { price_min: "preț min", price_max: "preț max", rooms_min: "camere", area_min: "suprafață" };

const inputStyle = {
  width: "100%", background: "rgba(4,9,18,.45)", border: "1px solid var(--border-color)",
  borderRadius: "10px", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
  fontSize: "0.875rem", outline: "none",
};
const labelStyle = { display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" };
const td = { color: "var(--text-secondary)" };
const iconBtn = {
  display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "5px",
  background: "transparent", border: "none", borderRadius: "7px",
  color: "var(--text-dim)", cursor: "pointer", opacity: 0.8, transition: "all .15s ease",
};

export default function REKeywordsPage() {
  const [keywords, setKeywords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [platform, setPlatform] = useState("olx");
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [categories, setCategories] = useState({});   // technical_fields per platforma (/categories)
  // MODIFICARE 18 — modal confirmare stergere cu impact.
  const [deleteModal, setDeleteModal] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await realEstateMonitorAPI.getKeywords();
      setKeywords(r.data || []);
    } catch (e) {
      console.error("[REKeywords]", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    realEstateMonitorAPI.getCategories()
      .then((r) => setCategories(r.data?.technical_fields || {}))
      .catch(() => {});
  }, []);

  const handleScanNow = async () => {
    setScanning(true);
    try { await realEstateMonitorAPI.scanNow(); setTimeout(() => setScanning(false), 3000); }
    catch { setScanning(false); }
  };

  const openAdd = () => { setEditingId(null); setPlatform("olx"); setForm(EMPTY_FORM); setShowModal(true); };

  const openEdit = (kw) => {
    setEditingId(kw.id);
    setPlatform(kw.platform || "olx");
    setForm({
      name: kw.name || "", property_type: kw.property_type || "", tip_anunt: kw.tip_anunt || "vanzare",
      rooms: kw.rooms ?? "", rooms_max: kw.rooms_max ?? "",
      area_min: kw.area_min ?? "", area_max: kw.area_max ?? "",
      price_min: kw.price_min ?? "", price_max: kw.price_max ?? "",
      price_currency: kw.price_currency || "EUR", zone: kw.zone || "", city: kw.city || "București",
      floor_min: kw.floor_min ?? "", floor_max: kw.floor_max ?? "",
      furnished: kw.furnished === null || kw.furnished === undefined ? "" : (kw.furnished ? "true" : "false"),
      query: kw.query || "", exclude_words: Array.isArray(kw.exclude_words) ? kw.exclude_words : [],
      is_active: kw.is_active, notify_email: kw.notify_email, notify_discord: kw.notify_discord,
      use_active_hours: kw.active_hours_start != null && kw.active_hours_end != null,
      active_hours_start: kw.active_hours_start ?? 8, active_hours_end: kw.active_hours_end ?? 22,
      polling_interval: kw.polling_interval_minutes ?? 30,
    });
    setShowModal(true);
  };

  const submit = async () => {
    if (!form.name.trim()) { alert("Numele keyword-ului este obligatoriu."); return; }
    const payload = {
      name: form.name,
      platform,
      property_type: form.property_type || null,
      tip_anunt: form.tip_anunt || "vanzare",
      rooms: form.rooms ? parseInt(form.rooms) : null,
      rooms_max: form.rooms_max ? parseInt(form.rooms_max) : null,
      area_min: form.area_min ? parseInt(form.area_min) : null,
      area_max: form.area_max ? parseInt(form.area_max) : null,
      price_min: form.price_min ? parseFloat(form.price_min) : null,
      price_max: form.price_max ? parseFloat(form.price_max) : null,
      price_currency: form.price_currency || "EUR",
      zone: form.zone || null,
      city: form.city || "București",
      floor_min: form.floor_min ? parseInt(form.floor_min) : null,
      floor_max: form.floor_max ? parseInt(form.floor_max) : null,
      furnished: form.furnished === "" ? null : form.furnished === "true",
      query: form.query || null,
      exclude_words: form.exclude_words,
      is_active: form.is_active,
      notify_email: form.notify_email,
      notify_discord: form.notify_discord,
      active_hours_start: form.use_active_hours ? form.active_hours_start : null,
      active_hours_end: form.use_active_hours ? form.active_hours_end : null,
      polling_interval_minutes: parseInt(form.polling_interval) || 30,
    };
    setSaving(true);
    try {
      if (editingId) await realEstateMonitorAPI.updateKeyword(editingId, payload);
      else await realEstateMonitorAPI.createKeyword(payload);
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
      await realEstateMonitorAPI.updateKeyword(kw.id, {
        name: kw.name, platform: kw.platform, property_type: kw.property_type,
        tip_anunt: kw.tip_anunt || "vanzare", rooms: kw.rooms,
        rooms_max: kw.rooms_max,   // CRITIC: ca la exclude_words — fara el, toggle-ul sterge plafonul
        area_min: kw.area_min, area_max: kw.area_max,
        price_min: kw.price_min != null ? parseFloat(kw.price_min) : null,
        price_max: kw.price_max != null ? parseFloat(kw.price_max) : null,
        price_currency: kw.price_currency, zone: kw.zone, city: kw.city,
        floor_min: kw.floor_min, floor_max: kw.floor_max, furnished: kw.furnished, query: kw.query,
        exclude_words: kw.exclude_words || [],   // CRITIC: KeywordUpdate seteaza tot; fara asta toggle-ul sterge excluderile
        is_active: !kw.is_active, notify_email: kw.notify_email, notify_discord: kw.notify_discord,
        active_hours_start: kw.active_hours_start, active_hours_end: kw.active_hours_end,
        polling_interval_minutes: kw.polling_interval_minutes,
      });
      await load();
    } catch (e) { alert(e.response?.data?.detail || "Eroare la actualizare."); }
  };

  // MODIFICARE 18 — deschide modalul cu impactul (nr. listinguri asociate).
  const handleDeleteClick = async (kw) => {
    let impact = { listing_count: 0, seen_count: 0 };
    try { impact = (await realEstateMonitorAPI.getKeywordImpact(kw.id)).data; } catch { /* fallback 0 */ }
    setDeleteModal({
      keywordId: kw.id, keywordName: kw.name,
      listingCount: impact.listing_count ?? 0, seenCount: impact.seen_count ?? 0,
    });
  };

  const performDelete = async (id) => {
    try { await realEstateMonitorAPI.deleteKeyword(id); await load(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare la ștergere."); }
  };

  const platLabel = (v) => RE_PLATFORMS.find((p) => p.value === v)?.label || v;
  const activeCount = keywords.filter((k) => k.is_active).length;

  return (
    <div>
      <TopBar path={["IMOBILIARE", "KEYWORD-URI"]}>
        <button onClick={handleScanNow} disabled={scanning} title="Scanare imediată" className="btn-cyan">
          <RefreshCw style={{ width: "13px", height: "13px", animation: scanning ? "spin 1s linear infinite" : "none" }} strokeWidth={2} />
          {scanning ? "Scanare pornită…" : "Scanează acum"}
        </button>
      </TopBar>

      <PageHeading
        icon={Home}
        title="Keyword-uri Imobiliare"
        subtitle={<>Monitorizare chirii pe {RE_PLATFORMS.length} surse — <Hl>{keywords.length} keyword-uri</Hl>, {activeCount} active.</>}
      >
        <button onClick={openAdd} className="btn-cyan">
          <Plus style={{ width: "13px", height: "13px" }} strokeWidth={2.2} /> Adaugă keyword
        </button>
      </PageHeading>

      <div className="glass-panel" style={{ marginTop: "16px", overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-dim)", fontSize: "12.5px" }}>Se încarcă…</div>
        ) : keywords.length === 0 ? (
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-dim)", fontSize: "12.5px" }}>
            Niciun keyword încă. Apasă „Adaugă keyword” pentru a începe monitorizarea.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
          <table className="data-table" style={{ minWidth: "920px" }}>
            <thead>
              <tr>
                {["Nume", "Sursă", "Tip", "Zonă / Oraș", "Preț max", "Interval", "Status", "Acțiuni"].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {keywords.map((k) => (
                <tr key={k.id}>
                  <td style={td}>
                    <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)" }}>{k.name}</div>
                    {(k.active_hours_start != null && k.active_hours_end != null) && (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", color: "var(--text-muted)", display: "block", marginTop: "4px" }}>
                        ⏱ {String(k.active_hours_start).padStart(2, "0")}:00 – {String(k.active_hours_end).padStart(2, "0")}:00
                      </span>
                    )}
                    {Array.isArray(k.exclude_words) && k.exclude_words.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "4px" }}>
                        {k.exclude_words.map((w) => (
                          <span key={w} style={{
                            fontSize: "9.5px", padding: "1.5px 7px", borderRadius: "6px",
                            background: "rgba(248,113,113,.09)", color: "#fca5a5",
                            border: "1px solid rgba(248,113,113,.22)", whiteSpace: "nowrap",
                          }}>− {w}</span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td style={td}>
                    <span style={platformChipStyle(k.platform)}>{platLabel(k.platform)}</span>
                  </td>
                  <td style={td}>{k.property_type || (k.rooms ? `${k.rooms} cam` : "—")}</td>
                  <td style={td}>{[k.zone, k.city].filter(Boolean).join(", ") || "—"}</td>
                  <td style={{ ...td, color: "var(--text-primary)", fontWeight: 500 }}>{k.price_max ? `${Math.round(k.price_max).toLocaleString("ro-RO")} ${k.price_currency}` : "—"}</td>
                  <td style={{ ...td, fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-dim)" }}>{k.polling_interval_minutes} min</td>
                  <td style={td}>
                    <button
                      onClick={() => toggle(k)}
                      className={`toggle-cyan${k.is_active ? " on" : ""}`}
                      aria-label={k.is_active ? "Dezactivează" : "Activează"}
                      title={k.is_active ? "Activ" : "Inactiv"}
                    />
                  </td>
                  <td style={td}>
                    <div style={{ display: "flex", gap: "4px", justifyContent: "flex-end" }}>
                      <button onClick={() => openEdit(k)} title="Editează" style={iconBtn}><Pencil style={{ width: "13px", height: "13px" }} strokeWidth={1.8} /></button>
                      <button onClick={() => handleDeleteClick(k)} title="Șterge" style={{ ...iconBtn, color: "#f87171" }}><Trash2 style={{ width: "13px", height: "13px" }} strokeWidth={1.8} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>

      {showModal && (
        <KeywordModal editing={!!editingId} platform={platform} setPlatform={setPlatform}
          form={form} setForm={setForm} saving={saving} categories={categories}
          onClose={() => setShowModal(false)} onSubmit={submit} />
      )}

      {/* MODIFICARE 18 — modal confirmare stergere cu impact */}
      <DeleteKeywordModal
        data={deleteModal}
        onCancel={() => setDeleteModal(null)}
        onConfirm={() => { performDelete(deleteModal.keywordId); setDeleteModal(null); }}
      />

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function Field({ label, children }) {
  return (<div><label style={labelStyle}>{label}</label>{children}</div>);
}

function KeywordModal({ editing, platform, setPlatform, form, setForm, saving, categories, onClose, onSubmit }) {
  const set = (patch) => setForm((prev) => ({ ...prev, ...patch }));
  const [chipInput, setChipInput] = useState("");
  const excludeChips = form.exclude_words || [];
  const addChip = () => {
    const w = chipInput.trim();
    if (w && !excludeChips.some((c) => c.toLowerCase() === w.toLowerCase())) {
      set({ exclude_words: [...excludeChips, w] });
    }
    setChipInput("");
  };
  const showFloors = ["olx", "storia", "imobiliare_ro"].includes(platform);
  // Filtre confirmate la sursa pt platforma selectata (din /categories) — form dinamic.
  const reKey = PLATFORM_TO_RE_KEY[platform];
  const techForPlatform = (reKey && categories?.[reKey]) || {};
  const confirmedLabels = Object.entries(techForPlatform)
    .filter(([, spec]) => spec && spec.confirmed)
    .map(([f]) => TECH_LABELS[f]).filter(Boolean);

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(2,5,12,0.72)", backdropFilter: "blur(6px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1.5rem" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "var(--bg-card)", backdropFilter: "blur(20px)", border: "1px solid var(--border-color)", borderRadius: "14px", width: "100%", maxWidth: "640px", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "1.25rem", borderBottom: "1px solid var(--border-color)", position: "sticky", top: 0, background: "var(--bg-card)", backdropFilter: "blur(20px)" }}>
          <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            {editing ? "Editează keyword imobiliar" : "Adaugă keyword imobiliar"}
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}><X style={{ width: "20px", height: "20px" }} /></button>
        </div>

        <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <Field label="Nume keyword *">
            <input value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="ex: 2 camere Floreasca sub 700€" style={inputStyle} autoFocus />
          </Field>

          {/* Platform selector — button group */}
          <div>
            <label style={labelStyle}>Sursă</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
              {RE_PLATFORMS.map((p) => {
                const active = platform === p.value;
                return (
                  <button key={p.value} onClick={() => { setPlatform(p.value); if (p.value === "facebook_marketplace" && form.tip_anunt === "vanzare") set({ tip_anunt: "inchiriere" }); }} style={{
                    padding: "0.375rem 0.75rem", borderRadius: "10px", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
                    border: `1px solid ${active ? "rgba(37,99,235,0.4)" : "var(--border-color)"}`,
                    backgroundColor: active ? "rgba(37,99,235,0.15)" : "transparent",
                    color: active ? "#60a5fa" : "var(--text-secondary)",
                  }}>{p.label}</button>
                );
              })}
            </div>
            {confirmedLabels.length > 0 ? (
              <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", margin: "0.5rem 0 0" }}>
                Filtre aplicate la sursă pentru această platformă:{" "}
                <span style={{ color: "var(--text-secondary)", fontWeight: 600 }}>{confirmedLabels.join(", ")}</span>. Restul se rafinează local.
              </p>
            ) : reKey ? (
              <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", margin: "0.5rem 0 0" }}>
                Fără filtre structurate confirmate la sursă — doar căutare liberă + rafinare locală.
              </p>
            ) : null}
          </div>

          {platform === "facebook_groups" && (
            <div style={{ padding: "0.625rem 0.875rem", backgroundColor: "rgba(245,158,11,0.06)", border: "0.5px solid rgba(245,158,11,0.2)", borderRadius: "10px", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
              <Info style={{ width: "14px", height: "14px", display: "inline", verticalAlign: "-2px", marginRight: "0.35rem" }} />Postările din grupurile configurate în Setări → „Grupuri Facebook — Chirii” vor fi incluse automat în feed pentru acest keyword.
            </div>
          )}
          {platform === "facebook_marketplace" && (
            <div style={{ padding: "0.625rem 0.875rem", backgroundColor: "rgba(245,158,11,0.06)", border: "0.5px solid rgba(245,158,11,0.2)", borderRadius: "10px", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
              <Info style={{ width: "14px", height: "14px", display: "inline", verticalAlign: "-2px", marginRight: "0.35rem" }} />Facebook Marketplace folosește sesiunea autentificată din <a href="/dashboard/settings" style={{ color: "#fbbf24" }}>Setări → Facebook</a>. Doar <strong>Închiriere</strong> e disponibil — categoria de vânzare Facebook nu conține anunțuri imobiliare reale.
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <Field label="Tip anunț">
              <select value={form.tip_anunt} onChange={(e) => set({ tip_anunt: e.target.value })} style={inputStyle}>
                <option value="vanzare" disabled={platform === "facebook_marketplace"}>
                  Vânzare{platform === "facebook_marketplace" ? " — indisponibil pe Facebook" : ""}
                </option>
                <option value="inchiriere">Închiriere</option>
              </select>
            </Field>
            <Field label="Tip proprietate">
              <select value={form.property_type} onChange={(e) => set({ property_type: e.target.value })} style={inputStyle}>
                <option value="">Toate</option>
                {PROPERTY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="Camere (min)">
              <input type="number" min="1" max="8" value={form.rooms} onChange={(e) => set({ rooms: e.target.value })} placeholder="ex: 2" style={inputStyle} />
            </Field>
            <Field label="Camere (max)">
              <input type="number" min="1" max="8" value={form.rooms_max} onChange={(e) => set({ rooms_max: e.target.value })} placeholder="fără plafon" style={inputStyle} />
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Pentru garsonieră: min 1, max 1.
              </div>
            </Field>
            <Field label="Suprafață min (mp)"><input type="number" value={form.area_min} onChange={(e) => set({ area_min: e.target.value })} placeholder="40" style={inputStyle} /></Field>
            <Field label="Suprafață max (mp)"><input type="number" value={form.area_max} onChange={(e) => set({ area_max: e.target.value })} placeholder="80" style={inputStyle} /></Field>
            <Field label="Preț min">
              <input type="number" value={form.price_min} onChange={(e) => set({ price_min: e.target.value })} placeholder="300" style={inputStyle} />
            </Field>
            <Field label="Preț max">
              <input type="number" value={form.price_max} onChange={(e) => set({ price_max: e.target.value })} placeholder="700" style={inputStyle} />
            </Field>
            <Field label="Monedă">
              <select value={form.price_currency} onChange={(e) => set({ price_currency: e.target.value })} style={inputStyle}>
                <option value="EUR">EUR</option>
                <option value="RON">RON</option>
              </select>
            </Field>
            <Field label="Oraș">
              <select value={form.city} onChange={(e) => set({ city: e.target.value })} style={inputStyle}>
                {CITIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Zonă"><input value={form.zone} onChange={(e) => set({ zone: e.target.value })} placeholder="ex: Floreasca, Dorobanți" style={inputStyle} /></Field>
            {showFloors && (
              <>
                <Field label="Etaj de la"><input type="number" value={form.floor_min} onChange={(e) => set({ floor_min: e.target.value })} placeholder="1" style={inputStyle} /></Field>
                <Field label="Etaj până la"><input type="number" value={form.floor_max} onChange={(e) => set({ floor_max: e.target.value })} placeholder="8" style={inputStyle} /></Field>
              </>
            )}
          </div>

          <Field label="Căutare liberă (opțional)">
            <input value={form.query} onChange={(e) => set({ query: e.target.value })} placeholder="ex: mobilat, parcare" style={inputStyle} />
          </Field>

          <Field label="Cuvinte excluse (titlu + descriere)">
            <div style={{ border: "1px solid var(--border-color)", borderRadius: "10px", background: "rgba(4,9,18,.45)", padding: "0.375rem 0.5rem", display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.375rem", minHeight: "2.5rem" }}>
              {excludeChips.map((chip) => (
                <span key={chip} style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", backgroundColor: "rgba(37,99,235,0.15)", border: "1px solid rgba(37,99,235,0.3)", color: "#60a5fa", fontSize: "0.75rem", padding: "0.125rem 0.5rem", borderRadius: "8px" }}>
                  {chip}
                  <button type="button" onClick={() => set({ exclude_words: excludeChips.filter((c) => c !== chip) })} style={{ background: "none", border: "none", color: "#60a5fa", cursor: "pointer", padding: 0, display: "flex" }}>
                    <X style={{ width: "12px", height: "12px" }} />
                  </button>
                </span>
              ))}
              <input
                type="text"
                value={chipInput}
                onChange={(e) => setChipInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addChip(); } }}
                placeholder="ex: demisol, regim hotelier (Enter)"
                style={{ flex: 1, minWidth: "140px", backgroundColor: "transparent", border: "none", color: "var(--text-primary)", fontSize: "0.8125rem", outline: "none", padding: "0.25rem" }}
              />
            </div>
            <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", margin: "0.375rem 0 0" }}>
              Anunțurile care conțin oricare dintre acești termeni sunt excluse (fără diacritice).
            </p>
          </Field>

          <Field label="Interval verificare">
            <select value={form.polling_interval} onChange={(e) => set({ polling_interval: parseInt(e.target.value) })} style={inputStyle}>
              {POLL_OPTIONS.map((m) => <option key={m} value={m}>{m} min</option>)}
            </select>
          </Field>

          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
              <input type="checkbox" id="re-use-hours" checked={form.use_active_hours} onChange={(e) => set({ use_active_hours: e.target.checked })} style={{ width: "15px", height: "15px", cursor: "pointer" }} />
              <label htmlFor="re-use-hours" style={{ fontSize: "0.875rem", color: "var(--text-primary)", cursor: "pointer" }}>Activ doar în interval orar</label>
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

          {/* Canale de notificare — identic cu Radar (NotifToggle partajat) */}
          <div style={{
            border: "1px solid var(--border-color)",
            borderRadius: "10px",
            padding: "1rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}>
            <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
              Canale de notificare
            </div>
            <NotifToggle
              label="Notificări Email"
              subtitle="Primești email pentru anunțuri imobiliare cu grad A/B"
              value={form.notify_email}
              onChange={(v) => set({ notify_email: v })}
            />
            <NotifToggle
              label="Notificări Discord"
              subtitle="Trimite la webhook-urile configurate în Setări"
              value={form.notify_discord}
              onChange={(v) => set({ notify_discord: v })}
            />
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
              Notificările in-app sunt întotdeauna active indiferent de selecție.
            </div>
          </div>
          <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-primary)", cursor: "pointer" }}>
            <input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} style={{ width: "auto" }} /> Activ
          </label>
        </div>

        <div style={modalFooterStyle}>
          <button onClick={onClose} style={{ padding: "0.5rem 1rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "10px", fontSize: "0.8125rem", fontWeight: 500, cursor: "pointer" }}>Anulează</button>
          <button onClick={onSubmit} disabled={saving} style={{ padding: "0.5rem 1.25rem", background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)", color: "#7ee7f8", border: "1px solid rgba(34,211,238,.42)", borderRadius: "10px", fontSize: "0.8125rem", fontWeight: 600, cursor: saving ? "wait" : "pointer", opacity: saving ? 0.7 : 1 }}>
            {saving ? "Se salvează..." : editing ? "Salvează" : "Adaugă"}
          </button>
        </div>
      </div>
    </div>
  );
}
