"use client";
import { useSyncExternalStore } from "react";
import Link from "next/link";
import { Calendar, Bell } from "lucide-react";

// Bara de sus comuna tuturor paginilor de dashboard:
// breadcrumb mono · chip cu data curenta · clopotel cu dot cyan · slot de actiuni.
//
// `path` = segmentele de dupa FLIPRADAR, ex. ["RADAR PIATA", "FEED ANUNTURI"].
// `children` = actiunile din dreapta (ex. butonul "Scanează acum").

const chipStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  padding: "8px 13px",
  borderRadius: "12px",
  background:
    "linear-gradient(rgba(8,14,27,.72),rgba(8,14,27,.72)) padding-box, linear-gradient(135deg, rgba(34,211,238,.32), rgba(59,130,246,.1) 50%, transparent) border-box",
  border: "1px solid transparent",
  fontSize: "12px",
  color: "var(--text-dim)",
  whiteSpace: "nowrap",
};

// Data curenta se citeste ca "store extern": paginile sunt pre-randate la build
// (output: "export"), asa ca serverul da string gol si abia clientul completeaza —
// fara hydration mismatch si fara setState in efect. Cache-ul pe zi pastreaza
// referinta stabila ceruta de useSyncExternalStore.
let dateCache = { key: null, value: "" };
function readToday() {
  const d = new Date();
  const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  if (dateCache.key !== key) {
    const s = d.toLocaleDateString("ro-RO", {
      weekday: "long", day: "numeric", month: "long", year: "numeric",
    });
    dateCache = { key, value: s.charAt(0).toUpperCase() + s.slice(1) };
  }
  return dateCache.value;
}
const neverChanges = () => () => {};
const emptyOnServer = () => "";

export default function TopBar({ path = [], children, showDate = true, showBell = true }) {
  const today = useSyncExternalStore(neverChanges, readToday, emptyOnServer);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
      <div className="breadcrumb">
        FLIPRADAR
        {path.map((seg) => (
          <span key={seg}>
            {" "}<span className="sep">{"//"}</span> {seg}
          </span>
        ))}
      </div>
      <div style={{ flex: 1 }} />
      {showDate && today && (
        <div style={chipStyle}>
          <Calendar style={{ width: "13px", height: "13px", color: "#7ee7f8", flexShrink: 0 }} strokeWidth={1.8} />
          {today}
        </div>
      )}
      {showBell && (
        <Link
          href="/dashboard/alerts"
          aria-label="Alerte preț"
          title="Alerte preț"
          className="glow-hover"
          style={{
            position: "relative", width: "36px", height: "36px", borderRadius: "12px",
            background:
              "linear-gradient(rgba(8,14,27,.72),rgba(8,14,27,.72)) padding-box, linear-gradient(135deg, rgba(34,211,238,.32), rgba(59,130,246,.1) 50%, transparent) border-box",
            border: "1px solid transparent", display: "flex", alignItems: "center",
            justifyContent: "center", flexShrink: 0,
          }}
        >
          <Bell style={{ width: "15px", height: "15px", color: "var(--text-dim)" }} strokeWidth={1.8} />
          <span
            style={{
              position: "absolute", top: "8px", right: "9px", width: "6px", height: "6px",
              borderRadius: "50%", background: "#22d3ee", boxShadow: "0 0 7px #22d3ee",
            }}
          />
        </Link>
      )}
      {children}
    </div>
  );
}
