"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { alertsAPI, productsAPI, trackedProductsAPI } from "@/lib/api";

/**
 * RETAIL-4 — asistent in 3 pasi peste POST /api/products/from-url.
 * Pasul 1 previzualizeaza ce a extras backendul, pasul 2 configureaza
 * monitorizarea, pasul 3 confirma si scrie. Stilul oglindeste modalul de
 * keyword din radar/keywords (overlay fix, card centrat, Inapoi/Continua).
 */

const overlayStyle = {
  position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", zIndex: 100,
  display: "flex", alignItems: "flex-start", justifyContent: "center",
  padding: "3rem 1rem", overflowY: "auto",
};
const cardStyle = {
  width: "100%", maxWidth: "640px", backgroundColor: "var(--bg-card)",
  border: "1px solid var(--border-color)", borderRadius: "0.875rem", padding: "1.5rem",
};
const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
  fontSize: "0.875rem", outline: "none",
};
const labelStyle = {
  display: "block", fontSize: "0.75rem", fontWeight: 600,
  color: "var(--text-secondary)", marginBottom: "0.375rem",
};
const primaryBtn = {
  padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "var(--blue-primary)",
  color: "white", border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600,
};
const secondaryBtn = {
  padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "transparent",
  color: "var(--text-secondary)", border: "1px solid var(--border-color)",
  cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
};
const hintStyle = { fontSize: "0.6875rem", color: "var(--text-muted)", marginTop: "0.25rem" };

const badge = (bg, fg) => ({
  padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
  fontWeight: 500, backgroundColor: bg, color: fg,
});

/** Stoc tri-state: null/undefined inseamna NECUNOSCUT, nu "epuizat". */
function StockBadge({ inStock }) {
  if (inStock === true) return <span style={badge("rgba(34,197,94,0.15)", "#4ade80")}>In stoc</span>;
  if (inStock === false) return <span style={badge("rgba(239,68,68,0.15)", "#f87171")}>Stoc epuizat</span>;
  return <span style={badge("rgba(148,163,184,0.15)", "#cbd5e1")}>Stoc necunoscut</span>;
}

