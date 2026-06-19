"use client";
// FlipRadar — Modulul 1 Marketplace: wizard 3 pasi pentru alerte keyword.
// Reutilizabil: primeste onSubmit(config) cu { platform, keyword, category, subcategory, filters }.
import { useState } from "react";
import { X } from "lucide-react";
import {
  MARKETPLACE_PLATFORMS, PLATFORM_LONG_LABEL, MARKETPLACE_CATEGORIES,
  CONDITION_BY_PLATFORM, FACEBOOK_DISTANCES, KLEIN_RADIUS, KLEIN_OFFER_TYPES, JUDETE,
} from "@/lib/marketplaceConstants";

const EMPTY = { platform: "", keyword: "", category: "", subcategory: "", filters: {} };

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
  fontSize: "0.875rem", outline: "none",
};
const wlabel = { display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" };

export default function MarketplaceKeywordWizard({ open, onClose, onSubmit }) {
  const [step, setStep] = useState(1);
  const [data, setData] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  if (!open) return null;

  const f = data.filters || {};
  const plat = data.platform;

  const reset = () => { setData(EMPTY); setStep(1); setSaving(false); };
  const close = () => { reset(); onClose?.(); };

  const setFilter = (key, value) => setData((p) => ({ ...p, filters: { ...p.filters, [key]: value } }));
  const toggleCondition = (value) => setData((p) => {
    const cur = Array.isArray(p.filters.condition) ? p.filters.condition : [];
    const next = cur.includes(value) ? cur.filter((c) => c !== value) : [...cur, value];
    return { ...p, filters: { ...p.filters, condition: next } };
  });

  const canNext = () => {
    if (step === 1) return !!data.platform;
    if (step === 2) return !!data.keyword.trim();
    return true;
  };

  const submit = async () => {
    if (!data.keyword.trim()) return;
    const cleanFilters = {};
    for (const [k, v] of Object.entries(f)) {
      if (v == null || v === "") continue;
      if (Array.isArray(v) && v.length === 0) continue;
      if ((k === "price_min" || k === "price_max") && Number.isFinite(parseFloat(v))) cleanFilters[k] = parseFloat(v);
      else cleanFilters[k] = v;
    }
    setSaving(true);
    try {
      await onSubmit?.({
        platform: data.platform,
        keyword: data.keyword.trim(),
        category: data.category || null,
        subcategory: data.subcategory || null,
        filters: cleanFilters,
      });
      reset();
    } finally {
      setSaving(false);
    }
  };

  const primaryBtn = { padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600 };
  const secondaryBtn = { padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500 };

  const renderCondition = () => (
    <div>
      <label style={wlabel}>Stare</label>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        {(CONDITION_BY_PLATFORM[plat] || []).map((c) => {
          const checked = Array.isArray(f.condition) && f.condition.includes(c);
          return (
            <label key={c} style={{
              display: "inline-flex", alignItems: "center", gap: "0.375rem", fontSize: "0.8125rem",
              color: checked ? "var(--blue-light)" : "var(--text-secondary)", cursor: "pointer",
              padding: "0.3rem 0.6rem", border: `1px solid ${checked ? "var(--blue-primary)" : "var(--border-color)"}`,
              borderRadius: "0.5rem", backgroundColor: checked ? "var(--blue-dim)" : "transparent",
            }}>
              <input type="checkbox" checked={checked} onChange={() => toggleCondition(c)} />
              {c}
            </label>
          );
        })}
      </div>
    </div>
  );

  const renderPrice = () => (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
      <div>
        <label style={wlabel}>Pret min (RON)</label>
        <input type="number" value={f.price_min ?? ""} onChange={(e) => setFilter("price_min", e.target.value)} placeholder="ex: 500" style={inputStyle} />
      </div>
      <div>
        <label style={wlabel}>Pret max (RON)</label>
        <input type="number" value={f.price_max ?? ""} onChange={(e) => setFilter("price_max", e.target.value)} placeholder="ex: 2000" style={inputStyle} />
      </div>
    </div>
  );

  const renderJudet = () => (
    <div>
      <label style={wlabel}>Judet</label>
      <select value={f.location_county || ""} onChange={(e) => setFilter("location_county", e.target.value)} style={inputStyle}>
        <option value="">Toate judetele</option>
        {JUDETE.map((j) => <option key={j} value={j}>{j}</option>)}
      </select>
    </div>
  );

  return (
    <div onClick={close} style={{
      position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", zIndex: 100,
      display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "3rem 1rem", overflowY: "auto",
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: "100%", maxWidth: "640px", backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)", borderRadius: "0.875rem", padding: "1.5rem",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            Adauga alerta — Pasul {step} din 3
          </h2>
          <button onClick={close} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}>
            <X style={{ width: "20px", height: "20px" }} />
          </button>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
          {[1, 2, 3].map((s) => (
            <div key={s} style={{ flex: 1, height: "4px", borderRadius: "2px", backgroundColor: s <= step ? "var(--blue-primary)" : "var(--border-color)" }} />
          ))}
        </div>

        {/* PAS 1 */}
        {step === 1 && (
          <div>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: 0, marginBottom: "0.875rem" }}>
              Alege platforma pe care vrei sa monitorizezi anunturile.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: "0.625rem" }}>
              {MARKETPLACE_PLATFORMS.map((p) => {
                const active = data.platform === p.value;
                return (
                  <button key={p.value} type="button" onClick={() => setData({ ...EMPTY, platform: p.value })}
                    style={{
                      padding: "0.875rem", borderRadius: "0.625rem", cursor: "pointer", textAlign: "left",
                      fontSize: "0.8125rem", fontWeight: 600,
                      backgroundColor: active ? "var(--blue-dim)" : "var(--bg-dark)",
                      color: active ? "var(--blue-light)" : "var(--text-primary)",
                      border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}`,
                    }}>
                    {PLATFORM_LONG_LABEL[p.value] || p.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* PAS 2 */}
        {step === 2 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
            <div>
              <label style={wlabel}>Keyword *</label>
              <input value={data.keyword} onChange={(e) => setData({ ...data, keyword: e.target.value })}
                placeholder="ex: iPhone 14 Pro" style={inputStyle} autoFocus />
            </div>
            <div>
              <label style={wlabel}>Categorie principala</label>
              <select value={data.category} onChange={(e) => setData({ ...data, category: e.target.value, subcategory: "" })} style={inputStyle}>
                <option value="">Alege categoria</option>
                {(MARKETPLACE_CATEGORIES[plat] || []).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
            </div>
            {data.category && (
              <div>
                <label style={wlabel}>Sub-categorie</label>
                <select value={data.subcategory} onChange={(e) => setData({ ...data, subcategory: e.target.value })} style={inputStyle}>
                  <option value="">Toate sub-categoriile</option>
                  {((MARKETPLACE_CATEGORIES[plat] || []).find((c) => c.name === data.category)?.sub || []).map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            )}
          </div>
        )}

        {/* PAS 3 */}
        {step === 3 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>
              Filtre pentru <strong style={{ color: "var(--text-primary)" }}>{PLATFORM_LONG_LABEL[plat] || plat}</strong>
            </p>

            {plat === "olx" && (<>
              {renderCondition()}
              {renderPrice()}
              {renderJudet()}
              <div>
                <label style={wlabel}>Oras</label>
                <input value={f.location_city || ""} onChange={(e) => setFilter("location_city", e.target.value)} placeholder="ex: Cluj-Napoca" style={inputStyle} />
              </div>
            </>)}

            {plat === "vinted" && (<>
              {renderCondition()}
              <div>
                <label style={wlabel}>Marime</label>
                <input value={f.size || ""} onChange={(e) => setFilter("size", e.target.value)} placeholder="ex: M, 42, 9.5" style={inputStyle} />
              </div>
              {renderPrice()}
            </>)}

            {plat === "facebook" && (<>
              {renderCondition()}
              {renderPrice()}
              <div>
                <label style={wlabel}>Locatie (oras)</label>
                <input value={f.location_city || ""} onChange={(e) => setFilter("location_city", e.target.value)} placeholder="ex: Bucuresti" style={inputStyle} />
              </div>
              <div>
                <label style={wlabel}>Distanta</label>
                <select value={f.distance_km || ""} onChange={(e) => setFilter("distance_km", e.target.value)} style={inputStyle}>
                  <option value="">Oricare</option>
                  {FACEBOOK_DISTANCES.map((d) => <option key={d} value={d}>{d} km</option>)}
                </select>
              </div>
            </>)}

            {(plat === "lajumate" || plat === "publi24" || plat === "okazii") && (<>
              {renderCondition()}
              {renderPrice()}
              {renderJudet()}
            </>)}

            {plat === "kleinanzeigen" && (<>
              <div>
                <label style={wlabel}>Tip oferta</label>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  {KLEIN_OFFER_TYPES.map((t) => {
                    const active = f.offer_type === t;
                    return (
                      <button key={t} type="button" onClick={() => setFilter("offer_type", t)}
                        style={{ flex: 1, padding: "0.5rem", borderRadius: "0.5rem", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600,
                          backgroundColor: active ? "var(--blue-dim)" : "var(--bg-dark)", color: active ? "var(--blue-light)" : "var(--text-primary)",
                          border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}` }}>
                        {t}
                      </button>
                    );
                  })}
                </div>
              </div>
              {renderCondition()}
              <div>
                <label style={wlabel}>PLZ (cod postal, 5 cifre)</label>
                <input value={f.plz || ""} maxLength={5}
                  onChange={(e) => setFilter("plz", e.target.value.replace(/\D/g, "").slice(0, 5))}
                  placeholder="ex: 10115" style={inputStyle} />
              </div>
              <div>
                <label style={wlabel}>Raza</label>
                <select value={f.radius_km || ""} onChange={(e) => setFilter("radius_km", e.target.value)} style={inputStyle}>
                  <option value="">Oricare</option>
                  {KLEIN_RADIUS.map((r) => <option key={r} value={r}>{r} km</option>)}
                </select>
              </div>
            </>)}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1.5rem" }}>
          <button type="button" onClick={() => (step > 1 ? setStep(step - 1) : close())} style={secondaryBtn}>
            {step > 1 ? "Inapoi" : "Anuleaza"}
          </button>
          {step < 3 ? (
            <button type="button" disabled={!canNext()} onClick={() => canNext() && setStep(step + 1)}
              style={{ ...primaryBtn, opacity: canNext() ? 1 : 0.5, cursor: canNext() ? "pointer" : "not-allowed" }}>
              Continua
            </button>
          ) : (
            <button type="button" onClick={submit} disabled={saving} style={{ ...primaryBtn, opacity: saving ? 0.7 : 1 }}>
              {saving ? "Se salveaza..." : "Salveaza alerta"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
