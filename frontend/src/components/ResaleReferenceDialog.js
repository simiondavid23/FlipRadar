"use client";
import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import { resaleAPI } from "@/lib/api";

/**
 * FASHION-3b — dialog de adaugare / editare a unei referinte de revanzare.
 *
 * Net-ul NU se calculeaza aici: vine de la POST /api/resale/net-preview, care
 * refoloseste exact `compute_net_ron`. O a doua implementare in JS ar diverge
 * tacut de backend la prima schimbare de reguli, iar userul ar vedea in dialog
 * alt numar decat cel salvat.
 */

const CURRENCIES = ["EUR", "USD", "RON"];

const overlayStyle = {
  position: "fixed", inset: 0, background: "rgba(2,5,12,0.72)", backdropFilter: "blur(6px)", zIndex: 100,
  display: "flex", alignItems: "flex-start", justifyContent: "center",
  padding: "3rem 1rem", overflowY: "auto",
};
const cardStyle = {
  width: "100%", maxWidth: "520px", background: "var(--bg-card)", backdropFilter: "blur(20px)",
  border: "1px solid var(--border-color)", borderRadius: "14px", padding: "1.5rem",
};
const inputStyle = {
  width: "100%", background: "rgba(4,9,18,.45)", border: "1px solid var(--border-color)",
  borderRadius: "10px", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
  fontSize: "0.875rem", outline: "none",
};
const labelStyle = {
  display: "block", fontSize: "0.75rem", fontWeight: 600,
  color: "var(--text-secondary)", marginBottom: "0.375rem",
};
const primaryBtn = {
  padding: "9px 18px", borderRadius: "12px", background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)", color: "#7ee7f8", border: "1px solid rgba(34,211,238,.42)", border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600,
};
const secondaryBtn = {
  padding: "0.5rem 1.25rem", borderRadius: "10px", backgroundColor: "transparent",
  color: "var(--text-secondary)", border: "1px solid var(--border-color)",
  cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
};

const ALL_SIZES = "__all__";      // marcheaza optiunea "Toate marimile" ('' in backend)
const CUSTOM_SIZE = "__custom__";

