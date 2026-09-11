"use client";
// Card de feed partajat (Radar + Auto + Imobiliare).
// Bucatile specifice modulului vin prin props (nu hardcodat Radar):
//   scoreCfg/scoreBadge  — obiect de culori + textul insignei de scor/grad
//   platformCfg/platformBadge — obiect de culori + textul insignei de platforma
//   image                — URL-ul imaginii (fiecare modul isi alege sursa)
//   openLabel            — eticheta butonului "Deschide" (+ title)
//   showMarginLine       — arata linia "-> revanzare | Marja" (Radar: mereu; Auto: doar cu marja)
//   onToggleCompare      — daca lipseste, butonul de comparare nu apare (opt-in)
import { useState } from "react";
import { ImageOff, Bookmark, EyeOff, ExternalLink, Check, Trash2, Scale, RefreshCw } from "lucide-react";
import IconButton from "@/components/IconButton";
import { marginColor, formatListedDate, timeAgo, sellerRatingLabel, memberSinceLabel, PretScazutBadge, bumpInfo } from "./listingHelpers";

// FRONT-1 — culoarea de avertizare discreta pentru anunturile repromovate. Aceeasi
// valoare in card si in modal; `uiStyles.js` nu are (inca) un token de warning.
const BUMP_COLOR = "#f59e0b";
const CARD_BORDER = "rgba(94,140,255,.13)";

