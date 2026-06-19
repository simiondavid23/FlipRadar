"use client";
// FlipRadar — Modulul 1 Marketplace: card minimal de anunt (cautare + salvate).
import { Heart, ExternalLink, Trash2, ImageOff } from "lucide-react";
import { platformLabel } from "@/lib/marketplaceConstants";

const PLATFORM_COLORS = {
  olx: "#0f9d58", vinted: "#09b1ba", facebook: "#1877f2", lajumate: "#e11d48",
  publi24: "#f97316", okazii: "#9333ea", kleinanzeigen: "#2dbe60",
};

export default function MarketplaceListingCard({ listing, onSave, onDelete, isSaved, busy }) {
  const plat = listing.source || listing.platform || "";
  const accent = PLATFORM_COLORS[plat] || "#64748b";
  const price = listing.price;

  return (
    <div style={{
      backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
      borderRadius: "0.75rem", overflow: "hidden", display: "flex", flexDirection: "column",
    }}>
      {/* Thumbnail */}
      <div style={{ position: "relative", width: "100%", aspectRatio: "4 / 3", backgroundColor: "var(--bg-dark)", overflow: "hidden" }}>
        {listing.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={listing.thumbnail_url} alt={listing.title || ""} loading="lazy"
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={(e) => { e.currentTarget.style.display = "none"; }} />
        ) : (
          <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
            <ImageOff style={{ width: "28px", height: "28px" }} />
          </div>
        )}
        <span style={{
          position: "absolute", top: "0.5rem", left: "0.5rem", padding: "0.125rem 0.5rem",
          borderRadius: "0.375rem", fontSize: "0.6875rem", fontWeight: 700, color: "white",
          backgroundColor: accent,
        }}>
          {platformLabel(plat)}
        </span>
      </div>

      {/* Body */}
      <div style={{ padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.375rem", flex: 1 }}>
        <h3 style={{
          fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, lineHeight: 1.3,
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", minHeight: "2.1em",
        }}>
          {listing.title}
        </h3>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
          <span style={{ fontSize: "1rem", fontWeight: 700, color: "#4ade80" }}>
            {price != null ? `${Number(price).toLocaleString("ro-RO")} ${listing.currency || ""}` : "—"}
          </span>
          {listing.condition && (
            <span style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.375rem", padding: "0.0625rem 0.375rem" }}>
              {listing.condition}
            </span>
          )}
        </div>

        {listing.location && (
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {listing.location}
          </span>
        )}

        {/* Actiuni */}
        <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto", paddingTop: "0.375rem" }}>
          {onSave && (
            <button type="button" onClick={() => onSave(listing)} disabled={busy || isSaved} title={isSaved ? "Salvat" : "Salveaza"}
              style={{
                flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.25rem",
                padding: "0.375rem", borderRadius: "0.5rem", fontSize: "0.75rem", fontWeight: 600,
                border: "1px solid var(--border-color)", cursor: isSaved ? "default" : "pointer",
                backgroundColor: isSaved ? "rgba(244,114,182,0.15)" : "transparent",
                color: isSaved ? "#f472b6" : "var(--text-secondary)",
              }}>
              <Heart style={{ width: "14px", height: "14px", fill: isSaved ? "#f472b6" : "none" }} />
              {isSaved ? "Salvat" : "Salveaza"}
            </button>
          )}
          {onDelete && (
            <button type="button" onClick={() => onDelete(listing)} disabled={busy} title="Sterge"
              style={{
                flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.25rem",
                padding: "0.375rem", borderRadius: "0.5rem", fontSize: "0.75rem", fontWeight: 600,
                border: "1px solid var(--border-color)", cursor: "pointer", backgroundColor: "transparent", color: "#f87171",
              }}>
              <Trash2 style={{ width: "14px", height: "14px" }} /> Sterge
            </button>
          )}
          {listing.source_url && (
            <a href={listing.source_url} target="_blank" rel="noopener noreferrer" title="Deschide"
              style={{
                flex: onSave || onDelete ? "0 0 auto" : 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.25rem",
                padding: "0.375rem 0.625rem", borderRadius: "0.5rem", fontSize: "0.75rem", fontWeight: 600,
                border: "none", backgroundColor: "var(--blue-primary)", color: "white", textDecoration: "none",
              }}>
              <ExternalLink style={{ width: "14px", height: "14px" }} /> Deschide
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
