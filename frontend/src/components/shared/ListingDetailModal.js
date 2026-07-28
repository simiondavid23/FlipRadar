"use client";
// Modal de detaliu partajat (Radar + Auto). Extras 1:1 din radar/page.js::ListingModal.
// Structura comuna (antet, galerie, bloc PREȚ/marjă/scor, vânzător/date, Descriere, Review AI,
// Mesaje rapide, acțiuni) traieste aici; bucatile specifice modulului vin prin props:
//   detailBannerSlot / mlSlot — ReactNode-uri opt-in (Radar: Vinted/FB detail + ML)
//   showReview / showTemplates / onBlockSeller — opt-in
//   children — slot ADIȚIONAL la finalul modalului (Auto pune Import Score aici)
// Culorile/insignele/eticheta "Deschide" vin ca props (nu hardcodat Radar).
import { useState, useEffect } from "react";
import {
  X, ImageOff, Tag, MapPin, Calendar, Sparkles,
  Bookmark, EyeOff, ExternalLink, MessageSquare, Copy, Check,
} from "lucide-react";
import { marginColor, formatListedDate, timeAgo, sellerRatingLabel, memberSinceLabel } from "./listingHelpers";
import { modalOverlayStyle, modalPanelStyle } from "@/lib/uiStyles";

// Eticheta mono de deasupra fiecarei valori din coloana de detalii.
const fieldLabel = {
  fontFamily: "var(--font-mono)",
  fontSize: "8.5px",
  letterSpacing: ".15em",
  textTransform: "uppercase",
  color: "var(--text-mono)",
  marginBottom: "3px",
};

