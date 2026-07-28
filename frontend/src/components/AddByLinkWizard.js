"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { alertsAPI, productsAPI, trackedProductsAPI } from "@/lib/api";

/**
 * RETAIL-4 — asistent peste POST /api/products/from-url.
 * Pasul 1 previzualizeaza ce a extras backendul, urmatorul configureaza
 * monitorizarea, ultimul confirma si scrie. Stilul oglindeste modalul de
 * keyword din radar/keywords (overlay fix, card centrat, Inapoi/Continua).
 *
 * FASHION-1d — doua schimbari:
 *  - previzualizarea trece prin /extract-url (READ-ONLY). Pana acum wizardul
 *    crea produsul la deschidere, doar ca sa aiba ce afisa; cu marimi asta ar
 *    fi lasat randuri agregate parazite la fiecare link deschis si abandonat.
 *    Acum nimic nu se scrie pana la Finalizeaza, deci Anuleaza chiar anuleaza.
 *  - cand pagina publica marimi apare un pas in plus, "Alege marimea", si
 *    numarul de pasi devine 4 in loc de 3.
 */

const overlayStyle = {
  position: "fixed", inset: 0, background: "rgba(2,5,12,0.72)", backdropFilter: "blur(6px)", zIndex: 100,
  display: "flex", alignItems: "flex-start", justifyContent: "center",
  padding: "3rem 1rem", overflowY: "auto",
};
const cardStyle = {
  width: "100%", maxWidth: "640px", background: "var(--bg-card)", backdropFilter: "blur(20px)",
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

/** Domeniul pentru badge: preview-ul e read-only si nu intoarce sursa salvata. */
function hostOf(u) {
  try {
    return new URL(u).hostname.replace(/^www\./, "");
  } catch {
    return u;
  }
}

const chipStyle = (selected) => ({
  display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "0.125rem",
  padding: "0.5rem 0.75rem", borderRadius: "10px", cursor: "pointer", textAlign: "left",
  backgroundColor: selected ? "rgba(59,130,246,0.15)" : "var(--bg-dark)",
  border: `1px solid ${selected ? "var(--blue-primary)" : "var(--border-color)"}`,
  color: "var(--text-primary)", fontSize: "0.8125rem", fontWeight: 600,
});

export default function AddByLinkWizard({ url, onClose }) {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);
  const [created, setCreated] = useState(null);

  const [selectedVariant, setSelectedVariant] = useState(null);
  const [monitorActive, setMonitorActive] = useState(true);
  const [targetPrice, setTargetPrice] = useState("");
  const [dropPctPercent, setDropPctPercent] = useState("");

  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  const extract = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await productsAPI.extractFromUrl(url);
      setData(res.data);
    } catch (e) {
      // Mesajele backendului sunt deja in romana si explica exact cauza.
      setError(e.response?.data?.detail || "Nu am putut prelua pagina. Incearca din nou.");
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => { extract(); }, [extract]);

  // Pasul de marime exista doar cand pagina publica oferte per marime.
  const variants = Array.isArray(data?.variants) ? data.variants : [];
  const hasVariants = variants.length > 0;
  const totalSteps = hasVariants ? 4 : 3;
  const variantStep = hasVariants ? 2 : 0;   // 0 = pas inexistent
  const monitorStep = hasVariants ? 3 : 2;

  // Cu o marime aleasa, pretul relevant e al ei, nu agregatul "de la" al paginii.
  const chosen = selectedVariant ? variants.find((v) => v.variant === selectedVariant) : null;
  const shownPrice = chosen ? chosen.price : data?.price;

  // Alerta de pret cere o tinta (target_price e obligatoriu in backend), deci
  // pragul procentual n-are unde fi atasat fara ea.
  const targetFilled = targetPrice.trim() !== "";
  const dropValue = Number(dropPctPercent);
  const dropValid = dropPctPercent.trim() === "" || (isFinite(dropValue) && dropValue >= 1 && dropValue <= 99);
  const targetValid = !targetFilled || (isFinite(Number(targetPrice)) && Number(targetPrice) > 0);
  const canContinueMonitor = targetValid && dropValid;
  const canContinue =
    step === variantStep ? selectedVariant !== null
      : step === monitorStep ? canContinueMonitor
        : true;

  const handleFinish = async () => {
    setSaving(true);
    setError("");
    try {
      // FASHION-1d — produsul se creeaza ABIA acum (pana la 1d se crea la
      // deschiderea wizardului). selectedVariant "" = toate marimile, deci
      // randul agregat fara varianta; `undefined` il omite din payload.
      const res = await productsAPI.createFromUrl(url, selectedVariant || undefined);
      const saved = res.data;
      setCreated(saved);
      const productId = saved.product.id;
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
          currency: saved.product.currency,
          alert_type: "price_drop",
          ...(dropPctPercent.trim() !== "" ? { drop_pct: Number(dropPctPercent) / 100 } : {}),
        });
      }
      setDone(true);
    } catch (e) {
      setError(e.response?.data?.detail || "Nu am putut salva produsul.");
    } finally {
      setSaving(false);
    }
  };

  const header = (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
          {done ? "Produs adaugat" : `Adauga prin link — Pasul ${step} din ${totalSteps}`}
        </h2>
        <button onClick={onClose} title="Inchide"
          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}>
          <X style={{ width: "20px", height: "20px" }} />
        </button>
      </div>
      {!done && (
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
          {Array.from({ length: totalSteps }, (_, i) => i + 1).map((s) => (
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
            <strong style={{ color: "var(--text-primary)" }}>{data.name}</strong>
            {selectedVariant ? ` (marimea ${selectedVariant})` : ""} a fost salvat
            {monitorActive ? " si este monitorizat." : "."}
          </p>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <Link href={`/dashboard/products/detail?id=${created.product.id}`}
              style={{ ...primaryBtn, display: "inline-block", textDecoration: "none" }}>
              Vezi produsul
            </Link>
            <button type="button" onClick={onClose} style={secondaryBtn}>Inchide</button>
          </div>
        </div>
      );
    }

    if (step === 1) {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <div style={{ display: "flex", gap: "0.875rem" }}>
            {data.image_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={data.image_url} alt={data.name}
                style={{ width: "84px", height: "84px", objectFit: "contain", borderRadius: "10px", background: "rgba(4,9,18,.45)" }} />
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 0.5rem" }}>
                {data.name}
              </p>
              <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap", alignItems: "center" }}>
                {/* Previzualizarea nu salveaza nimic, deci sursa se citeste din link. */}
                <span style={badge("rgba(147,51,234,0.15)", "#a78bfa")}>{hostOf(url)}</span>
                <StockBadge inStock={data.in_stock} />
                {data.domain_validated === false && (
                  <span style={badge("rgba(250,204,21,0.15)", "#fde047")}>
                    Domeniu nevalidat — monitorizare best-effort
                  </span>
                )}
              </div>
            </div>
          </div>

          <p style={{ fontSize: "1.375rem", fontWeight: 700, color: "#4ade80", margin: 0 }}>
            {data.price} {data.currency}
          </p>

          {data.is_aggregate && (
            <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", margin: 0 }}>
              Pret &quot;de la&quot; — pagina are mai multe oferte
              {hasVariants ? `, pe ${variants.length} marimi.` : "."}
            </p>
          )}
        </div>
      );
    }

    if (step === variantStep) {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>
            Alege marimea pe care vrei sa o urmaresti. Pretul si stocul vor fi citite
            pentru ea, nu pentru produs in general.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {/* TOATE marimile sunt selectabile, inclusiv cele epuizate: a urmari o
                marime epuizata ca sa afli cand revine e exact cazul de restock. */}
            {variants.map((v) => (
              <button key={v.variant} type="button"
                onClick={() => setSelectedVariant(v.variant)}
                style={chipStyle(selectedVariant === v.variant)}>
                <span>{v.variant}</span>
                <span style={{
                  display: "flex", alignItems: "center", gap: "0.3125rem",
                  fontSize: "0.6875rem", fontWeight: 500, color: "var(--text-secondary)",
                }}>
                  {v.price} {data.currency}
                  {v.in_stock === true && (
                    <span style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: "#4ade80" }}
                      title="In stoc" />
                  )}
                  {v.in_stock === false && <span style={{ color: "#f87171" }}>Epuizat</span>}
                </span>
              </button>
            ))}
            <button type="button" onClick={() => setSelectedVariant("")}
              style={chipStyle(selectedVariant === "")}>
              <span>Toate marimile</span>
              <span style={{ fontSize: "0.6875rem", fontWeight: 500, color: "var(--text-secondary)" }}>
                pret minim
              </span>
            </button>
          </div>
        </div>
      );
    }

    if (step === monitorStep) {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.8125rem", color: "var(--text-primary)" }}>
            <input type="checkbox" checked={monitorActive} onChange={(e) => setMonitorActive(e.target.checked)} />
            Monitorizeaza pretul
          </label>

          <div>
            <label style={labelStyle}>Tinta de pret (optional) — {data.currency}</label>
            <input type="number" min="0" step="0.01" value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
              placeholder={`ex: ${shownPrice}`} style={inputStyle} />
            {!targetValid && (
              <p style={{ ...hintStyle, color: "#fde047" }}>Tinta trebuie sa fie un numar mai mare decat 0.</p>
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
              <p style={{ ...hintStyle, color: "#fde047" }}>Pragul trebuie sa fie intre 1 si 99.</p>
            )}
          </div>
        </div>
      );
    }

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
        <p style={{ margin: 0 }}>
          Produs: <strong style={{ color: "var(--text-primary)" }}>{data.name}</strong>
        </p>
        {hasVariants && (
          <p style={{ margin: 0 }}>
            Marime: <strong style={{ color: "var(--text-primary)" }}>
              {selectedVariant ? selectedVariant : "toate (pret minim)"}
            </strong>
          </p>
        )}
        <p style={{ margin: 0 }}>
          Monitorizare: <strong style={{ color: "var(--text-primary)" }}>{monitorActive ? "da" : "nu"}</strong>
        </p>
        <p style={{ margin: 0 }}>
          Tinta de pret: <strong style={{ color: "var(--text-primary)" }}>
            {targetFilled ? `${Number(targetPrice)} ${data.currency}` : "fara"}
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
            {step < totalSteps ? (
              <button type="button"
                disabled={!canContinue}
                onClick={() => (canContinue ? setStep(step + 1) : null)}
                style={{
                  ...primaryBtn,
                  opacity: canContinue ? 1 : 0.5,
                  cursor: canContinue ? "pointer" : "not-allowed",
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
