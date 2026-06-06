"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { radarAPI } from "@/lib/api";
import {
  Target, Plus, Pencil, Trash2, X, Save, ToggleLeft, ToggleRight, Bookmark, TrendingUp
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend
} from "recharts";

const PLATFORM_OPTIONS = [
  { value: "olx", label: "OLX" },
  { value: "vinted", label: "Vinted" },
  { value: "okazii", label: "Okazii" },
  { value: "facebook", label: "Facebook" },
  { value: "lajumate", label: "Lajumate" },
  { value: "publi24", label: "Publi24" },
  { value: "autovit", label: "Autovit" },
  { value: "mobilede", label: "Mobile.de" },
];

const CAR_FUEL_OPTIONS = [
  { value: "", label: "Orice" },
  { value: "benzina", label: "Benzină" },
  { value: "diesel", label: "Diesel" },
  { value: "hibrid", label: "Hibrid" },
  { value: "electric", label: "Electric" },
  { value: "gpl", label: "GPL" },
  { value: "gnc", label: "GNC" },
];

const CAR_BODY_OPTIONS = [
  { value: "", label: "Orice" },
  { value: "sedan", label: "Berlină" },
  { value: "suv", label: "SUV" },
  { value: "break", label: "Break" },
  { value: "hatchback", label: "Hatchback" },
  { value: "coupe", label: "Coupe" },
  { value: "cabrio", label: "Cabrio" },
  { value: "van", label: "Van" },
  { value: "pickup", label: "Pickup" },
];

const CAR_GEARBOX_OPTIONS = [
  { value: "", label: "Orice" },
  { value: "manuala", label: "Manuală" },
  { value: "automata", label: "Automată" },
];

const EMPTY_CAR_FILTERS = {
  marca: "", model: "",
  an_de_la: "", an_pana_la: "",
  km_maxim: "",
  combustibil: "", caroserie: "", cutie_viteze: "",
};

const CONDITION_OPTIONS = [
  { value: "all", label: "Toate" },
  { value: "new", label: "Nou" },
  { value: "used", label: "Second hand" },
];

const POLL_OPTIONS = [5, 10, 15, 30];

const FALLBACK_CATEGORIES = [
  "Telefoane", "Tablete", "Laptopuri", "Electronice",
  "Îmbrăcăminte", "Încălțăminte", "Jocuri", "Cărți",
  "Sport", "Casă și grădină", "Auto", "Altele",
];

const EMPTY_FORM = {
  name: "",
  max_price: "",
  min_price: "",
  resale_price: "",
  category: "",
  exclude_words: [],
  platforms: ["olx", "vinted", "okazii"],
  poll_interval_minutes: 5,
  judet: "",
  oras: "",
  condition: "all",
  is_active: true,
  min_margin_pct: 10.0,
  notify_email: true,
  notify_discord: true,
  car_filters: { ...EMPTY_CAR_FILTERS },
};

function feeCeiling(resale, platform) {
  const r = parseFloat(resale) || 0;
  const ship = 20;
  if (platform === "okazii") return Math.max(0, r * 0.92 - ship);
  return Math.max(0, r - ship);
}