export default function AddByLinkWizard({ url, onClose }) {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);

  const [monitorActive, setMonitorActive] = useState(true);
  const [targetPrice, setTargetPrice] = useState("");
  const [dropPctPercent, setDropPctPercent] = useState("");

  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  const extract = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await productsAPI.createFromUrl(url);
      setData(res.data);
    } catch (e) {
      // Mesajele backendului sunt deja in romana si explica exact cauza.
      setError(e.response?.data?.detail || "Nu am putut prelua pagina. Incearca din nou.");
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => { extract(); }, [extract]);

  // Alerta de pret cere o tinta (target_price e obligatoriu in backend), deci
  // pragul procentual n-are unde fi atasat fara ea.
  const targetFilled = targetPrice.trim() !== "";
  const dropValue = Number(dropPctPercent);
  const dropValid = dropPctPercent.trim() === "" || (isFinite(dropValue) && dropValue >= 1 && dropValue <= 99);
  const targetValid = !targetFilled || (isFinite(Number(targetPrice)) && Number(targetPrice) > 0);
  const canContinueStep2 = targetValid && dropValid;

  const handleFinish = async () => {
    setSaving(true);
    setError("");
    try {
      const productId = data.product.id;
      // ORDINE OBLIGATORIE: toggle-ul de monitorizare INTAI. Activarea cu prag
      // face upsert peste alerta price_drop existenta si o rearmeaza (C-18), deci
      // o alerta creata inainte ar fi rescrisa. Trimitem toggle-ul FARA prag
      // tocmai ca alerta de mai jos sa fie singura care o defineste.
      if (monitorActive) {
        await trackedProductsAPI.toggleMonitoring(productId, true);
      }
      if (targetFilled) {
        await alertsAPI.createAlert({
          product_id: productId,
          target_price: Number(targetPrice),
          currency: data.product.currency,
          alert_type: "price_drop",
          ...(dropPctPercent.trim() !== "" ? { drop_pct: Number(dropPctPercent) / 100 } : {}),
        });
      }
      setDone(true);
    } catch (e) {
      setError(e.response?.data?.detail || "Nu am putut salva setarile de monitorizare.");
    } finally {
      setSaving(false);
    }
  };

  const header = (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
          {done ? "Produs adaugat" : `Adauga prin link — Pasul ${step} din 3`}
        </h2>
        <button onClick={onClose} title="Inchide"
          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}>
          <X style={{ width: "20px", height: "20px" }} />
        </button>
      </div>
      {!done && (
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
          {[1, 2, 3].map((s) => (
            <div key={s} style={{
              flex: 1, height: "4px", borderRadius: "2px",
              backgroundColor: s <= step ? "var(--blue-primary)" : "var(--border-color)",
            }} />
          ))}
        </div>
      )}
    </>
  );

  const body = () => {
    if (loading) {
      return (
        <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: 0 }}>
          Se citeste pagina produsului...
        </p>
      );
    }

    if (error && !data) {
      return (
        <div>
          <p style={{ fontSize: "0.875rem", color: "#f87171", marginTop: 0 }}>{error}</p>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", wordBreak: "break-all" }}>{url}</p>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
            <button type="button" onClick={extract} style={primaryBtn}>Incearca din nou</button>
            <button type="button" onClick={onClose} style={secondaryBtn}>Inchide</button>
          </div>
        </div>
      );
    }

    if (done) {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: 0 }}>
            <strong style={{ color: "var(--text-primary)" }}>{data.product.name}</strong> a fost salvat
            {monitorActive ? " si este monitorizat." : "."}
          </p>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <Link href={`/dashboard/products/detail?id=${data.product.id}`}
              style={{ ...primaryBtn, display: "inline-block", textDecoration: "none" }}>
              Vezi produsul
            </Link>
            <button type="button" onClick={onClose} style={secondaryBtn}>Inchide</button>
          </div>
        </div>
      );
    }

    const p = data.product;
    const extraction = data.extraction || {};

    if (step === 1) {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <div style={{ display: "flex", gap: "0.875rem" }}>
            {p.image_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={p.image_url} alt={p.name}
                style={{ width: "84px", height: "84px", objectFit: "contain", borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)" }} />
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 0.5rem" }}>
                {p.name}
              </p>
              <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap", alignItems: "center" }}>
                {/* Domeniul e sursa produsului — raspunsul from-url nu are camp separat. */}
                <span style={badge("rgba(147,51,234,0.15)", "#a78bfa")}>{p.source}</span>
                <StockBadge inStock={extraction.in_stock} />
                {data.domain_validated === false && (
                  <span style={badge("rgba(250,204,21,0.15)", "#facc15")}>
                    Domeniu nevalidat — monitorizare best-effort
                  </span>
                )}
              </div>
            </div>
          </div>

          <p style={{ fontSize: "1.375rem", fontWeight: 700, color: "#4ade80", margin: 0 }}>
            {p.current_price} {p.currency}
          </p>

          {data.is_new === false && (
            <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", margin: 0 }}>
              Produs existent — istoricul de pret e pastrat ({(data.price_history || []).length} puncte).
            </p>
          )}
        </div>
      );
    }

    if (step === 2) {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.8125rem", color: "var(--text-primary)" }}>
            <input type="checkbox" checked={monitorActive} onChange={(e) => setMonitorActive(e.target.checked)} />
            Monitorizeaza pretul
          </label>

          <div>
            <label style={labelStyle}>Tinta de pret (optional) — {p.currency}</label>
            <input type="number" min="0" step="0.01" value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
              placeholder={`ex: ${p.current_price}`} style={inputStyle} />
            {!targetValid && (
              <p style={{ ...hintStyle, color: "#facc15" }}>Tinta trebuie sa fie un numar mai mare decat 0.</p>
            )}
          </div>

          <div>
            <label style={{ ...labelStyle, opacity: targetFilled ? 1 : 0.5 }}>
              Alerta la scadere brusca % (optional)
            </label>
            <input type="number" min="1" max="99" step="1" value={dropPctPercent}
              onChange={(e) => setDropPctPercent(e.target.value)}
              disabled={!targetFilled} placeholder="ex: 15"
              style={{ ...inputStyle, opacity: targetFilled ? 1 : 0.5, cursor: targetFilled ? "text" : "not-allowed" }} />
            <p style={hintStyle}>
              {targetFilled
                ? "Intre 1 si 99. Se declanseaza la o scadere mai mare decat pragul, chiar daca tinta nu e atinsa."
                : "Completeaza intai tinta de pret — alerta se creeaza pe ea."}
            </p>
            {!dropValid && (
              <p style={{ ...hintStyle, color: "#facc15" }}>Pragul trebuie sa fie intre 1 si 99.</p>
            )}
          </div>
        </div>
      );
    }

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
        <p style={{ margin: 0 }}>
          Produs: <strong style={{ color: "var(--text-primary)" }}>{p.name}</strong>
        </p>
        <p style={{ margin: 0 }}>
          Monitorizare: <strong style={{ color: "var(--text-primary)" }}>{monitorActive ? "da" : "nu"}</strong>
        </p>
        <p style={{ margin: 0 }}>
          Tinta de pret: <strong style={{ color: "var(--text-primary)" }}>
            {targetFilled ? `${Number(targetPrice)} ${p.currency}` : "fara"}
          </strong>
        </p>
        <p style={{ margin: 0 }}>
          Alerta la scadere brusca: <strong style={{ color: "var(--text-primary)" }}>
            {targetFilled && dropPctPercent.trim() !== "" ? `${Number(dropPctPercent)}%` : "fara"}
          </strong>
        </p>
        {error && <p style={{ margin: "0.5rem 0 0", color: "#f87171" }}>{error}</p>}
      </div>
    );
  };

  const showFooter = !loading && !done && !(error && !data);

  return (
    <div onClick={onClose} style={overlayStyle}>
      <div onClick={(e) => e.stopPropagation()} style={cardStyle}>
        {header}
        {body()}
        {showFooter && (
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1.5rem" }}>
            <button type="button" onClick={() => (step > 1 ? setStep(step - 1) : onClose())} style={secondaryBtn}>
              {step > 1 ? "Inapoi" : "Anuleaza"}
            </button>
            {step < 3 ? (
              <button type="button"
                disabled={step === 2 && !canContinueStep2}
                onClick={() => (step === 2 && !canContinueStep2 ? null : setStep(step + 1))}
                style={{
                  ...primaryBtn,
                  opacity: step === 2 && !canContinueStep2 ? 0.5 : 1,
                  cursor: step === 2 && !canContinueStep2 ? "not-allowed" : "pointer",
                }}>
                Continua
              </button>
            ) : (
              <button type="button" onClick={handleFinish} disabled={saving}
                style={{ ...primaryBtn, opacity: saving ? 0.7 : 1 }}>
                {saving ? "Se salveaza..." : "Finalizeaza"}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
