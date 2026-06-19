"use client";
// FlipRadar — card dens pentru loturi de licitatie auto (Copart/IAAI/SCA/OpenLane).
import { Heart, ExternalLink, Trash2, ImageOff, MapPin, Calendar, Gauge, Lock } from "lucide-react";

const PLATFORM = {
  copart: { label: "Copart", color: "#0a4d8c" },
  iaai: { label: "IAAI", color: "#c8102e" },
  sca: { label: "SCA", color: "#1d4ed8" },
  openlane: { label: "OpenLane", color: "#0f766e" },
};

const SEVERE = ["fire", "flood", "water", "rollover", "front", "rear", "burn", "total", "all over", "undercarriage"];

function damageColor(damage) {
  if (!damage) return "var(--text-muted)";
  const d = damage.toLowerCase();
  if (d.includes("minor") || d.includes("mechanical") || d.includes("side")) return "#fb923c"; // moderat
  if (SEVERE.some((s) => d.includes(s))) return "#f87171"; // sever
  return "#fb923c";
}

function fmtDate(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString("ro-RO", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return iso;
  }
}

function AccountField({ label, value }) {
  const needsAccount = value == null;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.6875rem" }}>
      <span style={{ color: "var(--text-muted)" }}>{label}:</span>
      {needsAccount ? (
        <span style={{ color: "var(--text-muted)", fontStyle: "italic", display: "inline-flex", alignItems: "center", gap: "0.125rem" }}>
          <Lock style={{ width: "10px", height: "10px" }} /> Necesita cont
        </span>
      ) : (
        <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{String(value)}</span>
      )}
    </span>
  );
}

export default function AutoLotCard({ lot, onSave, onDelete, isSaved, busy }) {
  const plat = PLATFORM[lot.platform] || { label: lot.platform, color: "#64748b" };
  const title = lot.title || [lot.year, lot.make, lot.model].filter(Boolean).join(" ") || "Lot auto";
  const dmgColor = damageColor(lot.damage_primary);
  const auctionDate = fmtDate(lot.auction_date);
  const bool = (v) => (v == null ? null : v ? "Da" : "Nu");

  return (
    <div style={{
      backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
      borderRadius: "0.75rem", overflow: "hidden", display: "flex", flexDirection: "column",
    }}>
      <div style={{ position: "relative", width: "100%", aspectRatio: "4 / 3", backgroundColor: "var(--bg-dark)" }}>
        {lot.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={lot.thumbnail_url} alt={title} loading="lazy"
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
        <h3 style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, lineHeight: 1.3,
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {title}
        </h3>

        {lot.damage_primary && (
          <span style={{ fontSize: "0.6875rem", fontWeight: 700, color: dmgColor, border: `1px solid ${dmgColor}`, borderRadius: "0.375rem", padding: "0.0625rem 0.375rem", alignSelf: "flex-start" }}>
            {lot.damage_primary}
          </span>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: "0.125rem", fontSize: "0.6875rem", color: "var(--text-secondary)" }}>
          {(lot.location_city || lot.location_state) && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
              <MapPin style={{ width: "11px", height: "11px" }} /> {[lot.location_city, lot.location_state].filter(Boolean).join(", ")}
            </span>
          )}
          {auctionDate && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
              <Calendar style={{ width: "11px", height: "11px" }} /> {auctionDate}
            </span>
          )}
          {lot.odometer != null && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
              <Gauge style={{ width: "11px", height: "11px" }} /> {Number(lot.odometer).toLocaleString("ro-RO")} km/mi
            </span>
          )}
        </div>

        {/* Campuri care necesita cont */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.125rem", paddingTop: "0.25rem", borderTop: "1px dashed var(--border-color)" }}>
          <AccountField label="Bid curent" value={lot.current_bid} />
          <AccountField label="VIN" value={lot.vin} />
          <AccountField label="Starts/Drives" value={lot.starts == null && lot.drives == null ? null : `${bool(lot.starts) || "?"}/${bool(lot.drives) || "?"}`} />
        </div>

        <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto", paddingTop: "0.5rem" }}>
          {onSave && (
            <button type="button" onClick={() => onSave(lot)} disabled={busy || isSaved}
              style={btnStyle(isSaved ? "#f472b6" : "var(--text-secondary)", isSaved ? "rgba(244,114,182,0.15)" : "transparent", isSaved)}>
              <Heart style={{ width: "13px", height: "13px", fill: isSaved ? "#f472b6" : "none" }} /> {isSaved ? "Salvat" : "Salveaza"}
            </button>
          )}
          {onDelete && (
            <button type="button" onClick={() => onDelete(lot)} disabled={busy}
              style={btnStyle("#f87171", "transparent", false)}>
              <Trash2 style={{ width: "13px", height: "13px" }} /> Sterge
            </button>
          )}
          {lot.source_url && (
            <a href={lot.source_url} target="_blank" rel="noopener noreferrer"
              style={{ flex: "0 0 auto", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.25rem", padding: "0.375rem 0.625rem", borderRadius: "0.5rem", fontSize: "0.7rem", fontWeight: 600, border: "none", backgroundColor: "var(--blue-primary)", color: "white", textDecoration: "none" }}>
              <ExternalLink style={{ width: "13px", height: "13px" }} /> {plat.label}
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function btnStyle(color, bg, isSaved) {
  return {
    flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.25rem",
    padding: "0.375rem", borderRadius: "0.5rem", fontSize: "0.7rem", fontWeight: 600,
    border: "1px solid var(--border-color)", cursor: isSaved ? "default" : "pointer",
    backgroundColor: bg, color,
  };
}
