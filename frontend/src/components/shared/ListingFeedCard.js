"use client";
// Card de feed partajat (Radar + Auto). Extras 1:1 din radar/page.js::ListingCard.
// Bucatile specifice modulului vin prin props (nu hardcodat Radar):
//   scoreCfg/scoreBadge  — obiect de culori + textul insignei de scor/grad
//   platformCfg/platformBadge — obiect de culori + textul insignei de platforma
//   image                — URL-ul imaginii (fiecare modul isi alege sursa)
//   openLabel            — eticheta butonului "Deschide" (+ title)
//   showMarginLine       — arata linia "-> revanzare | Marja" (Radar: mereu; Auto: doar cu marja)
//   onToggleCompare      — daca lipseste, butonul de comparare nu apare (opt-in)
import { ImageOff, Bookmark, EyeOff, ExternalLink, Check, Trash2, Scale } from "lucide-react";
import { marginColor, formatListedDate, timeAgo, sellerRatingLabel, memberSinceLabel } from "./listingHelpers";

export default function ListingFeedCard({
  listing, scoreCfg, scoreBadge, platformCfg, platformBadge, image, openLabel,
  showMarginLine = true, imageOverlaySlot = null, priceNode = null, specsNode = null,
  onOpen, onSave, onIgnore, compareSelected, bulkSelected, isSelected,
  onToggleSelect, onToggleCompare, onToggleBulk, onDelete,
  confirmingDelete, onConfirmDelete, onCancelDelete,
}) {
  const margin = listing.margin_pct;
  const marginValue = listing.margin_value;

  const baseBorder = compareSelected ? "var(--blue-primary)" : bulkSelected ? "#94a3b8" : "var(--border-color)";

  return (
    <div
      onClick={onOpen}
      style={{
        backgroundColor: bulkSelected ? "rgba(148,163,184,0.05)" : "var(--bg-card)",
        border: `1px solid ${baseBorder}`,
        borderRadius: "0.75rem",
        overflow: "hidden",
        cursor: "pointer",
        transition: "all 0.15s ease",
        display: "flex",
        flexDirection: "column",
        position: "relative",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = scoreCfg.border;
        e.currentTarget.style.boxShadow = `0 4px 14px ${scoreCfg.bg}`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = baseBorder;
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* MODULE 2 — strip de selecție deasupra imaginii */}
      <div
        onClick={(e) => { e.stopPropagation(); onToggleSelect(); }}
        style={{
          display: "flex", alignItems: "center", gap: "0.5rem",
          padding: "0.3rem 0.625rem",
          borderBottom: "0.5px solid var(--border-color)",
          borderRadius: "0.75rem 0.75rem 0 0",
          backgroundColor: isSelected ? "rgba(37,99,235,0.08)" : "transparent",
          cursor: "pointer",
          transition: "background-color 0.12s",
          flexShrink: 0,
        }}
      >
        <div style={{
          width: "14px", height: "14px", borderRadius: "3px", flexShrink: 0,
          border: isSelected ? "2px solid #2563eb" : "1.5px solid rgba(100,116,139,0.45)",
          backgroundColor: isSelected ? "#2563eb" : "transparent",
          display: "flex", alignItems: "center", justifyContent: "center",
          transition: "all 0.1s",
        }}>
          {isSelected && <Check style={{ width: "10px", height: "10px", color: "white" }} strokeWidth={3} />}
        </div>
        <span style={{ fontSize: "0.6875rem", color: isSelected ? "#60a5fa" : "var(--text-secondary)", userSelect: "none" }}>
          {isSelected ? "Selectat" : "Selectează"}
        </span>
      </div>

      {/* Imagine */}
      <div style={{ position: "relative", height: "180px", backgroundColor: "var(--bg-dark)" }}>
        {image ? (
          <img
            src={image}
            alt={listing.title}
            loading="lazy"
            decoding="async"
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text-muted)" }}>
            <ImageOff style={{ width: "36px", height: "36px" }} />
          </div>
        )}

        {/* Insignă scor */}
        {scoreBadge && (
          <div style={{
            position: "absolute", top: "0.5rem", left: "0.5rem",
            padding: "0.25rem 0.625rem",
            backgroundColor: scoreCfg.bg,
            border: `1px solid ${scoreCfg.border}`,
            borderRadius: "0.375rem",
            color: scoreCfg.text,
            fontSize: "0.75rem",
            fontWeight: 700,
          }}>
            {scoreBadge}
          </div>
        )}

        {/* Insignă platformă */}
        <div style={{
          position: "absolute", top: "0.5rem", right: "0.5rem",
          padding: "0.25rem 0.625rem",
          backgroundColor: platformCfg.bg,
          border: `1px solid ${platformCfg.border}`,
          borderRadius: "0.375rem",
          color: platformCfg.text,
          fontSize: "0.6875rem",
          fontWeight: 600,
          textTransform: "uppercase",
        }}>
          {platformBadge}
        </div>

        {/* Slot opțional pentru overlay-uri peste imagine (ex. badge "Import" la Auto).
            Radar nu-l pasează → nimic randat → card identic. */}
        {imageOverlaySlot}
      </div>

      {/* Conținut card */}
      <div style={{ padding: "0.875rem", display: "flex", flexDirection: "column", gap: "0.5rem", flex: 1 }}>
        <h3 style={{
          fontSize: "0.875rem",
          fontWeight: 600,
          color: "var(--text-primary)",
          margin: 0,
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          textOverflow: "ellipsis",
          minHeight: "2.6em",
          lineHeight: "1.3",
        }}>
          {listing.title}
        </h3>

        <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
          {priceNode || <>{Math.round(listing.price)} {listing.currency}</>}
        </div>

        {showMarginLine && (
          <div style={{ fontSize: "0.75rem", color: marginColor(margin) }}>
            → {Math.round(listing.resale_price || 0)} RON revânzare
            {marginValue !== null && marginValue !== undefined && (
              <span> | Marjă: <strong>{Math.round(marginValue)} RON ({Math.round(margin || 0)}%)</strong></span>
            )}
          </div>
        )}

        {/* Slot opțional specificații (ex. an/km/combustibil/cutie la Auto). Radar nu-l pasează. */}
        {specsNode}

        {listing.fee_ceiling !== null && listing.fee_ceiling !== undefined && (
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
            Preț maxim recomandat: {Math.round(listing.fee_ceiling)} RON
          </div>
        )}

        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "0.125rem" }}>
          {listing.location && <span>{listing.location}</span>}
          <span>
            {listing.listed_at && formatListedDate(listing.listed_at) ? (
              <>Postat: {formatListedDate(listing.listed_at)} · Găsit: {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}</>
            ) : (
              <>Găsit: {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}</>
            )}
          </span>
        </div>

        {/* RP-1 — vânzător + rating + badge de risc (randate doar când există date). */}
        {(listing.seller_name || listing.seller_rating != null || listing.seller_risk || memberSinceLabel(listing)) && (
          <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: "0.375rem", flexWrap: "wrap" }}>
            {listing.seller_name && (
              <span style={{ maxWidth: "55%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {listing.seller_name}
              </span>
            )}
            {sellerRatingLabel(listing) && (
              <span style={{ color: "var(--text-muted)" }}>{sellerRatingLabel(listing)}</span>
            )}
            {memberSinceLabel(listing) && (
              <span style={{ color: "var(--text-muted)" }}>{memberSinceLabel(listing)}</span>
            )}
            {listing.seller_risk && (
              <span
                title={listing.risk_reason || "Vânzător riscant"}
                style={{
                  padding: "0.05rem 0.4rem", borderRadius: "0.3rem",
                  backgroundColor: "rgba(239,68,68,0.12)", color: "#f87171",
                  border: "1px solid rgba(239,68,68,0.35)", fontSize: "0.65rem", fontWeight: 600,
                }}
              >
                ⚠ Riscant
              </span>
            )}
          </div>
        )}

        {confirmingDelete ? (
          <div onClick={(e) => e.stopPropagation()} style={{
            display: "flex", alignItems: "center", gap: "0.5rem",
            marginTop: "auto",
            padding: "0.5rem 0.75rem",
            borderTop: "1px solid rgba(239,68,68,0.3)",
            backgroundColor: "rgba(239,68,68,0.05)",
          }}>
            <span style={{ fontSize: "0.75rem", color: "#fca5a5", flex: 1 }}>
              Ștergi acest anunț definitiv?
            </span>
            <button onClick={onConfirmDelete} style={{ padding: "0.25rem 0.625rem", backgroundColor: "rgba(239,68,68,0.2)", color: "#f87171", border: "1px solid rgba(239,68,68,0.4)", borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 600, cursor: "pointer" }}>
              Confirmă
            </button>
            <button onClick={onCancelDelete} style={{ padding: "0.25rem 0.625rem", backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.375rem", fontSize: "0.75rem", cursor: "pointer" }}>
              Anulează
            </button>
          </div>
        ) : (
        <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto", paddingTop: "0.5rem", alignItems: "center" }}>
          <button
            onClick={(e) => { e.stopPropagation(); onSave(); }}
            style={{
              display: "inline-flex", alignItems: "center", gap: "0.25rem",
              padding: "0.375rem 0.75rem",
              backgroundColor: listing.status === "saved" ? "rgba(22,163,74,0.2)" : "rgba(22,163,74,0.08)",
              color: "#4ade80",
              border: "1px solid rgba(22,163,74,0.35)",
              borderRadius: "0.375rem",
              fontSize: "0.75rem", fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <Bookmark style={{ width: "12px", height: "12px" }} />
            {listing.status === "saved" ? "Salvat" : "Salvează"}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onIgnore(); }}
            style={{
              display: "inline-flex", alignItems: "center", gap: "0.25rem",
              padding: "0.375rem 0.75rem",
              backgroundColor: listing.status === "ignored" ? "rgba(100,116,139,0.2)" : "rgba(100,116,139,0.08)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border-color)",
              borderRadius: "0.375rem",
              fontSize: "0.75rem", fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <EyeOff style={{ width: "12px", height: "12px" }} />
            {listing.status === "ignored" ? "Ignorat" : "Ignoră"}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); window.open(listing.url, "_blank", "noopener,noreferrer"); }}
            style={{ flex: 1, padding: "0.4rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.375rem", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer" }}
            title={openLabel}
          >
            <ExternalLink style={{ width: "12px", height: "12px", display: "inline", marginRight: "0.25rem" }} />
            {openLabel}
          </button>
          {onToggleCompare && (
            <button
              onClick={(e) => { e.stopPropagation(); onToggleCompare(); }}
              title={compareSelected ? "Scoate din comparare" : "Adaugă la comparare"}
              style={{
                background: "transparent", border: "none", cursor: "pointer",
                padding: "0.25rem", borderRadius: "0.375rem",
                color: compareSelected ? "#60a5fa" : "var(--text-secondary)",
                backgroundColor: compareSelected ? "rgba(37,99,235,0.12)" : "transparent",
                display: "inline-flex", alignItems: "center",
                transition: "all 0.12s",
              }}
            >
              <Scale style={{ width: "14px", height: "14px" }} />
            </button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            title="Șterge anunțul"
            style={{
              marginLeft: "auto",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              color: "#f87171",
              display: "inline-flex",
              alignItems: "center",
              padding: "0.25rem",
              borderRadius: "0.375rem",
            }}
          >
            <Trash2 style={{ width: "14px", height: "14px" }} />
          </button>
        </div>
        )}
      </div>
    </div>
  );
}
