"use client";
// FlipRadar — card pentru anunturi auto (OLX Auto / Autovit / Mobile.de / etc.).
import { Heart, ExternalLink, Trash2, ImageOff, Sparkles, MapPin } from "lucide-react";

const PLATFORM = {
  olx_auto: { label: "OLX Auto", color: "#0f9d58" },
  autovit: { label: "AutoVit", color: "#1d4ed8" },
  mobile_de: { label: "Mobile.de", color: "#f59e0b" },
  autoscout24: { label: "AutoScout24", color: "#fbbf24" },
  facebook_auto: { label: "FB Auto", color: "#1877f2" },
  kleinanzeigen_auto: { label: "Kleinanzeigen", color: "#2dbe60" },
};

function aiSummary(ai) {
  if (!ai || typeof ai !== "object") return null;
  const parts = [];
  if (ai.defects_mentioned) {
    const n = Array.isArray(ai.defects_mentioned) ? ai.defects_mentioned.length : 1;
    parts.push(`${n} defecte mentionate`);
  }
  if (ai.itp_valid_until) parts.push(`ITP: ${ai.itp_valid_until}`);
  if (ai.num_owners) parts.push(`${ai.num_owners} proprietari`);
  return parts.length ? parts.join(" · ") : null;
}

export default function AutoListingCard({ listing, onSave, onDelete, onAnalyze, isSaved, busy }) {
  const plat = PLATFORM[listing.platform] || { label: listing.platform, color: "#64748b" };
  const specs = [
    listing.year ? `${listing.year}` : null,
    listing.km != null ? `${Number(listing.km).toLocaleString("ro-RO")} km` : null,
    listing.engine_type || null,
    listing.gearbox || null,
  ].filter(Boolean);
  const ai = aiSummary(listing.ai_extract);

  return (
    <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", overflow: "hidden", display: "flex", flexDirection: "column" }}>
      <div style={{ position: "relative", width: "100%", aspectRatio: "4 / 3", backgroundColor: "var(--bg-dark)" }}>
        {listing.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={listing.thumbnail_url} alt={listing.titlu || ""} loading="lazy"
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={(e) => { e.currentTarget.style.display = "none"; }} />
        ) : (
          <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
            <ImageOff style={{ width: "28px", height: "28px" }} />
          </div>
        )}
        <span style={{ position: "absolute", top: "0.5rem", left: "0.5rem", padding: "0.125rem 0.5rem", borderRadius: "0.375rem", fontSize: "0.6875rem", fontWeight: 700, color: "white", backgroundColor: plat.color }}>
          {plat.label}
        </span>
      </div>

      <div style={{ padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.375rem", flex: 1 }}>
        <h3 style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, lineHeight: 1.3,
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", minHeight: "2.1em" }}>
          {listing.titlu}
        </h3>

        {specs.length > 0 && (
          <div style={{ fontSize: "0.6875rem", color: "var(--text-secondary)" }}>{specs.join("  •  ")}</div>
        )}

        <span style={{ fontSize: "1rem", fontWeight: 700, color: "#4ade80" }}>
          {listing.pret != null ? `${Number(listing.pret).toLocaleString("ro-RO")} ${listing.moneda || ""}` : "—"}
        </span>

        {listing.locatie && (
          <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: "0.25rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            <MapPin style={{ width: "11px", height: "11px" }} /> {listing.locatie}
          </span>
        )}

        {ai && (
          <div style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.6875rem", color: "#a78bfa", backgroundColor: "rgba(167,139,250,0.12)", borderRadius: "0.375rem", padding: "0.1875rem 0.375rem" }}>
            <Sparkles style={{ width: "11px", height: "11px" }} /> AI: {ai}
          </div>
        )}

        <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto", paddingTop: "0.5rem", flexWrap: "wrap" }}>
          {onSave && (
            <button type="button" onClick={() => onSave(listing)} disabled={busy || isSaved}
              style={btn(isSaved ? "#f472b6" : "var(--text-secondary)", isSaved ? "rgba(244,114,182,0.15)" : "transparent")}>
              <Heart style={{ width: "13px", height: "13px", fill: isSaved ? "#f472b6" : "none" }} /> {isSaved ? "Salvat" : "Salveaza"}
            </button>
          )}
          {onDelete && (
            <button type="button" onClick={() => onDelete(listing)} disabled={busy} style={btn("#f87171", "transparent")}>
              <Trash2 style={{ width: "13px", height: "13px" }} /> Sterge
            </button>
          )}
          {onAnalyze && (
            <button type="button" onClick={() => onAnalyze(listing)} style={btn("#a78bfa", "rgba(167,139,250,0.12)")}>
              <Sparkles style={{ width: "13px", height: "13px" }} /> Analiza AI
            </button>
          )}
          {listing.source_url && (
            <a href={listing.source_url} target="_blank" rel="noopener noreferrer"
              style={{ flex: "0 0 auto", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.25rem", padding: "0.375rem 0.625rem", borderRadius: "0.5rem", fontSize: "0.7rem", fontWeight: 600, border: "none", backgroundColor: "var(--blue-primary)", color: "white", textDecoration: "none" }}>
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
    flex: 1, minWidth: "70px", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.25rem",
    padding: "0.375rem", borderRadius: "0.5rem", fontSize: "0.7rem", fontWeight: 600,
    border: "1px solid var(--border-color)", cursor: "pointer", backgroundColor: bg, color,
  };
}
