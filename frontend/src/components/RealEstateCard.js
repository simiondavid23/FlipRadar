"use client";
// FlipRadar — Modul Imobiliare: card anunt (thumbnail mare + specs compacte).
import { Heart, ExternalLink, Trash2, ImageOff, MapPin } from "lucide-react";
import { rePlatformLabel, rePlatformColor } from "@/lib/realEstateConstants";

export default function RealEstateCard({ listing, onSave, onDelete, isSaved, busy }) {
  const accent = rePlatformColor(listing.platform);
  const specs = [
    listing.camere != null ? `${listing.camere} camere` : null,
    listing.suprafata_mp != null ? `${Number(listing.suprafata_mp)} mp` : null,
    listing.etaj ? `Etaj ${listing.etaj}` : null,
    listing.an_constructie ? `${listing.an_constructie}` : null,
  ].filter(Boolean);
  const loc = [listing.locatie_oras, listing.locatie_judet].filter(Boolean).join(", ");
  const savedAt = listing.created_at ? new Date(listing.created_at).toLocaleDateString("ro-RO") : null;

  return (
    <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", overflow: "hidden", display: "flex", flexDirection: "column" }}>
      {/* Thumbnail mare (16:10) */}
      <div style={{ position: "relative", width: "100%", aspectRatio: "16 / 10", backgroundColor: "var(--bg-dark)", overflow: "hidden" }}>
        {listing.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={listing.thumbnail_url} alt={listing.titlu || ""} loading="lazy"
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={(e) => { e.currentTarget.style.display = "none"; }} />
        ) : (
          <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
            <ImageOff style={{ width: "32px", height: "32px" }} />
          </div>
        )}
        <span style={{ position: "absolute", top: "0.5rem", left: "0.5rem", padding: "0.125rem 0.5rem", borderRadius: "0.375rem", fontSize: "0.6875rem", fontWeight: 700, color: "white", backgroundColor: accent }}>
          {rePlatformLabel(listing.platform)}
        </span>
        {listing.tip_anunt && (
          <span style={{ position: "absolute", top: "0.5rem", right: "0.5rem", padding: "0.125rem 0.5rem", borderRadius: "0.375rem", fontSize: "0.6875rem", fontWeight: 700, color: "white", backgroundColor: "rgba(0,0,0,0.55)", textTransform: "capitalize" }}>
            {listing.tip_anunt}
          </span>
        )}
      </div>

      <div style={{ padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.375rem", flex: 1 }}>
        <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, lineHeight: 1.3,
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", minHeight: "2.3em" }}>
          {listing.titlu || "Anunt imobiliar"}
        </h3>

        <span style={{ fontSize: "1.0625rem", fontWeight: 700, color: "#4ade80" }}>
          {listing.pret != null ? `${Number(listing.pret).toLocaleString("ro-RO")} ${listing.moneda || "EUR"}` : "Pret la cerere"}
        </span>

        {specs.length > 0 && (
          <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>{specs.join("  •  ")}</div>
        )}

        {loc && (
          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: "0.25rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            <MapPin style={{ width: "11px", height: "11px" }} /> {loc}
          </span>
        )}

        {onDelete && savedAt && (
          <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>Salvat: {savedAt}</span>
        )}

        <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto", paddingTop: "0.5rem" }}>
          {onSave && (
            <button type="button" onClick={() => onSave(listing)} disabled={busy || isSaved} title={isSaved ? "Salvat" : "Salveaza"}
              style={btn(isSaved ? "#f472b6" : "var(--text-secondary)", isSaved ? "rgba(244,114,182,0.15)" : "transparent")}>
              <Heart style={{ width: "13px", height: "13px", fill: isSaved ? "#f472b6" : "none" }} /> {isSaved ? "Salvat" : "Salveaza"}
            </button>
          )}
          {onDelete && (
            <button type="button" onClick={() => onDelete(listing)} disabled={busy} title="Sterge din salvate"
              style={btn("#f87171", "transparent")}>
              <Trash2 style={{ width: "13px", height: "13px" }} /> Sterge
            </button>
          )}
          {listing.source_url && (
            <a href={listing.source_url} target="_blank" rel="noopener noreferrer" title="Deschide"
              style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.25rem", padding: "0.375rem", borderRadius: "0.5rem", fontSize: "0.7rem", fontWeight: 600, border: "none", backgroundColor: "var(--blue-primary)", color: "white", textDecoration: "none" }}>
              <ExternalLink style={{ width: "13px", height: "13px" }} /> Deschide
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function btn(color, bg) {
  return {
    flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.25rem",
    padding: "0.375rem", borderRadius: "0.5rem", fontSize: "0.7rem", fontWeight: 600,
    border: "1px solid var(--border-color)", cursor: "pointer", backgroundColor: bg, color,
  };
}
