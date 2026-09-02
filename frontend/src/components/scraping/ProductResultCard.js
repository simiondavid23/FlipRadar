"use client";
import { Plus, Heart, ExternalLink } from "lucide-react";
import { styleFor } from "@/lib/sourceStyles";

/**
 * SEARCH-2 — cardul de produs, mutat din `dashboard/scraping/page.js` fara schimbari
 * de comportament: badge de sursa, EAN/SKU, „Stoc epuizat", pret colorat pe
 * `is_on_sale`, pret taiat + procentul de reducere, cele trei actiuni.
 *
 * Singura adaugire: echivalentul in RON pentru monedele straine (vezi `pretInRon`).
 */

/**
 * Pretul produsului in RON, pentru COMPARATIE intre magazine.
 *
 * Din cele 21 de domenii cautabile, 8 dau EUR — fara conversie, o sortare dupa pret
 * ar aseza 40 EUR sub 200 RON, adica exact invers. `null` inseamna „nu se poate
 * compara": fie n-avem pret, fie n-avem curs.
 *
 * Doar EUR se converteste: USD nu apare in registru, iar moneda `null` vine de pe
 * calea custom, care pune deja RON pe fiecare rezultat.
 */
export function pretInRon(product, eurRon) {
  const pret = Number(product?.price);
  if (!Number.isFinite(pret)) return null;
  const moneda = product?.currency || "RON";
  if (moneda === "RON") return pret;
  if (moneda === "EUR" && Number.isFinite(Number(eurRon))) return pret * Number(eurRon);
  return null;
}

const badge = (bg, border, color) => ({
  fontFamily: "var(--font-mono)",
  padding: "2.5px 7px",
  borderRadius: "7px",
  fontSize: "8.5px",
  letterSpacing: ".08em",
  background: bg,
  border: `1px solid ${border}`,
  color,
});

export default function ProductResultCard({ product, eurRon, onSave, onSaveAndTrack }) {
  const style = styleFor(product.source);
  const cur = product.currency || "RON";
  const inRon = cur !== "RON" ? pretInRon(product, eurRon) : null;

  return (
    <div className="glass-panel lift-hover" style={{ padding: "16px 18px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem", flexWrap: "wrap" }}>
            <h3 style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "14px", margin: 0 }}>{product.name}</h3>
            <span style={{ ...badge(style.bg, `${style.fg}55`, style.fg), textTransform: "uppercase" }}>{product.source}</span>
            {product.ean && (
              <span style={badge("rgba(253,224,71,0.14)", "rgba(253,224,71,0.4)", "#fde047")}>
                EAN: {product.ean}
              </span>
            )}
            {!product.ean && product.sku && (
              <span style={badge("rgba(148,163,184,0.12)", "rgba(148,163,184,0.3)", "var(--text-dim)")}>
                SKU: {product.sku}
              </span>
            )}
          </div>
          {product.in_stock === false ? (
            <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "#f87171" }}>
              Stoc epuizat
            </span>
          ) : product.price > 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", flexWrap: "wrap" }}>
              <span style={{ fontSize: "1.25rem", fontWeight: 700, color: product.is_on_sale ? "#f87171" : "#4ade80" }}>
                {product.price.toFixed(2)} {cur}
              </span>
              {/* Un SINGUR numar aproximativ per card: `original_price` nu se
                  converteste, ca sa nu punem doua aproximari langa doua exacte. */}
              {inRon != null && (
                <span
                  title={`curs BNR EUR/RON: ${eurRon}`}
                  style={{ fontFamily: "var(--font-mono)", fontSize: "11.5px", color: "var(--text-dim)" }}
                >
                  ≈ {inRon.toFixed(2)} RON
                </span>
              )}
              {product.is_on_sale && product.original_price > 0 && (
                <>
                  <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)", textDecoration: "line-through" }}>
                    {product.original_price.toFixed(2)} {cur}
                  </span>
                  <span style={{
                    padding: "0.125rem 0.5rem",
                    borderRadius: "0.25rem",
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    backgroundColor: "rgba(248,113,113,0.2)",
                    color: "#f87171",
                  }}>
                    Reducere -{Math.round(((product.original_price - product.price) / product.original_price) * 100)}%
                  </span>
                </>
              )}
            </div>
          ) : null}
        </div>
        <div style={{ display: "flex", gap: "0.375rem" }}>
          <button onClick={() => onSave(product)} title="Salveaza in baza de date"
            style={{ padding: "0.5rem", borderRadius: "10px", border: "none", backgroundColor: "transparent", color: "var(--text-secondary)", cursor: "pointer" }}>
            <Plus style={{ width: "1.25rem", height: "1.25rem" }} />
          </button>
          <button onClick={() => onSaveAndTrack(product)} title="Salveaza si urmareste"
            style={{ padding: "0.5rem", borderRadius: "10px", border: "none", backgroundColor: "transparent", color: "var(--text-secondary)", cursor: "pointer" }}>
            <Heart style={{ width: "1.25rem", height: "1.25rem" }} />
          </button>
          {product.source_url && (
            <a href={product.source_url} target="_blank" rel="noopener noreferrer"
              style={{ padding: "0.5rem", borderRadius: "10px", color: "var(--text-secondary)" }}>
              <ExternalLink style={{ width: "1.25rem", height: "1.25rem" }} />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
