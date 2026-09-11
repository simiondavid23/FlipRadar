"use client";
// UI-1 — buton doar-cu-iconita, cu UN SINGUR stil pentru toate randurile de actiuni.
//
// De ce exista: iconitele de comparare / stergere din carduri nu erau centrate, iar
// fiecare loc isi avea propriul padding. Reparat intr-un singur card, defectul ar fi
// reaparut in celalalt la prima modificare, asa ca stilul traieste aici.
//
// Centrarea vine din trei lucruri, toate necesare: `padding: 0` (fara padding
// asimetric mostenit), `lineHeight: 0` (altfel inaltimea liniei de text a
// butonului impinge svg-ul in jos) si `display: block` pe svg (un inline-svg sta
// pe linia de baza a textului, nu in centrul cutiei).
//
// `alignSelf: stretch` + `aspectRatio: 1` fac butonul PATRAT, exact cat inaltimea
// butoanelor cu text de langa el, fara nicio cifra hardcodata — de aceea randul
// care il contine trebuie sa aiba `alignItems: "stretch"`.
//
// Culoarea starii active e cyan-ul cardului (#7ee7f8), nu albastru: butonul sta
// langa „Deschide pe <platforma>", care e cyan, iar fundalul activ se deriva din
// ACEEASI valoare — altfel accentul si fundalul ar fi venit din doua familii.
export default function IconButton({
  icon: Icon, title, onClick, active, danger, className, style,
}) {
  const color = danger ? "#f87171" : active ? "#7ee7f8" : "var(--text-secondary)";
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      className={className}
      // stopPropagation aici, nu la fiecare apelant: cardurile sunt clicabile pe
      // toata suprafata (deschid modalul), iar un buton de actiune nu are voie sa
      // declanseze si clicul cardului.
      onClick={(e) => { e.stopPropagation(); onClick?.(e); }}
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        alignSelf: "stretch", aspectRatio: "1 / 1", padding: 0, lineHeight: 0,
        borderRadius: "0.375rem", border: "1px solid var(--border-color)",
        backgroundColor: active ? "rgba(126,231,248,0.15)" : "transparent",
        color, cursor: "pointer", flexShrink: 0, transition: "all .15s ease",
        ...style,
      }}
    >
      <Icon style={{ width: "14px", height: "14px", display: "block" }} strokeWidth={1.8} />
    </button>
  );
}