export default function ResaleReferenceDialog({ productId, reference, sizes = [], onClose, onSaved }) {
  const editing = Boolean(reference);

  const [profiles, setProfiles] = useState([]);
  const [platform, setPlatform] = useState(reference?.platform || "");
  const [sizeChoice, setSizeChoice] = useState(() => {
    if (!reference) return ALL_SIZES;
    if (!reference.variant) return ALL_SIZES;
    return sizes.includes(reference.variant) ? reference.variant : CUSTOM_SIZE;
  });
  const [customSize, setCustomSize] = useState(
    reference && reference.variant && !sizes.includes(reference.variant) ? reference.variant : ""
  );
  const [price, setPrice] = useState(reference?.ref_price ?? "");
  const [currency, setCurrency] = useState(reference?.ref_currency || "EUR");
  const [sourceUrl, setSourceUrl] = useState(reference?.source_url || "");

  const [net, setNet] = useState(reference?.net ?? null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Profilurile se iau LA DESCHIDERE: apelul declanseaza si seed-ul din backend,
  // deci lista nu poate fi goala la prima folosire a functionalitatii.
  useEffect(() => {
    let alive = true;
    resaleAPI.getFeeProfiles()
      .then((res) => {
        if (!alive) return;
        setProfiles(res.data);
        setPlatform((curr) => curr || res.data[0]?.platform || "");
      })
      .catch(() => setError("Nu am putut incarca profilurile de taxe."));
    return () => { alive = false; };
  }, []);

  const refreshNet = useCallback(async () => {
    const parsed = Number(price);
    if (!platform || !isFinite(parsed) || parsed <= 0) {
      setNet(null);
      return;
    }
    try {
      const res = await resaleAPI.netPreview({
        platform, ref_price: parsed, ref_currency: currency,
      });
      setNet(res.data);
    } catch {
      setNet(null);   // fara curs valutar sau eroare: nu afisam un net gresit
    }
  }, [platform, price, currency]);

  // Selecturile recalculeaza imediat; pretul recalculeaza la blur (vezi input).
  useEffect(() => { refreshNet(); }, [platform, currency]);  // eslint-disable-line react-hooks/exhaustive-deps

  const variantValue = () => {
    if (sizeChoice === ALL_SIZES) return "";
    if (sizeChoice === CUSTOM_SIZE) return customSize.trim();
    return sizeChoice;
  };

  const save = async () => {
    const parsed = Number(price);
    if (!isFinite(parsed) || parsed <= 0) {
      setError("Pretul de referinta trebuie sa fie un numar mai mare decat 0.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (editing) {
        await resaleAPI.updateReference(reference.id, {
          ref_price: parsed, ref_currency: currency, source_url: sourceUrl.trim() || null,
        });
      } else {
        await resaleAPI.createReference(productId, {
          platform, variant: variantValue(), ref_price: parsed,
          ref_currency: currency, source_url: sourceUrl.trim() || null,
        });
      }
      onSaved();
    } catch (e) {
      setError(e.response?.data?.detail || "Nu am putut salva referinta.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div onClick={onClose} style={overlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            {editing ? "Editeaza referinta" : "Adauga referinta de revanzare"}
          </h2>
          <button onClick={onClose} title="Inchide"
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}>
            <X style={{ width: "20px", height: "20px" }} />
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <div>
            <label style={labelStyle}>Platforma</label>
            <select value={platform} onChange={(e) => setPlatform(e.target.value)}
              disabled={editing} style={{ ...inputStyle, opacity: editing ? 0.6 : 1 }}>
              {profiles.map((p) => <option key={p.id} value={p.platform}>{p.label}</option>)}
            </select>
            {editing && (
              <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Platforma si marimea nu se schimba — sterge referinta si adauga alta.
              </p>
            )}
          </div>

          <div>
            <label style={labelStyle}>Marimea</label>
            <select value={sizeChoice} onChange={(e) => setSizeChoice(e.target.value)}
              disabled={editing} style={{ ...inputStyle, opacity: editing ? 0.6 : 1 }}>
              <option value={ALL_SIZES}>Toate marimile</option>
              {sizes.map((s) => <option key={s} value={s}>{`Marimea ${s}`}</option>)}
              <option value={CUSTOM_SIZE}>Alta marime…</option>
            </select>
            {sizeChoice === CUSTOM_SIZE && (
              <input type="text" value={customSize} onChange={(e) => setCustomSize(e.target.value)}
                placeholder="ex: 42 2/3 EU" disabled={editing}
                style={{ ...inputStyle, marginTop: "0.375rem" }} />
            )}
          </div>

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Pret de referinta</label>
              <input type="number" step="0.01" min="0" value={price}
                onChange={(e) => setPrice(e.target.value)} onBlur={refreshNet}
                placeholder="ex: 200" style={inputStyle} />
            </div>
            <div style={{ width: "110px" }}>
              <label style={labelStyle}>Moneda</label>
              <select value={currency} onChange={(e) => setCurrency(e.target.value)} style={inputStyle}>
                {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label style={labelStyle}>Link (optional)</label>
            <input type="text" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://..." style={inputStyle} />
          </div>

          <div style={{
            background: "rgba(4,9,18,.45)", borderRadius: "10px", padding: "0.75rem",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
          }}>
            <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
              Ramane net, dupa taxele platformei
            </span>
            <strong style={{ fontSize: "1.0625rem", color: net ? "#4ade80" : "var(--text-muted)" }}>
              {net ? `${net.net} ${net.net_currency}` : "—"}
            </strong>
          </div>

          {error && <p style={{ fontSize: "0.8125rem", color: "#f87171", margin: 0 }}>{error}</p>}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1.5rem" }}>
          <button type="button" onClick={onClose} style={secondaryBtn}>Anuleaza</button>
          <button type="button" onClick={save} disabled={saving || !platform}
            style={{ ...primaryBtn, opacity: saving || !platform ? 0.6 : 1 }}>
            {saving ? "Se salveaza..." : "Salveaza"}
          </button>
        </div>
      </div>
    </div>
  );
}