export default function ListingDetailModal({
  listing,
  images = [],
  scoreCfg,
  scoreBadge,
  scoreExplanation,
  platformCfg,
  platformBadge,
  platformUpper,
  openLabel,
  priceNode = null,
  specsNode = null,
  onClose,
  onSave,
  onIgnore,
  showReview = false,
  reviewEnabled = true,
  onGenerateAI,
  generatingAI,
  reviewSettingsHref = "/dashboard/settings",
  showTemplates = false,
  templates = [],
  onRenderTemplate,
  templatesHref = "/dashboard/settings",
  detailBannerSlot = null,
  mlSlot = null,
  children = null,
}) {
  // selectedImg ține DOAR imaginea aleasă de user din thumbnails; imaginea afișată
  // e derivată în render. Când se schimbă listing-ul SAU enrichment-ul aduce alte
  // poze (același id, `images` se schimbă), selecția veche nu mai e în `images` și
  // se cade automat pe prima imagine — fără efect, deci fără set-state-in-effect.
  const [selectedImg, setSelectedImg] = useState(null);
  // Fallback: cand galeria (enrichment) e goala, cade pe thumbnail-ul cardului. Auto expune
  // `image_url` (coloana din _d); Radar nu are camp separat (foloseste `images`) -> undefined,
  // deci fallback-ul e no-op pe Radar — fara regresie, se activeaza doar cand galeria e goala.
  const mainImg = (selectedImg && images.includes(selectedImg))
    ? selectedImg
    : (images[0] || listing?.image_url || null);

  return (
    <div onClick={onClose} style={modalOverlayStyle}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ ...modalPanelStyle, maxWidth: "900px", display: "flex", flexDirection: "column" }}
      >
        {/* Antet modal */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 18px", borderBottom: "1px solid rgba(94,140,255,.1)",
          gap: "10px",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flex: 1, minWidth: 0 }}>
            {scoreBadge && (
              <span style={{
                padding: "2px 9px",
                background: scoreCfg.bg,
                border: `1px solid ${scoreCfg.border}`,
                borderRadius: "7px",
                color: scoreCfg.text,
                fontFamily: "var(--font-mono)",
                fontSize: "11px",
                fontWeight: 700,
              }}>{scoreBadge}</span>
            )}
            <span style={{
              padding: "2.5px 7px",
              background: platformCfg.bg,
              border: `1px solid ${platformCfg.border}`,
              borderRadius: "7px",
              color: platformCfg.text,
              fontFamily: "var(--font-mono)",
              fontSize: "8.5px",
              letterSpacing: ".08em",
              textTransform: "uppercase",
            }}>{platformBadge}</span>
            <h2 style={{
              fontSize: "15px", fontWeight: 600, color: "var(--text-primary)",
              margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>{listing.title}</h2>
          </div>
          <button onClick={onClose} className="btn-icon" aria-label="Închide">
            <X style={{ width: "15px", height: "15px" }} strokeWidth={1.8} />
          </button>
        </div>

        {/* Corp modal */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
          gap: "1.25rem",
          padding: "1.25rem",
        }}>
          {/* Stânga: galerie imagini */}
          <div>
            <div style={{
              width: "100%", aspectRatio: "1",
              background: "repeating-linear-gradient(45deg, rgba(94,140,255,.055) 0 12px, rgba(94,140,255,.015) 12px 24px)",
              borderRadius: "12px",
              overflow: "hidden",
              display: "flex", alignItems: "center", justifyContent: "center",
              border: "1px solid rgba(94,140,255,.13)",
            }}>
              {mainImg ? (
                <img src={mainImg} alt={listing.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <ImageOff style={{ width: "36px", height: "36px", color: "var(--text-mono)" }} strokeWidth={1.6} />
              )}
            </div>
            {images.length > 1 && (
              <div style={{ display: "flex", gap: "8px", marginTop: "8px", flexWrap: "wrap" }}>
                {images.slice(0, 6).map((img, idx) => (
                  <img
                    key={idx}
                    src={img}
                    alt=""
                    onClick={() => setSelectedImg(img)}
                    style={{
                      width: "64px", height: "64px", objectFit: "cover",
                      borderRadius: "9px", cursor: "pointer",
                      border: mainImg === img ? "1.5px solid rgba(34,211,238,.6)" : "1px solid rgba(94,140,255,.13)",
                      boxShadow: mainImg === img ? "0 0 14px rgba(34,211,238,.2)" : "none",
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Dreapta: detalii */}
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <div>
              <div style={fieldLabel}>Preț cerut</div>
              <div style={{ fontSize: "24px", fontWeight: 700, letterSpacing: "-.5px", color: "#ffffff" }}>
                {priceNode || <>{Math.round(listing.price)} <span style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-tertiary)" }}>{listing.currency}</span></>}
              </div>
            </div>

            {/* Slot opțional specificații (ex. an/km/combustibil/cutie la Auto). Radar nu-l pasează. */}
            {specsNode}

            {listing.resale_price && (
              <div>
                <div style={fieldLabel}>Preț estimat revânzare</div>
                <div style={{ fontSize: "17px", fontWeight: 600, color: "var(--text-primary)" }}>
                  {Math.round(listing.resale_price)} RON
                </div>
              </div>
            )}

            {listing.margin_pct !== null && listing.margin_pct !== undefined && (
              <div>
                <div style={fieldLabel}>Marjă</div>
                <div style={{ fontSize: "15px", fontWeight: 600, color: marginColor(listing.margin_pct) }}>
                  {Math.round(listing.margin_value || 0)} RON ({Math.round(listing.margin_pct)}%)
                </div>
              </div>
            )}

            {listing.fee_ceiling !== null && listing.fee_ceiling !== undefined && (
              <div>
                <div style={fieldLabel}>Preț maxim recomandat</div>
                <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>
                  {Math.round(listing.fee_ceiling)} RON
                </div>
              </div>
            )}

            {scoreBadge && (
              <div style={{ padding: "10px 12px", background: scoreCfg.bg, border: `1px solid ${scoreCfg.border}`, borderRadius: "12px" }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".14em", fontWeight: 700, color: scoreCfg.text, textTransform: "uppercase" }}>Scor {scoreBadge}</div>
                <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "3px" }}>{scoreExplanation}</div>
              </div>
            )}

            <div style={{ fontSize: "11.5px", color: "var(--text-tertiary)", display: "flex", flexDirection: "column", gap: "4px" }}>
              <div><Tag style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} /> {platformUpper}</div>
              {listing.location && <div><MapPin style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} /> {listing.location}</div>}
              {listing.condition && <div>Condiție: {listing.condition}</div>}
              {(listing.seller_name || listing.seller_rating != null || listing.seller_risk || memberSinceLabel(listing)) && (
                <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", flexWrap: "wrap" }}>
                  {listing.seller_name && <span>Vânzător: {listing.seller_name}</span>}
                  {sellerRatingLabel(listing) && (
                    <span style={{ color: "var(--text-mono)" }}>· {sellerRatingLabel(listing)}</span>
                  )}
                  {memberSinceLabel(listing) && (
                    <span style={{ color: "var(--text-mono)" }}>· {memberSinceLabel(listing)}</span>
                  )}
                  {listing.seller_risk && (
                    <span
                      title={listing.risk_reason || "Vânzător riscant"}
                      style={{
                        padding: "1px 7px", borderRadius: "6px",
                        background: "rgba(248,113,113,.1)", color: "#f87171",
                        border: "1px solid rgba(248,113,113,.3)", fontSize: "9.5px", fontWeight: 600,
                      }}
                    >
                      ⚠ Riscant
                    </span>
                  )}
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.125rem", marginTop: "0.25rem" }}>
                <span>
                  <Calendar style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
                  <strong>Postat pe platformă:</strong>{" "}
                  {formatListedDate(listing.listed_at) || "Necunoscut"}
                </span>
                <span>
                  <Calendar style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
                  <strong>Găsit de FlipRadar:</strong>{" "}
                  {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Slot bannere detaliu on-demand (Radar: Vinted/Facebook) */}
        {detailBannerSlot}

        {/* RP-1 — Detalii articol (atribute, ex. Vinted): cheile RO cunoscute întâi. */}
        {listing.attributes && Object.keys(listing.attributes).length > 0 && (
          <div style={{ padding: "0 1.25rem 1rem" }}>
            <div style={{ fontSize: "12.5px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "8px" }}>
              Detalii articol
            </div>
            <div style={{ border: "1px solid rgba(94,140,255,.13)", borderRadius: "12px", overflow: "hidden" }}>
              {orderedAttributes(listing.attributes).map(([k, v], idx) => (
                <div key={k} style={{
                  display: "flex", justifyContent: "space-between", gap: "1rem",
                  fontSize: "12px", padding: "7px 11px",
                  background: idx % 2 ? "rgba(4,9,18,.45)" : "transparent",
                }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".12em", textTransform: "uppercase", color: "var(--text-mono)", alignSelf: "center" }}>{k}</span>
                  <span style={{ color: "var(--text-primary)", textAlign: "right" }}>{String(v)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Descriere */}
        {listing.description && (
          <div style={{ padding: "0 1.25rem 1rem" }}>
            <div style={{ fontSize: "12.5px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "6px" }}>Descriere</div>
            <div style={{ fontSize: "12.5px", color: "var(--text-secondary)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{listing.description}</div>
          </div>
        )}

        {/* Slot predicție ML (opt-in per modul) */}
        {mlSlot}

        {/* Review AI */}
        {showReview && (
          <div style={{ padding: "0 1.25rem 1.25rem" }}>
            <div style={{ fontSize: "12.5px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "6px", display: "flex", alignItems: "center", gap: "6px" }}>
              <Sparkles style={{ width: "14px", height: "14px", color: "#7ee7f8" }} strokeWidth={1.8} />
              Review AI
            </div>
            {listing.ai_review ? (
              <div style={{ fontSize: "12.5px", color: "var(--text-secondary)", fontStyle: "italic", lineHeight: 1.55, padding: "11px 13px", background: "rgba(4,9,18,.45)", border: "1px solid rgba(94,140,255,.13)", borderRadius: "12px" }}>
                {listing.ai_review}
              </div>
            ) : (
              <>
              <button
                onClick={reviewEnabled ? onGenerateAI : undefined}
                disabled={generatingAI}
                style={{
                  padding: "8px 15px",
                  background: "linear-gradient(135deg, rgba(147,51,234,.2), rgba(147,51,234,.05) 60%, transparent)",
                  color: "#c4b5fd",
                  border: "1px solid rgba(147,51,234,.4)",
                  borderRadius: "10px",
                  fontFamily: "var(--font-sans)",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: reviewEnabled ? (generatingAI ? "wait" : "pointer") : "default",
                  opacity: reviewEnabled ? 1 : 0.4,
                }}
              >
                {generatingAI ? "Se generează…" : "Generează review AI"}
              </button>
              {!reviewEnabled && (
                <p style={{ fontSize: "11.5px", color: "var(--text-tertiary)", marginTop: "6px" }}>
                  Feature dezactivat · <a href={reviewSettingsHref}>Activează din Setări</a>
                </p>
              )}
              </>
            )}
          </div>
        )}

        {/* Mesaje rapide */}
        {showTemplates && (
          <MessageTemplateBlock listing={listing} templates={templates} onRenderTemplate={onRenderTemplate} templatesHref={templatesHref} />
        )}

        {/* Acțiuni */}
        <div style={{ padding: "1rem 1.25rem", borderTop: "1px solid rgba(94,140,255,.1)", display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <button
            onClick={onSave}
            style={btn(
              "#4ade80",
              listing.status === "saved" ? "rgba(74,222,128,0.2)" : "rgba(74,222,128,0.08)",
              "rgba(74,222,128,0.32)"
            )}
          >
            <Bookmark style={{ width: "13px", height: "13px", display: "inline", marginRight: "6px" }} strokeWidth={2} />
            {listing.status === "saved" ? "Salvat" : "Salvează"}
          </button>
          <button
            onClick={onIgnore}
            style={btn(
              "var(--text-dim)",
              listing.status === "ignored" ? "rgba(148,163,184,0.18)" : "rgba(148,163,184,0.07)",
              "rgba(148,163,184,0.2)"
            )}
          >
            <EyeOff style={{ width: "13px", height: "13px", display: "inline", marginRight: "6px" }} strokeWidth={2} />
            {listing.status === "ignored" ? "Ignorat" : "Ignoră"}
          </button>
          <a
            href={listing.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-cyan"
            style={{ marginLeft: "auto" }}
          >
            <ExternalLink style={{ width: "13px", height: "13px" }} strokeWidth={2} />
            {openLabel}
          </a>
        </div>

        {/* Slot ADIȚIONAL la finalul modalului (Auto: Import Score) */}
        {children}
      </div>
    </div>
  );
}

// RP-1 — ordoneaza atributele: cheile RO cunoscute intai, apoi restul (ordinea data).
function orderedAttributes(attrs) {
  const KNOWN = ["Brand", "Model", "Sănătatea bateriei", "Capacitate de stocare", "Stare", "Blocare SIM", "Culoare"];
  const known = KNOWN.filter((k) => attrs[k] !== undefined && attrs[k] !== null).map((k) => [k, attrs[k]]);
  const rest = Object.entries(attrs).filter(([k]) => !KNOWN.includes(k) && attrs[k] !== null);
  return [...known, ...rest];
}

function btn(color, bg, border) {
  return {
    padding: "9px 16px",
    background: bg,
    color: color,
    border: `1px solid ${border}`,
    borderRadius: "12px",
    fontFamily: "var(--font-sans)",
    fontSize: "12.5px",
    fontWeight: 600,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
  };
}

// Mesaje rapide — parametrizat: onRenderTemplate(templateId, {listing_id, pret_oferit}) + templatesHref.
function MessageTemplateBlock({ listing, templates, onRenderTemplate, templatesHref }) {
  const compat = templates.filter((t) => t.platform === "all" || t.platform === listing.platform);
  const [templateId, setTemplateId] = useState(compat[0]?.id || "");
  const defaultPretOferit = Math.round(listing.fee_ceiling || listing.price * 0.9);
  const [pret, setPret] = useState(defaultPretOferit);
  const [rendered, setRendered] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (compat[0]?.id && !templateId) setTemplateId(compat[0].id);
    setPret(Math.round(listing.fee_ceiling || listing.price * 0.9));
  }, [listing.id]);

  if (templates.length === 0) {
    return (
      <div style={{ padding: "0 1.25rem 1rem" }}>
        <div style={{ fontSize: "12.5px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "6px", display: "flex", alignItems: "center", gap: "6px" }}>
          <MessageSquare style={{ width: "14px", height: "14px", color: "#7ee7f8" }} strokeWidth={1.8} />
          Mesaje rapide
        </div>
        <div style={{ fontSize: "11.5px", color: "var(--text-muted)" }}>
          Configurează șabloane în <a href={templatesHref}>Șabloane Mesaje</a>.
        </div>
      </div>
    );
  }

  const render = async () => {
    if (!templateId) return;
    setBusy(true);
    try {
      const r = await onRenderTemplate(templateId, {
        listing_id: listing.id,
        pret_oferit: parseFloat(pret) || null,
      });
      setRendered(r.data?.rendered_text || "");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la randare șablon.");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!rendered) return;
    try {
      await navigator.clipboard.writeText(rendered);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      alert("Nu am putut copia. Selectează manual textul.");
    }
  };

  const ctlStyle = {
    background: "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.08) 55%, transparent) border-box",
    border: "1px solid transparent",
    borderRadius: "10px", padding: "7px 11px",
    color: "var(--text-primary)", fontSize: "12px",
    fontFamily: "var(--font-sans)", outline: "none",
  };

  return (
    <div style={{ padding: "0 1.25rem 1rem" }}>
      <div style={{ fontSize: "12.5px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "6px", display: "flex", alignItems: "center", gap: "6px" }}>
        <MessageSquare style={{ width: "14px", height: "14px", color: "#7ee7f8" }} strokeWidth={1.8} />
        Mesaje rapide
      </div>
      <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
        <select
          value={templateId}
          onChange={(e) => setTemplateId(parseInt(e.target.value) || "")}
          style={{ ...ctlStyle, minWidth: "200px" }}
        >
          {compat.length === 0 && <option value="">Niciun șablon pentru această platformă</option>}
          {compat.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        <input
          type="number"
          value={pret}
          onChange={(e) => setPret(e.target.value)}
          style={{ ...ctlStyle, width: "120px" }}
          placeholder="Preț oferit"
        />
        <button onClick={render} disabled={busy || !templateId} className="btn-cyan" style={{ padding: "7px 14px", borderRadius: "10px", fontSize: "12px" }}>
          {busy ? "…" : "Generează"}
        </button>
      </div>
      {rendered && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <textarea
            readOnly
            value={rendered}
            rows={4}
            style={{
              width: "100%",
              background: "rgba(4,9,18,.45)", border: "1px solid rgba(94,140,255,.13)",
              borderRadius: "12px", padding: "10px 12px",
              color: "var(--text-primary)", fontSize: "12.5px",
              fontFamily: "var(--font-sans)", resize: "vertical", outline: "none",
            }}
          />
          <div style={{ display: "flex", gap: "0.375rem" }}>
            <button onClick={copy} style={{
              padding: "7px 12px",
              background: copied ? "rgba(74,222,128,.14)" : "rgba(148,163,184,.07)",
              color: copied ? "#4ade80" : "var(--text-dim)",
              border: `1px solid ${copied ? "rgba(74,222,128,.32)" : "rgba(148,163,184,.2)"}`,
              borderRadius: "10px", fontSize: "12px", fontWeight: 600,
              fontFamily: "var(--font-sans)",
              cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "5px",
            }}>
              {copied ? <Check style={{ width: "12px", height: "12px" }} strokeWidth={2} /> : <Copy style={{ width: "12px", height: "12px" }} strokeWidth={2} />}
              {copied ? "Copiat!" : "Copiază"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
