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
import { marginColor, formatListedDate, timeAgo, sellerRatingLabel } from "./listingHelpers";

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
  const mainImg = (selectedImg && images.includes(selectedImg)) ? selectedImg : (images[0] || null);

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
          maxWidth: "900px",
          width: "100%",
          maxHeight: "90vh",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Antet modal */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "1rem 1.25rem", borderBottom: "1px solid var(--border-color)",
          gap: "0.75rem",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flex: 1, minWidth: 0 }}>
            {scoreBadge && (
              <span style={{
                padding: "0.25rem 0.625rem",
                backgroundColor: scoreCfg.bg,
                border: `1px solid ${scoreCfg.border}`,
                borderRadius: "0.375rem",
                color: scoreCfg.text,
                fontSize: "0.75rem",
                fontWeight: 700,
              }}>{scoreBadge}</span>
            )}
            <span style={{
              padding: "0.2rem 0.5rem",
              backgroundColor: platformCfg.bg,
              border: `1px solid ${platformCfg.border}`,
              borderRadius: "0.375rem",
              color: platformCfg.text,
              fontSize: "0.7rem",
              fontWeight: 600,
              textTransform: "uppercase",
            }}>{platformBadge}</span>
            <h2 style={{
              fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)",
              margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>{listing.title}</h2>
          </div>
          <button
            onClick={onClose}
            style={{
              backgroundColor: "transparent", border: "none", color: "var(--text-secondary)",
              cursor: "pointer", padding: "0.25rem",
            }}
          >
            <X style={{ width: "20px", height: "20px" }} />
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
              backgroundColor: "var(--bg-dark)",
              borderRadius: "0.625rem",
              overflow: "hidden",
              display: "flex", alignItems: "center", justifyContent: "center",
              border: "1px solid var(--border-color)",
            }}>
              {mainImg ? (
                <img src={mainImg} alt={listing.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <ImageOff style={{ width: "48px", height: "48px", color: "var(--text-muted)" }} />
              )}
            </div>
            {images.length > 1 && (
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
                {images.slice(0, 6).map((img, idx) => (
                  <img
                    key={idx}
                    src={img}
                    alt=""
                    onClick={() => setSelectedImg(img)}
                    style={{
                      width: "64px", height: "64px", objectFit: "cover",
                      borderRadius: "0.375rem", cursor: "pointer",
                      border: mainImg === img ? "2px solid var(--blue-primary)" : "1px solid var(--border-color)",
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Dreapta: detalii */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
            <div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Preț cerut</div>
              <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>
                {priceNode || <>{Math.round(listing.price)} {listing.currency}</>}
              </div>
            </div>

            {/* Slot opțional specificații (ex. an/km/combustibil/cutie la Auto). Radar nu-l pasează. */}
            {specsNode}

            {listing.resale_price && (
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Preț estimat revânzare</div>
                <div style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  {Math.round(listing.resale_price)} RON
                </div>
              </div>
            )}

            {listing.margin_pct !== null && listing.margin_pct !== undefined && (
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Marjă</div>
                <div style={{ fontSize: "1rem", fontWeight: 600, color: marginColor(listing.margin_pct) }}>
                  {Math.round(listing.margin_value || 0)} RON ({Math.round(listing.margin_pct)}%)
                </div>
              </div>
            )}

            {listing.fee_ceiling !== null && listing.fee_ceiling !== undefined && (
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Preț maxim recomandat</div>
                <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  {Math.round(listing.fee_ceiling)} RON
                </div>
              </div>
            )}

            {scoreBadge && (
              <div style={{ padding: "0.625rem", backgroundColor: scoreCfg.bg, border: `1px solid ${scoreCfg.border}`, borderRadius: "0.5rem" }}>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, color: scoreCfg.text }}>Scor {scoreBadge}</div>
                <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{scoreExplanation}</div>
              </div>
            )}

            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              <div><Tag style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} /> {platformUpper}</div>
              {listing.location && <div><MapPin style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} /> {listing.location}</div>}
              {listing.condition && <div>Condiție: {listing.condition}</div>}
              {(listing.seller_name || listing.seller_rating != null || listing.seller_risk) && (
                <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", flexWrap: "wrap" }}>
                  {listing.seller_name && <span>Vânzător: {listing.seller_name}</span>}
                  {sellerRatingLabel(listing) && (
                    <span style={{ color: "var(--text-muted)" }}>· {sellerRatingLabel(listing)}</span>
                  )}
                  {listing.seller_risk && (
                    <span
                      title={listing.risk_reason || "Vânzător riscant"}
                      style={{
                        padding: "0.05rem 0.4rem", borderRadius: "0.3rem",
                        backgroundColor: "rgba(239,68,68,0.12)", color: "#f87171",
                        border: "1px solid rgba(239,68,68,0.35)", fontSize: "0.7rem", fontWeight: 600,
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
            <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
              Detalii articol
            </div>
            <div style={{ border: "1px solid var(--border-color)", borderRadius: "0.5rem", overflow: "hidden" }}>
              {orderedAttributes(listing.attributes).map(([k, v], idx) => (
                <div key={k} style={{
                  display: "flex", justifyContent: "space-between", gap: "1rem",
                  fontSize: "0.8125rem", padding: "0.4rem 0.625rem",
                  backgroundColor: idx % 2 ? "var(--bg-dark)" : "transparent",
                }}>
                  <span style={{ color: "var(--text-muted)" }}>{k}</span>
                  <span style={{ color: "var(--text-primary)", textAlign: "right" }}>{String(v)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Descriere */}
        {listing.description && (
          <div style={{ padding: "0 1.25rem 1rem" }}>
            <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem" }}>Descriere</div>
            <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{listing.description}</div>
          </div>
        )}

        {/* Slot predicție ML (opt-in per modul) */}
        {mlSlot}

        {/* Review AI */}
        {showReview && (
          <div style={{ padding: "0 1.25rem 1.25rem" }}>
            <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem", display: "flex", alignItems: "center", gap: "0.375rem" }}>
              <Sparkles style={{ width: "14px", height: "14px", color: "#a78bfa" }} />
              Review AI
            </div>
            {listing.ai_review ? (
              <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", fontStyle: "italic", lineHeight: 1.5, padding: "0.625rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem" }}>
                {listing.ai_review}
              </div>
            ) : (
              <>
              <button
                onClick={reviewEnabled ? onGenerateAI : undefined}
                disabled={generatingAI}
                style={{
                  padding: "0.5rem 0.875rem",
                  backgroundColor: "rgba(147,51,234,0.15)",
                  color: "#c4b5fd",
                  border: "1px solid rgba(147,51,234,0.3)",
                  borderRadius: "0.5rem",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  cursor: reviewEnabled ? (generatingAI ? "wait" : "pointer") : "default",
                  opacity: reviewEnabled ? 1 : 0.4,
                }}
              >
                {generatingAI ? "Se generează..." : "Generează review AI"}
              </button>
              {!reviewEnabled && (
                <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                  Feature dezactivat · <a href={reviewSettingsHref} style={{ color: "#60a5fa" }}>Activează din Setări</a>
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
        <div style={{ padding: "1rem 1.25rem", borderTop: "1px solid var(--border-color)", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            onClick={onSave}
            style={btn(
              "#4ade80",
              listing.status === "saved" ? "rgba(22,163,74,0.25)" : "rgba(22,163,74,0.15)",
              "rgba(22,163,74,0.3)"
            )}
          >
            <Bookmark style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem" }} />
            {listing.status === "saved" ? "Salvat" : "Salvează"}
          </button>
          <button
            onClick={onIgnore}
            style={btn(
              "var(--text-secondary)",
              listing.status === "ignored" ? "rgba(100,116,139,0.2)" : "rgba(100,116,139,0.15)",
              "var(--border-color)"
            )}
          >
            <EyeOff style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem" }} />
            {listing.status === "ignored" ? "Ignorat" : "Ignoră"}
          </button>
          <a
            href={listing.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ ...btn("white", "var(--blue-primary)", "var(--blue-primary)"), textDecoration: "none", marginLeft: "auto" }}
          >
            <ExternalLink style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem" }} />
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
    padding: "0.5rem 0.875rem",
    backgroundColor: bg,
    color: color,
    border: `1px solid ${border}`,
    borderRadius: "0.5rem",
    fontSize: "0.8125rem",
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
        <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem", display: "flex", alignItems: "center", gap: "0.375rem" }}>
          <MessageSquare style={{ width: "14px", height: "14px", color: "#60a5fa" }} />
          Mesaje rapide
        </div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
          Configurează șabloane în <a href={templatesHref} style={{ color: "var(--blue-light)" }}>Șabloane Mesaje</a>.
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
    backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
    borderRadius: "0.375rem", padding: "0.4rem 0.5rem",
    color: "var(--text-primary)", fontSize: "0.75rem", outline: "none",
  };

  return (
    <div style={{ padding: "0 1.25rem 1rem" }}>
      <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem", display: "flex", alignItems: "center", gap: "0.375rem" }}>
        <MessageSquare style={{ width: "14px", height: "14px", color: "#60a5fa" }} />
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
        <button onClick={render} disabled={busy || !templateId} style={{
          padding: "0.4rem 0.625rem",
          backgroundColor: "var(--blue-primary)", color: "white",
          border: "none", borderRadius: "0.375rem",
          fontSize: "0.75rem", fontWeight: 600,
          cursor: busy ? "wait" : "pointer", opacity: busy ? 0.7 : 1,
        }}>
          {busy ? "..." : "Generează"}
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
              backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
              borderRadius: "0.375rem", padding: "0.5rem 0.625rem",
              color: "var(--text-primary)", fontSize: "0.8125rem",
              fontFamily: "inherit", resize: "vertical",
            }}
          />
          <div style={{ display: "flex", gap: "0.375rem" }}>
            <button onClick={copy} style={{
              padding: "0.375rem 0.625rem",
              backgroundColor: copied ? "rgba(22,163,74,0.15)" : "var(--bg-dark)",
              color: copied ? "#4ade80" : "var(--text-primary)",
              border: `1px solid ${copied ? "rgba(22,163,74,0.3)" : "var(--border-color)"}`,
              borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 600,
              cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.25rem",
            }}>
              {copied ? <Check style={{ width: "12px", height: "12px" }} /> : <Copy style={{ width: "12px", height: "12px" }} />}
              {copied ? "Copiat!" : "Copiază"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