export default function ListingFeedCard({
  listing, scoreCfg, scoreBadge, platformCfg, platformBadge, image, openLabel,
  showMarginLine = true, imageOverlaySlot = null, priceNode = null, specsNode = null,
  // SHOP-2b — doua props ADITIVE, folosite deocamdata doar de feed-ul de deal-uri:
  //   hideActions   — randeaza DOAR butonul de deschidere (deal-urile incheiate nu
  //                   mai pot fi promovate sau ignorate, deci butoanele ar minti).
  //   onOpenExternal— hook pe butonul de deschidere, care isi face singur
  //                   window.open si opreste propagarea, deci nu ajunge la onOpen.
  // Ambele sunt optionale: paginile care nu le paseaza raman identice.
  hideActions = false, onOpenExternal = null,
  onOpen, onSave, onIgnore, compareSelected, bulkSelected, isSelected,
  onToggleSelect, onToggleCompare, onToggleBulk, onDelete,
  confirmingDelete, onConfirmDelete, onCancelDelete,
}) {
  // IMG-1b — o poza care nu se incarca (link mort, hotlink blocat) lasa acum
  // placeholderul "FARA FOTO", nu un dreptunghi gol: `display:none` pe <img> ascundea
  // imaginea, dar rama ramanea goala, fara sa spuna nimic.
  //
  // Retinem URL-ul care a esuat, nu un boolean: asa resetarea la schimbarea lui
  // `image` e DERIVATA (`imgEsuat !== image`), nu facuta dintr-un efect. Un
  // `useEffect(() => setImgEroare(false), [image])` ar fi facut acelasi lucru, dar
  // e respins de `react-hooks/set-state-in-effect` — pe buna dreptate: ar fi
  // declansat o a doua randare la fiecare card reciclat de React.
  const [imgEsuat, setImgEsuat] = useState(null);

  const margin = listing.margin_pct;
  const marginValue = listing.margin_value;

  const baseBorder = compareSelected
    ? "rgba(96,165,250,.55)"
    : bulkSelected
      ? "rgba(148,163,184,.4)"
      : CARD_BORDER;

  // UI-1 — primul rand de actiuni exista doar daca are ce tine. Pe un deal incheiat
  // (`hideActions`, fara comparare si fara stergere) ar fi ramas un rand gol care
  // ar fi impins butonul de deschidere in jos cu un gap in plus.
  const randUnuAreContinut = (!hideActions && (onSave || onIgnore))
    || Boolean(onToggleCompare) || Boolean(onDelete);

  return (
    <div
      onClick={onOpen}
      className="listing-card"
      style={{
        borderRadius: "16px",
        background: bulkSelected ? "rgba(148,163,184,.05)" : "rgba(8,14,27,.6)",
        backdropFilter: "blur(20px)",
        "--card-border": baseBorder,
        overflow: "hidden",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        position: "relative",
      }}
    >
      {/* Strip de selecție deasupra imaginii */}
      <div
        onClick={(e) => { e.stopPropagation(); onToggleSelect(); }}
        style={{
          display: "flex", alignItems: "center", gap: "8px",
          padding: "6px 12px",
          borderBottom: "1px solid rgba(94,140,255,.09)",
          background: isSelected ? "rgba(34,211,238,.07)" : "transparent",
          cursor: "pointer",
          transition: "background-color 0.12s",
          flexShrink: 0,
        }}
      >
        <div style={{
          width: "13px", height: "13px", borderRadius: "4px", flexShrink: 0,
          border: isSelected ? "1.5px solid #22d3ee" : "1.5px solid rgba(94,140,255,.35)",
          background: isSelected ? "rgba(34,211,238,.9)" : "transparent",
          display: "flex", alignItems: "center", justifyContent: "center",
          transition: "all 0.1s",
        }}>
          {isSelected && <Check style={{ width: "9px", height: "9px", color: "#04070e" }} strokeWidth={3.5} />}
        </div>
        <span
          style={{
            fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".12em",
            textTransform: "uppercase", color: isSelected ? "#7ee7f8" : "var(--text-mono)", userSelect: "none",
          }}
        >
          {isSelected ? "Selectat" : "Selectează"}
        </span>
        {listing.id != null && (
          <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: "8px", color: "var(--text-faint)" }}>
            #{listing.id}
          </span>
        )}
      </div>

      {/* Imagine */}
      <div
        style={{
          position: "relative", height: "168px",
          background: "repeating-linear-gradient(45deg, rgba(94,140,255,.055) 0 12px, rgba(94,140,255,.015) 12px 24px)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        {image && imgEsuat !== image ? (
          <img
            src={image}
            alt={listing.title}
            loading="lazy"
            decoding="async"
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={() => setImgEsuat(image)}
          />
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-mono)" }}>
            <ImageOff style={{ width: "16px", height: "16px" }} strokeWidth={1.6} />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".18em" }}>FĂRĂ FOTO</span>
          </div>
        )}

        {/* Insignă scor */}
        {scoreBadge && (
          <div style={{
            position: "absolute", top: "9px", left: "9px",
            padding: "3px 9px",
            background: scoreCfg.bg,
            border: `1px solid ${scoreCfg.border}`,
            borderRadius: "7px",
            color: scoreCfg.text,
            fontSize: "12px",
            fontWeight: 700,
            backdropFilter: "blur(8px)",
          }}>
            {scoreBadge}
          </div>
        )}

        {/* Insignă platformă */}
        <div style={{
          position: "absolute", top: "9px", right: "9px",
          padding: "3px 8px",
          background: platformCfg.bg,
          border: `1px solid ${platformCfg.border}`,
          borderRadius: "7px",
          color: platformCfg.text,
          fontFamily: "var(--font-mono)",
          fontSize: "8.5px",
          letterSpacing: ".08em",
          textTransform: "uppercase",
          backdropFilter: "blur(8px)",
        }}>
          {platformBadge}
        </div>

        {/* Slot opțional pentru overlay-uri peste imagine (ex. badge "Import" la Auto).
            Radar nu-l pasează → nimic randat → card identic. */}
        {imageOverlaySlot}
      </div>

      {/* Conținut card */}
      <div style={{ padding: "13px 14px", display: "flex", flexDirection: "column", gap: "7px", flex: 1 }}>
        <h3 style={{
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--text-primary)",
          margin: 0,
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          textOverflow: "ellipsis",
          minHeight: "2.7em",
          lineHeight: "1.35",
        }}>
          {listing.title}
        </h3>

        {/* Prețul pe cardurile de anunțuri este alb pur — nu gradient. */}
        <div style={{ display: "flex", alignItems: "baseline", gap: "5px", flexWrap: "wrap" }}>
          {priceNode || (
            <>
              <span style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "-.4px", color: "#ffffff" }}>
                {Math.round(listing.price)}
              </span>
              <span style={{ fontSize: "11.5px", fontWeight: 500, color: "var(--text-tertiary)" }}>{listing.currency}</span>
            </>
          )}
          <PretScazutBadge listing={listing} />
        </div>

        {showMarginLine && (
          <div style={{ fontSize: "11.5px", color: marginColor(margin) }}>
            → {Math.round(listing.resale_price || 0)} RON revânzare
            {marginValue !== null && marginValue !== undefined && (
              <span> · marjă <strong>{Math.round(marginValue)} RON ({Math.round(margin || 0)}%)</strong></span>
            )}
          </div>
        )}

        {/* Slot opțional specificații (ex. an/km/combustibil/cutie la Auto). Radar nu-l pasează. */}
        {specsNode}

        {listing.fee_ceiling !== null && listing.fee_ceiling !== undefined && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".08em", color: "var(--text-mono)", textTransform: "uppercase" }}>
            Max recomandat · {Math.round(listing.fee_ceiling)} RON
          </div>
        )}

        <div style={{ fontSize: "10.5px", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
          {listing.location && (
            <>
              <span>{listing.location}</span>
              <span style={{ color: "var(--text-faint)" }}>·</span>
            </>
          )}
          <span>
            {listing.listed_at && formatListedDate(listing.listed_at) ? (
              <>postat {formatListedDate(listing.listed_at)} · găsit {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}</>
            ) : (
              <>găsit {formatListedDate(listing.found_at) || timeAgo(listing.found_at)}</>
            )}
          </span>
          {/* FRONT-1 — al treilea segment, DOAR pe anunturile chiar repromovate
              (>= 24 h intre publicare si reactualizare, vezi bumpInfo). Semnalul:
              anunt vechi care se tot bumpa = marfa care nu pleaca = loc de negociere.
              Pe hover, ambele date absolute. */}
          {bumpInfo(listing).bumped && (
            <>
              <span style={{ color: "var(--text-faint)" }}>·</span>
              <span
                title={`Postat ${formatListedDate(listing.listed_at)} · reactualizat ${formatListedDate(listing.refreshed_at)}`}
                style={{ color: BUMP_COLOR, display: "inline-flex", alignItems: "center", gap: "3px" }}
              >
                <RefreshCw size={12} />
                reactualizat {timeAgo(listing.refreshed_at)}
              </span>
            </>
          )}
        </div>

        {/* RP-1 — vânzător + rating + badge de risc (randate doar când există date). */}
        {(listing.seller_name || listing.seller_rating != null || listing.seller_risk || memberSinceLabel(listing)) && (
          <div style={{ fontSize: "10.5px", color: "var(--text-tertiary)", display: "flex", alignItems: "center", gap: "7px", flexWrap: "wrap" }}>
            {listing.seller_name && (
              <span style={{ maxWidth: "55%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {listing.seller_name}
              </span>
            )}
            {sellerRatingLabel(listing) && (
              <span style={{ color: "var(--text-mono)" }}>{sellerRatingLabel(listing)}</span>
            )}
            {memberSinceLabel(listing) && (
              <span style={{ color: "var(--text-mono)" }}>{memberSinceLabel(listing)}</span>
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

        {confirmingDelete ? (
          <div onClick={(e) => e.stopPropagation()} style={{
            display: "flex", alignItems: "center", gap: "8px",
            marginTop: "auto",
            padding: "8px 10px",
            borderRadius: "10px",
            border: "1px solid rgba(248,113,113,.3)",
            background: "rgba(248,113,113,.06)",
          }}>
            <span style={{ fontSize: "11px", color: "#fca5a5", flex: 1 }}>
              Ștergi acest anunț definitiv?
            </span>
            <button
              onClick={onConfirmDelete}
              style={{
                padding: "4px 10px", background: "rgba(248,113,113,.18)", color: "#f87171",
                border: "1px solid rgba(248,113,113,.4)", borderRadius: "8px", fontSize: "11px",
                fontWeight: 600, cursor: "pointer", fontFamily: "var(--font-sans)",
              }}
            >
              Confirmă
            </button>
            <button
              onClick={onCancelDelete}
              style={{
                padding: "4px 10px", background: "rgba(148,163,184,.07)", color: "var(--text-dim)",
                border: "1px solid rgba(148,163,184,.2)", borderRadius: "8px", fontSize: "11px",
                cursor: "pointer", fontFamily: "var(--font-sans)",
              }}
            >
              Anulează
            </button>
          </div>
        ) : (
        // UI-1 — zona de actiuni pe DOUA randuri. Inainte, „Deschide pe <platforma>"
        // statea pe acelasi rand cu „Salveaza"/„Ignora" si se taia la nume lungi
        // (LaJumate, Autoscout24, Facebook Marketplace). Orice reglaj de padding sau
        // de font s-ar fi rupt la primul nume si mai lung, deci butonul a coborat pe
        // randul lui, pe toata latimea — acolo incape mereu.
        <div style={{
          display: "flex", flexDirection: "column", gap: "0.375rem",
          marginTop: "auto", paddingTop: "8px",
        }}>
          {randUnuAreContinut && (
          // `alignItems: "stretch"` NU e decorativ: de el depinde ca IconButton
          // (aspectRatio 1) sa iasa patrat, la inaltimea butoanelor cu text.
          <div style={{ display: "flex", gap: "0.375rem", alignItems: "stretch" }}>
          {/* Fiecare buton cere handlerul lui. `hideActions` singur nu mai e de ajuns:
              feed-ul de deal-uri paseaza `onSave` (promovare) dar NU si `onIgnore`,
              de cand starea `ignorat` a fost scoasa la MAG-1 — butonul randat
              neconditionat arunca TypeError la click. */}
          {!hideActions && onSave && (
          <button
            onClick={(e) => { e.stopPropagation(); onSave(); }}
            style={{
              display: "inline-flex", alignItems: "center", gap: "5px",
              padding: "6px 11px", borderRadius: "9px",
              background: listing.status === "saved" ? "rgba(74,222,128,.2)" : "rgba(74,222,128,.08)",
              color: "#4ade80",
              border: "1px solid rgba(74,222,128,.32)",
              fontFamily: "var(--font-sans)", fontSize: "11px", fontWeight: 600,
              cursor: "pointer", transition: "all .15s ease",
            }}
          >
            <Bookmark style={{ width: "11px", height: "11px" }} strokeWidth={2} />
            {listing.status === "saved" ? "Salvat" : "Salvează"}
          </button>
          )}
          {!hideActions && onIgnore && (
          <button
            onClick={(e) => { e.stopPropagation(); onIgnore(); }}
            style={{
              display: "inline-flex", alignItems: "center", gap: "5px",
              padding: "6px 11px", borderRadius: "9px",
              background: listing.status === "ignored" ? "rgba(148,163,184,.18)" : "rgba(148,163,184,.07)",
              color: "var(--text-dim)",
              border: "1px solid rgba(148,163,184,.2)",
              fontFamily: "var(--font-sans)", fontSize: "11px", fontWeight: 600,
              cursor: "pointer", transition: "all .15s ease",
            }}
          >
            <EyeOff style={{ width: "11px", height: "11px" }} strokeWidth={2} />
            {listing.status === "ignored" ? "Ignorat" : "Ignoră"}
          </button>
          )}
          {/* Butoanele-iconita se lipesc de marginea dreapta; `marginLeft: auto` sta
              pe PRIMUL prezent, ca randul sa arate la fel si cand unul lipseste. */}
          {onToggleCompare && (
            <IconButton
              icon={Scale}
              title={compareSelected ? "Scoate din comparare" : "Adaugă la comparare"}
              active={compareSelected}
              onClick={onToggleCompare}
              style={{ marginLeft: "auto" }}
            />
          )}
          {/* `onDelete &&`: feed-ul de deal-uri nu paseaza handlerul, iar butonul
              randat neconditionat arunca TypeError la click. */}
          {onDelete && (
            <IconButton
              icon={Trash2}
              title="Șterge anunțul"
              danger
              className="listing-trash"
              onClick={onDelete}
              style={onToggleCompare ? undefined : { marginLeft: "auto" }}
            />
          )}
          </div>
          )}

          <button
            onClick={(e) => {
              e.stopPropagation();
              if (onOpenExternal) onOpenExternal();
              window.open(listing.url, "_blank", "noopener,noreferrer");
            }}
            title={openLabel}
            className="listing-open"
            style={{
              width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "5px",
              padding: "6px 8px", borderRadius: "9px",
              border: "1px solid rgba(34,211,238,.4)",
              background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)",
              color: "#7ee7f8", fontFamily: "var(--font-sans)", fontSize: "10.5px", fontWeight: 600,
              cursor: "pointer", whiteSpace: "nowrap", transition: "all .15s ease",
            }}
          >
            <ExternalLink style={{ width: "11px", height: "11px" }} strokeWidth={2} />
            {openLabel}
          </button>
        </div>
        )}
      </div>
    </div>
  );
}
