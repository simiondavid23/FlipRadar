// FlipRadar — Modul Imobiliare: constante comune (platforme, tip proprietate, facilitati).

export const RE_PLATFORMS = [
  { value: "olx", label: "OLX Imobiliare" },
  { value: "storia", label: "Storia.ro" },
  { value: "imobiliare", label: "Imobiliare.ro" },
  { value: "facebook", label: "Facebook Marketplace" },
];

export const TIP_ANUNT = [
  { value: "vanzare", label: "Vanzare" },
  { value: "inchiriere", label: "Inchiriere" },
];

export const TIP_PROPRIETATE = [
  { value: "apartament", label: "Apartament" },
  { value: "casa", label: "Casa" },
  { value: "garsoniera", label: "Garsoniera" },
  { value: "teren", label: "Teren" },
  { value: "comercial", label: "Comercial" },
];

export const ROOMS = ["1", "2", "3", "4+"];

// Cheile corespund campului `facilitati` (JSON) din real_estate_listing.
export const FACILITIES = [
  { key: "parcare", label: "Parcare" },
  { key: "balcon", label: "Balcon" },
  { key: "lift", label: "Lift" },
  { key: "gradina", label: "Gradina" },
  { key: "bloc_nou", label: "Bloc nou" },
  { key: "centrala", label: "Centrala proprie" },
];

const PLATFORM_COLORS = {
  olx: "#0f9d58", storia: "#7c3aed", imobiliare: "#e11d48", facebook: "#1877f2",
};

export const rePlatformLabel = (v) => RE_PLATFORMS.find((p) => p.value === v)?.label || v || "";
export const rePlatformColor = (v) => PLATFORM_COLORS[v] || "#64748b";

export const JUDETE = [
  "Alba", "Arad", "Arges", "Bacau", "Bihor", "Bistrita-Nasaud", "Botosani", "Braila",
  "Brasov", "Bucuresti", "Buzau", "Calarasi", "Caras-Severin", "Cluj", "Constanta",
  "Covasna", "Dambovita", "Dolj", "Galati", "Giurgiu", "Gorj", "Harghita", "Hunedoara",
  "Ialomita", "Iasi", "Ilfov", "Maramures", "Mehedinti", "Mures", "Neamt", "Olt",
  "Prahova", "Salaj", "Satu Mare", "Sibiu", "Suceava", "Teleorman", "Timis", "Tulcea",
  "Valcea", "Vaslui", "Vrancea",
];