export default function RadarKeywordsPage() {
  const [keywords, setKeywords] = useState([]);
  const [presets, setPresets] = useState([]);
  const [categories, setCategories] = useState(FALLBACK_CATEGORIES);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [excludeInput, setExcludeInput] = useState("");
  const [presetName, setPresetName] = useState("");
  const [trendKw, setTrendKw] = useState(null);
  const [trendData, setTrendData] = useState(null);
  const [trendDays, setTrendDays] = useState(30);
  const [trendLoading, setTrendLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [kw, ps, cat] = await Promise.all([
        radarAPI.getKeywords(),
        radarAPI.getPresets(),
        radarAPI.getCategories().catch(() => null),
      ]);
      setKeywords(kw.data || []);
      setPresets(ps.data || []);
      if (cat?.data?.categories?.length) setCategories(cat.data.categories);
    } catch (e) {
      console.error("[RadarKeywords]", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setExcludeInput("");
    setShowForm(true);
  };

  const openEdit = (kw) => {
    setEditingId(kw.id);
    setForm({
      name: kw.name,
      max_price: kw.max_price,
      min_price: kw.min_price ?? "",
      resale_price: kw.resale_price,
      category: kw.category || "",
      exclude_words: kw.exclude_words || [],
      platforms: kw.platforms || [],
      poll_interval_minutes: kw.poll_interval_minutes,
      judet: kw.judet || "",
      oras: kw.oras || "",
      condition: kw.condition,
      is_active: kw.is_active,
      min_margin_pct: kw.min_margin_pct,
      notify_email: kw.notify_email !== false,
      notify_discord: kw.notify_discord !== false,
      car_filters: { ...EMPTY_CAR_FILTERS, ...(kw.car_filters || {}) },
    });
    setExcludeInput("");
    setShowForm(true);
  };

  const togglePlatform = (p) => {
    setForm((prev) => ({
      ...prev,
      platforms: prev.platforms.includes(p)
        ? prev.platforms.filter((x) => x !== p)
        : [...prev.platforms, p],
    }));
  };

  const addExclude = () => {
    const w = excludeInput.trim();
    if (!w) return;
    if (!form.exclude_words.includes(w)) {
      setForm({ ...form, exclude_words: [...form.exclude_words, w] });
    }
    setExcludeInput("");
  };

  const removeExclude = (w) => {
    setForm({ ...form, exclude_words: form.exclude_words.filter((x) => x !== w) });
  };

  const submit = async (e) => {
    e?.preventDefault();
    const minPriceVal = form.min_price === "" || form.min_price === null ? null : parseFloat(form.min_price);
    // Compactează filtrele auto: trimite null dacă niciun câmp nu e completat.
    const cfRaw = form.car_filters || {};
    const cfCompact = {};
    for (const [k, v] of Object.entries(cfRaw)) {
      if (v === null || v === undefined) continue;
      if (typeof v === "string" && v.trim() === "") continue;
      if (["an_de_la", "an_pana_la", "km_maxim"].includes(k)) {
        const n = parseInt(v);
        if (!Number.isNaN(n) && n > 0) cfCompact[k] = n;
      } else {
        cfCompact[k] = String(v).trim();
      }
    }
    const carFiltersForSend = Object.keys(cfCompact).length > 0 ? cfCompact : null;
    const payload = {
      name: form.name.trim(),
      max_price: parseFloat(form.max_price),
      min_price: minPriceVal,
      resale_price: parseFloat(form.resale_price),
      category: form.category || null,
      exclude_words: form.exclude_words,
      platforms: form.platforms,
      poll_interval_minutes: parseInt(form.poll_interval_minutes) || 5,
      judet: form.judet || null,
      oras: form.oras || null,
      condition: form.condition,
      is_active: form.is_active,
      min_margin_pct: parseFloat(form.min_margin_pct) || 10.0,
      notify_email: !!form.notify_email,
      notify_discord: !!form.notify_discord,
      car_filters: carFiltersForSend,
    };
    if (!payload.name || !payload.max_price || !payload.resale_price) {
      alert("Numele, prețul maxim și prețul de revânzare sunt obligatorii.");
      return;
    }
    if (payload.min_price !== null && payload.min_price > payload.max_price) {
      alert("Prețul minim nu poate fi mai mare decât prețul maxim.");
      return;
    }
    if (payload.platforms.length === 0) {
      alert("Selectează cel puțin o platformă.");
      return;
    }
    try {
      if (editingId) {
        await radarAPI.updateKeyword(editingId, payload);
      } else {
        await radarAPI.createKeyword(payload);
      }
      setShowForm(false);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    }
  };

  const remove = async (id) => {
    if (!confirm("Sigur vrei să ștergi acest keyword? Anunțurile asociate vor fi șterse.")) return;
    try {
      await radarAPI.deleteKeyword(id);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la ștergere.");
    }
  };

  const toggle = async (id) => {
    try {
      await radarAPI.toggleKeyword(id);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la comutare.");
    }
  };

  const bulkSet = async (matcher, isActive) => {
    try {
      for (const kw of keywords) {
        if (matcher(kw) && kw.is_active !== isActive) {
          await radarAPI.updateKeyword(kw.id, { is_active: isActive });
        }
      }
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la actualizare în masă.");
    }
  };

  const savePreset = async () => {
    const n = presetName.trim();
    if (!n) {
      alert("Introdu un nume pentru preset.");
      return;
    }
    try {
      await radarAPI.savePreset({ name: n });
      setPresetName("");
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare preset.");
    }
  };

  const loadPreset = async (id) => {
    if (!confirm("Încărcarea presetului va adăuga noi keyword-uri. Continui?")) return;
    try {
      await radarAPI.loadPreset(id);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la încărcare preset.");
    }
  };

  const removePreset = async (id) => {
    if (!confirm("Ștergi presetul?")) return;
    try {
      await radarAPI.deletePreset(id);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la ștergere preset.");
    }
  };

  const openTrend = async (kw, days = 30) => {
    setTrendKw(kw);
    setTrendDays(days);
    setTrendData(null);
    setTrendLoading(true);
    try {
      const r = await radarAPI.keywordPriceTrend(kw.id, days);
      setTrendData(r.data);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la încărcarea trendului.");
      setTrendKw(null);
    } finally {
      setTrendLoading(false);
    }
  };

  const changeTrendDays = (days) => {
    if (!trendKw) return;
    openTrend(trendKw, days);
  };

  const marginPreview = useMemo(() => {
    const mp = parseFloat(form.max_price) || 0;
    const rp = parseFloat(form.resale_price) || 0;
    if (rp <= 0) return null;
    const v = rp - mp;
    const pct = (v / rp) * 100;
    return { value: v, pct };
  }, [form.max_price, form.resale_price]);

  const inputStyle = {
    width: "100%",
    backgroundColor: "var(--bg-dark)",
    border: "1px solid var(--border-color)",
    borderRadius: "0.5rem",
    padding: "0.5rem 0.75rem",
    color: "var(--text-primary)",
    fontSize: "0.875rem",
    outline: "none",
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Target style={{ width: "22px", height: "22px", color: "#2563eb" }} />
            Keyword-uri Urmărite
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Configurează ce caută Radar-ul pe platformele active ({keywords.length} keyword-uri)
          </p>
        </div>
        <button
          onClick={openCreate}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.5rem 0.875rem",
            backgroundColor: "var(--blue-primary)",
            color: "white",
            border: "none",
            borderRadius: "0.5rem",
            fontSize: "0.8125rem",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          <Plus style={{ width: "16px", height: "16px" }} />
          Adaugă keyword
        </button>
      </div>

      {/* Acțiuni în masă */}
      <div style={{
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "0.75rem",
        padding: "0.75rem",
        marginBottom: "1rem",
        display: "flex",
        flexWrap: "wrap",
        gap: "0.5rem",
      }}>
        <button onClick={() => bulkSet(() => true, true)} style={bulkBtn}>Activează toate</button>
        <button onClick={() => bulkSet(() => true, false)} style={bulkBtn}>Dezactivează toate</button>
        <button onClick={() => bulkSet((k) => k.platforms?.includes("olx"), true)} style={bulkBtn}>Activează OLX</button>
        <button onClick={() => bulkSet((k) => k.platforms?.includes("vinted"), true)} style={bulkBtn}>Activează Vinted</button>
        <button onClick={() => bulkSet((k) => k.platforms?.includes("okazii"), true)} style={bulkBtn}>Activează Okazii</button>
      </div>

      {/* Listă keyword-uri */}
      {keywords.length === 0 ? (
        <div style={{
          textAlign: "center",
          padding: "2.5rem",
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          color: "var(--text-secondary)",
        }}>
          Nu ai keyword-uri configurate. Apasă „Adaugă keyword" ca să începi.
        </div>
      ) : (
        <div style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          overflow: "hidden",
        }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
              <thead>
                <tr style={{ backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)" }}>
                  <th style={th}>Keyword</th>
                  <th style={th}>Preț min</th>
                  <th style={th}>Preț max</th>
                  <th style={th}>Revânzare</th>
                  <th style={th}>Marjă țintă</th>
                  <th style={th}>Categorie</th>
                  <th style={th}>Platforme</th>
                  <th style={th}>Interval</th>
                  <th style={th}>Notificări</th>
                  <th style={th}>Status</th>
                  <th style={th}>Acțiuni</th>
                </tr>
              </thead>
              <tbody>
                {keywords.map((k) => {
                  const m = k.resale_price > 0 ? ((k.resale_price - k.max_price) / k.resale_price) * 100 : 0;
                  return (
                    <tr key={k.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                      <td style={td}>{k.name}</td>
                      <td style={td}>{k.min_price ? `${Math.round(k.min_price)} RON` : "—"}</td>
                      <td style={td}>{Math.round(k.max_price)} RON</td>
                      <td style={td}>{Math.round(k.resale_price)} RON</td>
                      <td style={{ ...td, color: m >= 25 ? "#4ade80" : m >= 10 ? "#facc15" : "#fb923c" }}>
                        {Math.round(m)}%
                      </td>
                      <td style={td}>{k.category || "—"}</td>
                      <td style={td}>{(k.platforms || []).join(", ")}</td>
                      <td style={td}>{k.poll_interval_minutes} min</td>
                      <td style={td}>
                        <span style={{ display: "inline-flex", gap: "0.25rem", fontSize: "0.95rem" }}>
                          <span title="Email" style={{ opacity: k.notify_email ? 1 : 0.25 }}>📧</span>
                          <span title="Discord" style={{ opacity: k.notify_discord ? 1 : 0.25 }}>💬</span>
                        </span>
                      </td>
                      <td style={td}>
                        <button onClick={() => toggle(k.id)} style={{ background: "none", border: "none", cursor: "pointer", color: k.is_active ? "#4ade80" : "var(--text-muted)" }}>
                          {k.is_active ? <ToggleRight style={{ width: "22px", height: "22px" }} /> : <ToggleLeft style={{ width: "22px", height: "22px" }} />}
                        </button>
                      </td>
                      <td style={td}>
                        <div style={{ display: "flex", gap: "0.375rem" }}>
                          <button onClick={() => openTrend(k)} style={iconBtn} title="Trend preț">
                            <TrendingUp style={{ width: "14px", height: "14px" }} />
                          </button>
                          <button onClick={() => openEdit(k)} style={iconBtn} title="Editează">
                            <Pencil style={{ width: "14px", height: "14px" }} />
                          </button>
                          <button onClick={() => remove(k.id)} style={{ ...iconBtn, color: "#f87171" }} title="Șterge">
                            <Trash2 style={{ width: "14px", height: "14px" }} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Preseturi */}
      <div style={{
        marginTop: "1.5rem",
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "0.75rem",
        padding: "1rem",
      }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.75rem" }}>Preseturi Salvate</h2>
        {presets.length === 0 ? (
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", marginBottom: "0.75rem" }}>Nu ai preseturi salvate.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "0.75rem" }}>
            {presets.map((p) => (
              <div key={p.id} style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "0.5rem 0.75rem", backgroundColor: "var(--bg-dark)",
                border: "1px solid var(--border-color)", borderRadius: "0.5rem",
              }}>
                <div style={{ fontSize: "0.875rem", color: "var(--text-primary)" }}>
                  <strong>{p.name}</strong>{" "}
                  <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                    ({(p.keywords_config || []).length} keyword-uri)
                  </span>
                </div>
                <div style={{ display: "flex", gap: "0.375rem" }}>
                  <button onClick={() => loadPreset(p.id)} style={smallBtn("#60a5fa")}>Încarcă</button>
                  <button onClick={() => removePreset(p.id)} style={smallBtn("#f87171")}>Șterge</button>
                </div>
              </div>
            ))}
          </div>
        )}
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="text"
            placeholder="Nume preset nou..."
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            style={{ ...inputStyle, flex: 1 }}
          />
          <button
            onClick={savePreset}
            style={{
              padding: "0.5rem 0.875rem",
              backgroundColor: "rgba(22,163,74,0.15)",
              color: "#4ade80",
              border: "1px solid rgba(22,163,74,0.3)",
              borderRadius: "0.5rem",
              fontSize: "0.8125rem",
              fontWeight: 600,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.375rem",
            }}
          >
            <Bookmark style={{ width: "14px", height: "14px" }} />
            Salvează configurația curentă
          </button>
        </div>
      </div>

      {/* Formular modal */}
      {showForm && (
        <div
          onClick={() => setShowForm(false)}
          style={{
            position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 100, padding: "1.5rem",
          }}
        >
          <form
            onClick={(e) => e.stopPropagation()}
            onSubmit={submit}
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "0.875rem",
              maxWidth: "620px",
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
              padding: "1.25rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
              <h2 style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                {editingId ? "Editează keyword" : "Adaugă keyword"}
              </h2>
              <button type="button" onClick={() => setShowForm(false)} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}>
                <X style={{ width: "20px", height: "20px" }} />
              </button>
            </div>

            <div style={{ display: "grid", gap: "0.75rem" }}>
              <Field label="Keyword">
                <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="iPhone 13" style={inputStyle} required />
              </Field>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Field label="Preț maxim achiziție (RON)">
                  <input type="number" value={form.max_price} onChange={(e) => setForm({ ...form, max_price: e.target.value })} style={inputStyle} required min="0" step="any" />
                </Field>
                <Field label="Preț estimat revânzare (RON)">
                  <input type="number" value={form.resale_price} onChange={(e) => setForm({ ...form, resale_price: e.target.value })} style={inputStyle} required min="0" step="any" />
                </Field>
              </div>

              <Field label="Preț minim achiziție (RON) — opțional">
                <input
                  type="number"
                  value={form.min_price}
                  onChange={(e) => setForm({ ...form, min_price: e.target.value })}
                  placeholder="ex: 100"
                  style={inputStyle}
                  min="0"
                  step="any"
                />
                <small style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>
                  Util pentru a exclude accesorii ieftine (huse, cabluri etc.)
                </small>
              </Field>

              <Field label="Categorie">
                <select
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  style={inputStyle}
                >
                  <option value="">Toate categoriile</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
                <small style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>
                  Selectarea categoriei reduce rezultatele irelevante (ex: alege Telefoane pentru a exclude husele și accesoriile)
                </small>
              </Field>

              {marginPreview && (
                <div style={{ padding: "0.5rem 0.75rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem" }}>
                  Marjă estimată: <strong style={{ color: marginPreview.pct >= 25 ? "#4ade80" : marginPreview.pct >= 10 ? "#facc15" : "#fb923c" }}>
                    {Math.round(marginPreview.value)} RON ({Math.round(marginPreview.pct)}%)
                  </strong>
                  {parseFloat(form.min_price) > 0 && (
                    <div style={{ marginTop: "0.25rem", color: "var(--text-secondary)", fontSize: "0.75rem" }}>
                      Interval preț: {Math.round(parseFloat(form.min_price))} — {Math.round(parseFloat(form.max_price) || 0)} RON
                    </div>
                  )}
                  {form.platforms.length > 0 && (
                    <div style={{ marginTop: "0.375rem", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                      Fee ceiling: {form.platforms.map((p) => `${p.toUpperCase()}: ${Math.round(feeCeiling(form.resale_price, p))} RON`).join(" · ")}
                    </div>
                  )}
                </div>
              )}

              <Field label="Exclude cuvinte (Enter pentru a adăuga)">
                <div style={{
                  border: "1px solid var(--border-color)",
                  backgroundColor: "var(--bg-dark)",
                  borderRadius: "0.5rem",
                  padding: "0.375rem 0.5rem",
                  display: "flex", flexWrap: "wrap", gap: "0.375rem",
                  alignItems: "center",
                }}>
                  {form.exclude_words.map((w) => (
                    <span key={w} style={{
                      backgroundColor: "rgba(239,68,68,0.15)",
                      border: "1px solid rgba(239,68,68,0.3)",
                      color: "#f87171",
                      padding: "0.125rem 0.5rem",
                      borderRadius: "0.375rem",
                      fontSize: "0.75rem",
                      display: "inline-flex", alignItems: "center", gap: "0.25rem",
                    }}>
                      {w}
                      <button type="button" onClick={() => removeExclude(w)} style={{ background: "none", border: "none", color: "#f87171", cursor: "pointer", padding: 0, display: "flex" }}>
                        <X style={{ width: "12px", height: "12px" }} />
                      </button>
                    </span>
                  ))}
                  <input
                    type="text"
                    value={excludeInput}
                    onChange={(e) => setExcludeInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addExclude(); } }}
                    placeholder="defect, stricat, ..."
                    style={{
                      flex: 1, minWidth: "120px",
                      backgroundColor: "transparent !important",
                      border: "none !important",
                      color: "var(--text-primary) !important",
                      fontSize: "0.8125rem", outline: "none", padding: "0.25rem",
                    }}
                  />
                </div>
              </Field>

              <Field label="Platforme active">
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  {PLATFORM_OPTIONS.map((p) => {
                    const on = form.platforms.includes(p.value);
                    return (
                      <button
                        key={p.value}
                        type="button"
                        onClick={() => togglePlatform(p.value)}
                        style={{
                          padding: "0.375rem 0.75rem",
                          backgroundColor: on ? "rgba(37,99,235,0.15)" : "var(--bg-dark)",
                          color: on ? "#60a5fa" : "var(--text-secondary)",
                          border: `1px solid ${on ? "rgba(37,99,235,0.3)" : "var(--border-color)"}`,
                          borderRadius: "0.5rem",
                          fontSize: "0.8125rem",
                          fontWeight: 500,
                          cursor: "pointer",
                        }}
                      >
                        {on ? "✓ " : ""}{p.label}
                      </button>
                    );
                  })}
                </div>
              </Field>

              {(form.platforms.includes("autovit") || form.platforms.includes("mobilede")) && (
                <CarFiltersSection
                  value={form.car_filters || EMPTY_CAR_FILTERS}
                  onChange={(cf) => setForm({ ...form, car_filters: cf })}
                  inputStyle={inputStyle}
                />
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Field label="Interval polling">
                  <select value={form.poll_interval_minutes} onChange={(e) => setForm({ ...form, poll_interval_minutes: parseInt(e.target.value) })} style={inputStyle}>
                    {POLL_OPTIONS.map((m) => <option key={m} value={m}>{m} min</option>)}
                  </select>
                </Field>
                <Field label="Stare produs">
                  <select value={form.condition} onChange={(e) => setForm({ ...form, condition: e.target.value })} style={inputStyle}>
                    {CONDITION_OPTIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </Field>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Field label="Județ (opțional)">
                  <input type="text" value={form.judet} onChange={(e) => setForm({ ...form, judet: e.target.value })} placeholder="București, Cluj..." style={inputStyle} />
                </Field>
                <Field label="Oraș (opțional)">
                  <input type="text" value={form.oras} onChange={(e) => setForm({ ...form, oras: e.target.value })} placeholder="București, Cluj-Napoca..." style={inputStyle} />
                </Field>
              </div>

              <Field label="Marjă minimă AI Filter (%)">
                <input type="number" value={form.min_margin_pct} onChange={(e) => setForm({ ...form, min_margin_pct: e.target.value })} step="any" min="0" style={inputStyle} />
                <small style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>
                  Listingurile cu marjă sub acest procent sunt ascunse implicit din feed.
                </small>
              </Field>

              <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", padding: "0.375rem 0.5rem", color: "var(--text-primary)", fontSize: "0.8125rem", cursor: "pointer" }}>
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} style={{ width: "auto" }} />
                Activ
              </label>

              <div style={{
                backgroundColor: "transparent",
                border: "1px solid var(--border-color)",
                borderRadius: "0.5rem",
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
                  subtitle="Primești email pentru dealuri cu scor A și B"
                  value={form.notify_email}
                  onChange={(v) => setForm({ ...form, notify_email: v })}
                />
                <NotifToggle
                  label="Notificări Discord"
                  subtitle="Trimite la webhook-urile configurate în Setări Radar"
                  value={form.notify_discord}
                  onChange={(v) => setForm({ ...form, notify_discord: v })}
                />

                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                  Notificările in-app sunt întotdeauna active indiferent de selecție.
                </div>
              </div>
            </div>

            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button type="button" onClick={() => setShowForm(false)} style={{ padding: "0.5rem 0.875rem", backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem", cursor: "pointer" }}>
                Anulează
              </button>
              <button type="submit" style={{ padding: "0.5rem 0.875rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                <Save style={{ width: "14px", height: "14px" }} />
                Salvează
              </button>
            </div>
          </form>
        </div>
      )}

      {trendKw && (
        <TrendModal
          kw={trendKw}
          data={trendData}
          days={trendDays}
          loading={trendLoading}
          onClose={() => { setTrendKw(null); setTrendData(null); }}
          onDaysChange={changeTrendDays}
        />
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function TrendModal({ kw, data, days, loading, onClose, onDaysChange }) {
  const trendColors = {
    crescator: { bg: "rgba(239,68,68,0.15)", border: "#ef4444", text: "#fca5a5", label: "↑ Crescător" },
    descrescator: { bg: "rgba(22,163,74,0.15)", border: "#16a34a", text: "#4ade80", label: "↓ Descrescător" },
    stabil: { bg: "rgba(100,116,139,0.15)", border: "#64748b", text: "#94a3b8", label: "→ Stabil" },
  };
  const trendCfg = trendColors[data?.trend_direction] || trendColors.stabil;
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 100, padding: "1.5rem",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.875rem",
          maxWidth: "900px", width: "100%",
          maxHeight: "90vh", overflowY: "auto",
          padding: "1.25rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem", flexWrap: "wrap", gap: "0.5rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>
            Evoluție preț — {kw.name}
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}>
            <X style={{ width: "20px", height: "20px" }} />
          </button>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.875rem" }}>
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => onDaysChange(d)}
              style={{
                padding: "0.375rem 0.75rem",
                backgroundColor: days === d ? "var(--blue-primary)" : "var(--bg-dark)",
                color: days === d ? "white" : "var(--text-secondary)",
                border: "1px solid var(--border-color)",
                borderRadius: "0.5rem",
                fontSize: "0.8125rem",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Ultimele {d} zile
            </button>
          ))}
        </div>

        {loading ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "300px" }}>
            <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
          </div>
        ) : !data || data.series.length === 0 ? (
          <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
            Nu există date suficiente pentru intervalul selectat.
          </div>
        ) : (
          <>
            <div style={{ height: "320px", width: "100%" }}>
              <ResponsiveContainer>
                <LineChart data={data.series} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border-color)" strokeDasharray="3 3" />
                  <XAxis dataKey="date" stroke="var(--text-muted)" style={{ fontSize: "0.7rem" }} />
                  <YAxis stroke="var(--text-muted)" style={{ fontSize: "0.7rem" }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.75rem" }}
                    labelStyle={{ color: "var(--text-primary)" }}
                  />
                  <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
                  <Line type="monotone" dataKey="avg_price" name="Preț mediu" stroke="#60a5fa" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="min_price" name="Cel mai mic" stroke="#4ade80" strokeDasharray="4 3" strokeWidth={1.5} dot={false} />
                  <Line type="monotone" dataKey="max_price" name="Cel mai mare" stroke="#f87171" strokeDasharray="4 3" strokeWidth={1.5} dot={false} />
                  {kw.max_price ? (
                    <ReferenceLine y={kw.max_price} stroke="#facc15" strokeDasharray="6 4" label={{ value: "Bugetul tău max", position: "right", fontSize: 10, fill: "#facc15" }} />
                  ) : null}
                  {kw.resale_price ? (
                    <ReferenceLine y={kw.resale_price} stroke="#a78bfa" strokeDasharray="6 4" label={{ value: "Preț revânzare", position: "right", fontSize: 10, fill: "#a78bfa" }} />
                  ) : null}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem", marginTop: "0.875rem" }}>
              <StatCard label="Preț mediu" value={`${Math.round(data.overall_avg)} RON`} color="#60a5fa" />
              <StatCard label="Cel mai mic găsit" value={`${Math.round(data.overall_min)} RON`} color="#4ade80" />
              <div style={{
                padding: "0.75rem", backgroundColor: "var(--bg-dark)",
                border: `1px solid ${trendCfg.border}`, borderRadius: "0.5rem", textAlign: "center",
              }}>
                <div style={{ fontSize: "1rem", fontWeight: 700, color: trendCfg.text }}>{trendCfg.label}</div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>Tendință</div>
              </div>
            </div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic", marginTop: "0.5rem" }}>
              Graficul se bazează pe listingurile găsite de FlipRadar. Primele zile pot avea date incomplete.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{ padding: "0.75rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", textAlign: "center" }}>
      <div style={{ fontSize: "1rem", fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>{label}</div>
    </div>
  );
}

function NotifToggle({ label, subtitle, value, onChange }) {
  const on = !!value;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "0.8125rem", color: "var(--text-primary)", fontWeight: 500 }}>{label}</div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>{subtitle}</div>
      </div>
      <button
        type="button"
        onClick={() => onChange(!on)}
        aria-pressed={on}
        style={{
          width: 44, height: 24, borderRadius: 12,
          backgroundColor: on ? "var(--blue-primary)" : "var(--border-color)",
          border: "none", padding: 2, cursor: "pointer",
          position: "relative",
          transition: "background-color 0.15s ease",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: on ? 22 : 2,
            width: 20, height: 20, borderRadius: "50%",
            backgroundColor: "#ffffff",
            transition: "left 0.15s ease",
            boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
          }}
        />
      </button>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label style={{ display: "block" }}>
      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>{label}</div>
      {children}
    </label>
  );
}

const th = { textAlign: "left", padding: "0.625rem 0.75rem", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" };
const td = { padding: "0.625rem 0.75rem", color: "var(--text-primary)" };
const iconBtn = {
  padding: "0.375rem",
  backgroundColor: "var(--bg-dark)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.375rem",
  color: "var(--text-secondary)",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
};

const bulkBtn = {
  padding: "0.375rem 0.75rem",
  backgroundColor: "var(--bg-dark)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.5rem",
  color: "var(--text-secondary)",
  fontSize: "0.75rem",
  fontWeight: 500,
  cursor: "pointer",
};

function smallBtn(color) {
  return {
    padding: "0.3rem 0.625rem",
    backgroundColor: "var(--bg-card)",
    color: color,
    border: `1px solid ${color}55`,
    borderRadius: "0.375rem",
    fontSize: "0.75rem",
    fontWeight: 500,
    cursor: "pointer",
  };
}


function CarFiltersSection({ value, onChange, inputStyle }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div style={{
      backgroundColor: "var(--bg-dark)",
      border: "1px solid var(--border-color)",
      borderRadius: "0.5rem",
      padding: "0.875rem",
      display: "flex",
      flexDirection: "column",
      gap: "0.625rem",
    }}>
      <div>
        <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "0.375rem" }}>
          🚗 Filtre specifice platformelor auto
        </div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
          Aceste filtre se aplică doar pentru Autovit și Mobile.de.
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.625rem" }}>
        <Field label="Marcă">
          <input type="text" value={value.marca || ""} onChange={(e) => set("marca", e.target.value)} placeholder="ex: BMW, Audi, Dacia..." style={inputStyle} />
        </Field>
        <Field label="Model">
          <input type="text" value={value.model || ""} onChange={(e) => set("model", e.target.value)} placeholder="ex: X5, Golf, Logan..." style={inputStyle} />
        </Field>
        <Field label="An fabricație de la">
          <input type="number" min="1980" max="2030" value={value.an_de_la || ""} onChange={(e) => set("an_de_la", e.target.value)} placeholder="ex: 2018" style={inputStyle} />
        </Field>
        <Field label="An fabricație până la">
          <input type="number" min="1980" max="2030" value={value.an_pana_la || ""} onChange={(e) => set("an_pana_la", e.target.value)} placeholder="ex: 2023" style={inputStyle} />
        </Field>
        <Field label="Kilometri maximi">
          <input type="number" min="0" value={value.km_maxim || ""} onChange={(e) => set("km_maxim", e.target.value)} placeholder="ex: 150000" style={inputStyle} />
        </Field>
        <Field label="Combustibil">
          <select value={value.combustibil || ""} onChange={(e) => set("combustibil", e.target.value)} style={inputStyle}>
            {CAR_FUEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Caroserie">
          <select value={value.caroserie || ""} onChange={(e) => set("caroserie", e.target.value)} style={inputStyle}>
            {CAR_BODY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Cutie viteze">
          <select value={value.cutie_viteze || ""} onChange={(e) => set("cutie_viteze", e.target.value)} style={inputStyle}>
            {CAR_GEARBOX_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
      </div>

      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
        Câmpurile de mai sus nu sunt obligatorii. Cu cât adaugi mai multe filtre, cu atât rezultatele vor fi mai precise și mai puțin zgomot în feed.
      </div>
    </div>
  );
}
