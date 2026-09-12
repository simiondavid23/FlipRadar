"use client";
import { useState, useEffect } from "react";
import { ChevronDown } from "lucide-react";

// SET-1b — un rand pliabil din pagina Setari. Inlocuieste vechiul `Section`:
// acelasi `glass-panel`, dar antetul e un buton pe toata latimea, iar in dreapta
// lui un `summary` derivat din starea reala (niciodata un text-sablon), ca sa poti
// citi configuratia fara sa deschizi randul.
//
// DOUA decizii care nu se vad din semnatura:
//  1. Continutul ramane MONTAT cand randul e inchis (`display: none`, nu unmount).
//     Altfel o valoare pe jumatate tastata s-ar pierde la fiecare inchidere, iar
//     componentele cu stare proprie (FacebookGroupsSection) si-ar reface fetch-ul.
//  2. Deep-link-ul se rezolva la montarea RANDULUI, nu a paginii: pagina randeaza
//     randurile abia dupa `loading === false`, deci un efect la nivel de pagina ar
//     rula cand `#id` n-are inca tinta in DOM.
export default function SettingsRow({ id, title, summary, dirty = false, children }) {
  const [open, setOpen] = useState(false);

  // Deschide + deruleaza daca hash-ul curent ne numeste. Nu scriem noi hash-ul la
  // toggle: ar umple istoricul browserului cu intrari pe care nimeni nu le-a cerut.
  //
  // Verificarea initiala e amanata un cadru, din doua motive care coincid: un
  // `setState` sincron in efect declanseaza randari in cascada (regula eslint), iar
  // `scrollIntoView` are nevoie de un layout asezat ca sa nimereasca randul.
  useEffect(() => {
    if (typeof window === "undefined" || !id) return undefined;
    const aplica = () => {
      if (window.location.hash !== "#" + id) return;
      setOpen(true);
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ block: "start" });
    };
    const cadru = window.requestAnimationFrame(aplica);
    window.addEventListener("hashchange", aplica);
    return () => {
      window.cancelAnimationFrame(cadru);
      window.removeEventListener("hashchange", aplica);
    };
  }, [id]);

  return (
    <section id={id} className="glass-panel" style={{ padding: "18px", marginTop: "14px" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          gap: "12px", width: "100%", padding: 0, background: "transparent",
          border: "none", cursor: "pointer", textAlign: "left",
          fontFamily: "var(--font-sans)",
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: "7px", minWidth: 0 }}>
          <span style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--text-primary)" }}>
            {title}
          </span>
          {dirty ? (
            <span
              title="Modificari nesalvate"
              style={{
                width: "6px", height: "6px", borderRadius: "50%",
                background: "#22d3ee", flexShrink: 0,
                boxShadow: "0 0 6px rgba(34,211,238,.7)",
              }}
            />
          ) : null}
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "9px", minWidth: 0 }}>
          {summary ? (
            <span style={{
              fontSize: "12px", color: "var(--text-secondary)", textAlign: "right",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {summary}
            </span>
          ) : null}
          <ChevronDown
            style={{
              width: "15px", height: "15px", flexShrink: 0, color: "var(--text-muted)",
              transform: open ? "rotate(180deg)" : "none",
            }}
            strokeWidth={1.8}
          />
        </span>
      </button>

      <div style={{
        display: open ? "flex" : "none",
        flexDirection: "column", gap: "10px", marginTop: "14px",
      }}>
        {children}
      </div>
    </section>
  );
}
