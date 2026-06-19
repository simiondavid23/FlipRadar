// FlipRadar — Modulul 1 Marketplace: constante comune (platforme, categorii,
// stari, distante, judete) folosite de paginile de cautare si de wizardul de alerte.

export const MARKETPLACE_PLATFORMS = [
  { value: "olx", label: "OLX" },
  { value: "vinted", label: "Vinted" },
  { value: "facebook", label: "FB Marketplace" },
  { value: "lajumate", label: "LaJumate" },
  { value: "publi24", label: "Publi24" },
  { value: "okazii", label: "Okazii" },
  { value: "kleinanzeigen", label: "eBay KA" },
];

// Eticheta lunga (folosita in wizard, pasul 1).
export const PLATFORM_LONG_LABEL = {
  olx: "OLX.ro",
  vinted: "Vinted.ro",
  facebook: "Facebook Marketplace",
  lajumate: "LaJumate.ro",
  publi24: "Publi24.ro",
  okazii: "Okazii.ro",
  kleinanzeigen: "eBay Kleinanzeigen",
};

export const MARKETPLACE_CATEGORIES = {
  olx: [
    { name: "Electronice si electrocasnice", sub: ["Telefoane mobile", "Laptopuri si PC", "Tablete", "Casti si audio", "TV si video", "Aparate foto"] },
    { name: "Imbracaminte si accesorii", sub: ["Haine barbati", "Haine femei", "Pantofi", "Genti si portofele"] },
    { name: "Casa si gradina", sub: ["Mobila", "Electrocasnice", "Decoratiuni"] },
    { name: "Sport, timp liber, arta", sub: ["Biciclete", "Fitness", "Gaming", "Muzica"] },
    { name: "Copii si bebelusi", sub: ["Jucarii", "Imbracaminte copii", "Carucioare"] },
  ],
  vinted: [
    { name: "Femei", sub: ["Bluze si topuri", "Pantaloni", "Rochii", "Geci", "Pantofi", "Genti"] },
    { name: "Barbati", sub: ["Tricouri", "Pantaloni", "Hanorace", "Incaltaminte"] },
    { name: "Copii", sub: ["Haine fete", "Haine baieti", "Jucarii", "Carti"] },
    { name: "Electrocasnice si electronice", sub: ["Telefoane", "Laptopuri", "Tablete", "Accesorii"] },
  ],
  facebook: [
    { name: "Electronica", sub: ["Telefoane", "Computere si laptopuri", "Tablete", "TV si video"] },
    { name: "Mobilier si articole de interior", sub: ["Canapele", "Paturi", "Birouri"] },
    { name: "Articole sportive", sub: ["Biciclete", "Echipament fitness"] },
    { name: "Haine si accesorii", sub: ["Femei", "Barbati", "Copii"] },
  ],
  lajumate: [
    { name: "Electronice", sub: ["Telefoane", "Laptopuri", "Tablete", "Audio-video"] },
    { name: "Casa si gospodarie", sub: ["Mobila", "Electrocasnice", "Decoratiuni"] },
    { name: "Moda", sub: ["Haine", "Incaltaminte", "Accesorii"] },
  ],
  publi24: [
    { name: "Electronice si IT", sub: ["Telefoane", "Laptopuri", "Componente PC"] },
    { name: "Casa si gradina", sub: ["Mobila", "Electrocasnice"] },
    { name: "Moda", sub: ["Haine", "Incaltaminte"] },
  ],
  okazii: [
    { name: "Electronice", sub: ["Telefoane", "Laptopuri", "Tablete", "Smartwatch"] },
    { name: "Casa si gradina", sub: ["Mobila", "Electrocasnice mari", "Electrocasnice mici"] },
    { name: "Moda", sub: ["Imbracaminte", "Incaltaminte", "Genti"] },
    { name: "Jocuri si console", sub: ["Console", "Jocuri PC", "Accesorii gaming"] },
  ],
  kleinanzeigen: [
    { name: "Elektronik (161)", sub: ["Smartphones (163)", "Laptops (228)", "Tablets (164)", "Kopfhörer (218)"] },
    { name: "Kleidung (11)", sub: ["Damen (12)", "Herren (13)", "Kinder (55)"] },
    { name: "Haus und Garten (80)", sub: ["Möbel (83)", "Haushaltsgeräte (227)"] },
  ],
};

export const CONDITION_BY_PLATFORM = {
  olx: ["Nou", "Folosit"],
  vinted: ["Nou cu eticheta", "Nou fara eticheta", "Foarte bun", "Bun", "Satisfacator"],
  facebook: ["Nou", "Ca nou", "Bun", "Acceptabil", "Defect"],
  lajumate: ["Nou", "Folosit"],
  publi24: ["Nou", "Folosit"],
  okazii: ["Nou", "Folosit"],
  kleinanzeigen: ["Neu", "Gebraucht"],
};

export const FACEBOOK_DISTANCES = [10, 20, 40, 80];
export const KLEIN_RADIUS = [10, 25, 50, 100, 200];
export const KLEIN_OFFER_TYPES = ["Verkaufen", "Verschenken"];

export const JUDETE = [
  "Alba", "Arad", "Arges", "Bacau", "Bihor", "Bistrita-Nasaud", "Botosani", "Braila",
  "Brasov", "Bucuresti", "Buzau", "Calarasi", "Caras-Severin", "Cluj", "Constanta",
  "Covasna", "Dambovita", "Dolj", "Galati", "Giurgiu", "Gorj", "Harghita", "Hunedoara",
  "Ialomita", "Iasi", "Ilfov", "Maramures", "Mehedinti", "Mures", "Neamt", "Olt",
  "Prahova", "Salaj", "Satu Mare", "Sibiu", "Suceava", "Teleorman", "Timis", "Tulcea",
  "Valcea", "Vaslui", "Vrancea",
];

export const platformLabel = (value) =>
  PLATFORM_LONG_LABEL[value] || MARKETPLACE_PLATFORMS.find((p) => p.value === value)?.label || value;
