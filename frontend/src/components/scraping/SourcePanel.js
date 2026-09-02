"use client";
import { useState } from "react";
import { ExternalLink, ChevronDown, ChevronRight } from "lucide-react";
import { styleFor } from "@/lib/sourceStyles";
import ProductResultCard from "./ProductResultCard";

/**
 * SEARCH-2 — un magazin, un panou.
 *
 * Panoul exista din clipa in care cautarea porneste (starea `pending`), nu din clipa
 * in care raspunde: asa lista nu sare, iar userul vede de la inceput pe cine
 * asteapta. Panourile FARA rezultate reale (empty/blocked/error) sunt pliate
 * implicit, ca sa nu impinga rezultatele bune sub ecran.
 */

const PILL = {
  fontFamily: "var(--font-mono)",
  fontSize: "9px",
  letterSpacing: ".1em",
  textTransform: "uppercase",
  padding: "3px 8px",
  borderRadius: "7px",
  whiteSpace: "nowrap",
};

/** Pastila de stare + daca panoul are continut care merita deschis implicit. */
function stare(state, result) {
  if (state === "pending") return { text: "in asteptare", bg: "rgba(148,163,184,0.12)", fg: "var(--text-dim)" };
  if (state === "loading") return { text: "se cauta…", bg: "rgba(34,211,238,0.14)", fg: "#22d3ee", spinner: true };
  if (state === "anulat") return { text: "anulat", bg: "rgba(148,163,184,0.12)", fg: "var(--text-dim)" };

  const status = result?.status;
  if (status === "ok") return { text: `${result.count} rezultate`, bg: "rgba(74,222,128,0.14)", fg: "#4ade80", deschis: true };
  if (status === "empty") return { text: "0 rezultate", bg: "rgba(148,163,184,0.12)", fg: "var(--text-dim)" };
  if (status === "blocked") return { text: "blocat / fara raspuns", bg: "rgba(248,113,113,0.16)", fg: "#f87171" };
  if (status === "error") return { text: "eroare", bg: "rgba(248,113,113,0.16)", fg: "#f87171", motivVizibil: true };
  if (status === "unsupported") return { text: "necautabil", bg: "rgba(148,163,184,0.12)", fg: "var(--text-dim)", motivVizibil: true };
  return { text: "necunoscut", bg: "rgba(148,163,184,0.12)", fg: "var(--text-dim)" };
}

export default function SourcePanel({ source, state, result, eurRon, sorteaza, onSave, onSaveAndTrack }) {
  const st = stare(state, result);
  // Deschis/pliat e stare LOCALA cu implicit derivat: `null` inseamna „n-a atins
  // userul", deci se foloseste implicitul de mai sus.
  const [deschisManual, setDeschisManual] = useState(null);
  const deschis = deschisManual ?? Boolean(st.deschis);

  const style = styleFor(source.domain);
  const produse = result?.status === "ok" ? result.results || [] : [];

  // SEARCH-2b — sortarea vine din `page.js` ca prop, ca sa existe intr-o SINGURA
  // copie: panourile si lista unica trebuie sa claseze identic, iar doua
  // implementari ar diverge la prima corectura.
  const sortate = typeof sorteaza === "function" ? sorteaza(produse) : produse;

  const arePlus = produse.length > 0 || st.motivVizibil;

  return (
    <div className="glass-panel" style={{ padding: "12px 14px" }}>
      <div
        onClick={() => arePlus && setDeschisManual(!deschis)}
        style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", cursor: arePlus ? "pointer" : "default" }}
      >
        {arePlus ? (
          deschis
            ? <ChevronDown style={{ width: 14, height: 14, color: "var(--text-dim)" }} />
            : <ChevronRight style={{ width: 14, height: 14, color: "var(--text-dim)" }} />
        ) : <span style={{ width: 14 }} />}

        <span style={{ fontFamily: "var(--font-mono)", padding: "2.5px 7px", borderRadius: "7px", fontSize: "8.5px", letterSpacing: ".08em", textTransform: "uppercase", background: style.bg, border: `1px solid ${style.fg}55`, color: style.fg }}>
          {source.domain}
        </span>
        <span style={{ color: "var(--text-primary)", fontSize: "13px", fontWeight: 600 }}>{source.label}</span>

        <span style={{ ...PILL, background: st.bg, color: st.fg, display: "inline-flex", alignItems: "center", gap: "6px" }}
          title={result?.reason || undefined}>
          {st.spinner && (
            <span style={{ width: 9, height: 9, border: "2px solid currentColor", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite", display: "inline-block" }} />
          )}
          {st.text}
        </span>

        {result?.status === "ok" && result.truncated && result.more_url && (
          <a
            href={result.more_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            style={{ ...PILL, background: "rgba(34,211,238,0.12)", color: "#22d3ee", display: "inline-flex", alignItems: "center", gap: "5px", textDecoration: "none" }}
          >
            vezi toate pe site <ExternalLink style={{ width: 10, height: 10 }} />
          </a>
        )}
      </div>

      {/* `reason` de la error/unsupported e text scurt din backend, fara traceback —
          e facut ca sa fie citit, deci se arata, nu se ascunde in tooltip. */}
      {st.motivVizibil && result?.reason && (
        <p style={{ margin: "8px 0 0 24px", fontSize: "11.5px", color: "#f87171" }}>{result.reason}</p>
      )}

      {deschis && produse.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "10px" }}>
          {sortate.map((product, i) => (
            <ProductResultCard
              key={`${product.source_url || product.name}-${i}`}
              product={product}
              eurRon={eurRon}
              onSave={onSave}
              onSaveAndTrack={onSaveAndTrack}
            />
          ))}
        </div>
      )}
    </div>
  );
}
