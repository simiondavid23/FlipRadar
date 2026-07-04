"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { radarAPI } from "@/lib/api";
import DeleteKeywordModal from "@/components/DeleteKeywordModal";
import {
  Target, Plus, Pencil, Trash2, X, Save, ToggleLeft, ToggleRight, TrendingUp
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend
} from "recharts";

const PLATFORM_OPTIONS = [
  { value: "olx", label: "OLX" },
  { value: "vinted", label: "Vinted" },
  { value: "okazii", label: "Okazii" },
  { value: "facebook", label: "Facebook" },
  { value: "lajumate", label: "Lajumate" },
  { value: "publi24", label: "Publi24" },
  { value: "autovit", label: "Autovit" },
  { value: "mobilede", label: "Mobile.de" },
];

const CAR_FUEL_OPTIONS = [
  { value: "", label: "Orice" },
  { value: "benzina", label: "Benzină" },
  { value: "diesel", label: "Diesel" },
  { value: "hibrid", label: "Hibrid" },
  { value: "electric", label: "Electric" },
  { value: "gpl", label: "GPL" },
  { value: "gnc", label: "GNC" },
];

const CAR_BODY_OPTIONS = [
  { value: "", label: "Orice" },
  { value: "sedan", label: "Berlină" },
  { value: "suv", label: "SUV" },
  { value: "break", label: "Break" },
  { value: "hatchback", label: "Hatchback" },
  { value: "coupe", label: "Coupe" },
  { value: "cabrio", label: "Cabrio" },
  { value: "van", label: "Van" },
  { value: "pickup", label: "Pickup" },
];

const CAR_GEARBOX_OPTIONS = [
  { value: "", label: "Orice" },
  { value: "manuala", label: "Manuală" },
  { value: "automata", label: "Automată" },
];

const EMPTY_CAR_FILTERS = {
  marca: "", model: "",
  an_de_la: "", an_pana_la: "",
  km_maxim: "",
  combustibil: "", caroserie: "", cutie_viteze: "",
};

const CONDITION_OPTIONS = [
  { value: "all", label: "Toate" },
  { value: "new", label: "Nou" },
  { value: "used", label: "Second hand" },
];

const POLL_OPTIONS = [5, 10, 15, 30];

const FALLBACK_CATEGORIES = [
  "Telefoane", "Tablete", "Laptopuri", "Electronice",
  "Îmbrăcăminte", "Încălțăminte", "Jocuri", "Cărți",
  "Sport", "Casă și grădină", "Auto", "Altele",
];

const EMPTY_FORM = {
  name: "",
  max_price: "",
  min_price: "",
  resale_price: "",
  category: "",
  exclude_words: [],
  platforms: ["olx", "vinted", "okazii"],
  poll_interval_minutes: 5,
  judet: "",
  oras: "",
  condition: "all",
  is_active: true,
  min_margin_pct: 10.0,
  notify_email: true,
  notify_discord: true,
  use_active_hours: false,
  active_hours_start: 8,
  active_hours_end: 22,
  car_filters: { ...EMPTY_CAR_FILTERS },
};

function feeCeiling(resale, platform) {
  const r = parseFloat(resale) || 0;
  const ship = 20;
  if (platform === "okazii") return Math.max(0, r * 0.92 - ship);
  return Math.max(0, r - ship);
}

// Parseaza exclude_words (array sau string) intr-un array de chip-uri.
function parseExcludeWords(raw) {
  if (Array.isArray(raw)) return raw.filter(Boolean);
  if (typeof raw === "string" && raw.trim()) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed.filter(Boolean);
    } catch {
      // nu e JSON — cade pe split dupa virgula
    }
    return raw.split(",").map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

// ── Wizard marketplace (alerte keyword) — NU pentru auto sau imobiliare ──────────
const WIZARD_PLATFORMS = [
  { value: "olx", label: "OLX.ro" },
  { value: "vinted", label: "Vinted.ro" },
  { value: "facebook", label: "Facebook Marketplace" },
  { value: "lajumate", label: "LaJumate.ro" },
  { value: "publi24", label: "Publi24.ro" },
  { value: "okazii", label: "Okazii.ro" },
  { value: "kleinanzeigen", label: "eBay Kleinanzeigen" },
];

const MARKETPLACE_CATEGORIES = {
  olx: [
    {
      name: "Electronice si electrocasnice",
      sub: [
        "Telefoane", "Electrocasnice", "Tablete - eReadere", "TV",
        "Videoproiectoare & Accesorii", "Retelistica & Servere",
        "Piese telefoane & tablete", "Laptop-Calculator-Gaming",
        "Ingrijire Personala", "Periferice & Accesorii Laptop-PC-Gaming",
        "Imprimante, scannere", "Home Cinema & Audio",
        "Gadgets, Wearables & Camere foto-video", "Drone & accesorii",
        "Componente Laptop-PC", "Casti Audio",
        "Casa inteligenta - Smarthome", "Audio Hi Fi & Profesionale",
        "Aparate medicale & Wellness", "Accesorii telefoane & tablete",
      ],
    },
    {
      name: "Moda si frumusete",
      sub: [
        "Haine dama", "Incaltaminte dama", "Incaltaminte barbati", "Haine barbati",
        "Accesorii", "Ceasuri", "Lenjerie si costume de baie dama",
        "Haine pentru gravide", "Lenjerie si costume de inot barbati",
        "Palarii, sepci si bandane", "Haine pentru nunta", "Sanatate si frumusete",
        "Alte accesorii de moda si frumusete", "Cadouri",
      ],
    },
    {
      name: "Piese auto",
      sub: [
        "Roti - Jante - Anvelope", "Consumabile - accesorii",
        "Caroserie - Interior", "Mecanica - electrica",
        "Alte piese", "Alte Vehicule", "Vehicule pentru dezmembrare",
      ],
    },
    {
      name: "Casa si gradina",
      sub: [
        "Articole menaj", "Constructii", "Decoratiuni pentru interior",
        "Finisaj interior", "Gradina",
        "Hale metalice, structuri metalice si containere",
        "Iluminat", "Instalatii electrice", "Instalatii sanitare",
        "Instalatii termice", "Mobila", "Scule, unelte, feronerie",
      ],
    },
    {
      name: "Mama si copilul",
      sub: [
        "Haine - Incaltaminte copii si gravide", "La plimbare",
        "Jocuri - Jucarii", "Camera copilului",
        "Alimentatie - Ingrijire", "Articole scolare - papetarie",
        "Alte produse copii",
      ],
    },
    {
      name: "Sport, timp liber, arta",
      sub: [
        "Airsoft", "Alergare", "Alpinism, escalada", "Baschet", "Baseball",
        "Biliard", "Box", "Biciclete - Fitness - Suplimente", "Camping",
        "Dans, gimnastica", "Drumetie", "Echitatie", "Fotbal", "Genti, trolere",
        "Golf", "Karate - Judo", "Moto, enduro, atv", "Parapanta", "Pescuit",
        "Sporturi de apa", "Sporturi de iarna", "Tenis", "Tir cu arcul",
        "Trambuline", "Trotinete, role, skateboard", "Vanatoare", "Volei",
        "Echipamente sportive si de turism", "Arta - Obiecte de colectie",
        "Carti - Muzica - Filme", "Evenimente - Divertisment",
      ],
    },
    {
      name: "Animale de companie",
      sub: [
        "Caini", "Pisici",
        "Mancare si gustari pentru animale de companie",
        "Accesorii pentru animale de companie",
        "Servicii pentru animale de companie",
        "Adoptii", "Alte animale de companie",
      ],
    },
    {
      name: "Agro si industrie",
      sub: [
        "Utilaje agricole si industriale", "Produse piata - alimentatie",
        "Cereale - plante - pomi", "Animale domestice si pasari",
        "Echipamente si articole zootehnie",
      ],
    },
    {
      name: "Servicii",
      sub: [
        "Servicii Auto - Transport", "Meseriasi - Constructori",
        "Reparatii electrocasnice, electronice si telefoane", "Evenimente",
        "Cursuri - Meditatii",
        "Servicii specializate si servicii pentru afaceri",
        "Servicii de infrumusetare", "Servicii de curatenie",
        "Servicii diverse",
        "Servicii medicale - Servicii de ingrijire - Croitorie",
      ],
    },
    {
      name: "Echipamente profesionale si vanzare companii",
      sub: [
        "Echipamente pentru magazine si birouri",
        "Echipamente profesionale de curatenie",
        "Firme si licente de vanzare", "Horeca",
        "Echipamente pentru reparatii auto si spalatorii auto",
        "Echipamente pentru evenimente",
        "Echipamente pentru industria textila",
        "Echipamente de lucru si protectie",
        "Echipamente profesionale de constructii",
        "Alte echipamente profesionale",
      ],
    },
    {
      name: "Cazare - Turism",
      sub: ["Cazare - Turism", "Cazare muncitori", "Sejururi si oferte de vacanta"],
    },
    {
      name: "Inchiriere bunuri si vehicule",
      sub: [
        "Inchiriere Vehicule", "Inchiriere Echipament de Constructii",
        "Inchiriere Materiale pentru Evenimente",
        "Inchiriere Electronice & Jocuri", "Inchiriere Articole Sport",
        "Inchiriere Articole Moda & Copii", "Inchiriere Alte Articole",
      ],
    },
  ],
  vinted: [
    {
      tab: "Femei",
      categories: [
        { name: "Haine", sub: ["Pulovere","Rochii","Fustă-pantaloni scurtă","Blugi","Pantaloni scurți și pantaloni trei sferturi","Costume de baie","Haine maternitate","Costume și ținute speciale","Îmbrăcăminte de exterior","Costume și blazere","Fuste","Topuri și tricouri","Pantaloni și colanți","Salopete lungi și scurte","Lenjerie intimă și pijamale","Îmbrăcăminte pentru sport","Alte articole de îmbrăcăminte"] },
        { name: "Pantofi", sub: ["Pantofi tip boat shoe, loaferi și mocasini","Saboți","Flip-flops și șlapi","Pantofi cu șiret","Sandale","Încălțăminte sport","Balerini","Cizme și ghete","Espadrile","Pantofi cu toc","Pantofi Mary Jane și T-bar","Papuci de casă","Pantofi sport"] },
        { name: "Genți", sub: ["Genți plajă","Genți bucket","Plicuri","Genți sport","Genți hobo","Genți de călătorie și valize","Genți tip poștas","Sacoșe","Poșete de mână","Rucsacuri","Serviete","Borsete","Saci protecție haine","Genți de mână","Genți și saci de voiaj","Genți pentru cosmetice","Genți de umăr","Poșete și portofele"] },
        { name: "Accesorii", sub: ["Curele","Accesorii pentru păr","Pălării și șepci","Brelocuri","Ochelari de soare","Ceasuri","Bandane și panglici","Mănuși","Batiste","Bijuterii","Fulare și eșarfe","Umbrele","Alte accesorii"] },
        { name: "Frumusețe", sub: ["Parfum","Instrumente pentru înfrumusețare","Îngrijirea unghiilor","Îngrijirea părului","Machiaj","Îngrijirea tenului","Îngrijirea mâinilor","Îngrijirea corpului","Alte articole de frumusețe"] },
      ]
    },
    {
      tab: "Bărbați",
      categories: [
        { name: "Haine", sub: ["Îmbrăcăminte de exterior","Costume și blazere","Pantaloni","Șosete și lenjerie intimă","Costume de baie","Costume și ținute speciale","Blugi","Topuri și tricouri","Pulovere","Pantaloni scurți","Haine de dormit","Îmbrăcăminte pentru sport","Alte articole de îmbrăcăminte"] },
        { name: "Pantofi", sub: ["Cizme și ghete","Espadrile","Pantofi eleganți","Papuci de casă","Pantofi sport","Pantofi tip boat shoe, loaferi și mocasini","Saboți și papuci","Flip-flops și șlapi","Sandale","Încălțăminte sport"] },
        { name: "Accesorii", sub: ["Bandane și eșarfe de păr","Bretele","Batiste","Bijuterii","Fulare și eșarfe","Cravate și papioane","Genți și rucsacuri","Curele","Mănuși","Pălării și șepci","Batiste buzunar","Ochelari de soare","Ceasuri","Altele"] },
        { name: "Îngrijire", sub: ["Instrumente și accesorii","Îngrijirea corpului","Aftershave și apă de colonie","Seturi de îngrijire","Îngrijirea tenului","Îngrijirea părului","Îngrijirea mâinilor și a unghiilor","Machiaj","Alte articole de îngrijire"] },
      ]
    },
    {
      tab: "Designer",
      categories: [
        { name: "Designer femei", sub: ["Pantofi de designer","Îmbrăcăminte de designer","Genți de designer","Accesorii de designer"] },
        { name: "Designer bărbați", sub: ["Accesorii de designer","Pantofi de designer","Îmbrăcăminte de designer"] },
      ]
    },
    {
      tab: "Copii",
      categories: [
        { name: "Îmbrăcăminte pentru fete", sub: ["Pantofi","Pulovere și hanorace cu glugă","Rochii","Pantaloni și pantaloni scurți","Accesorii","Lenjerie intimă și șosete","Îmbrăcăminte sportivă","Îmbrăcăminte pentru gemeni","Ținute de ocazie","Îmbrăcăminte pentru bebe fată","Îmbrăcăminte de exterior","Topuri și tricouri","Fuste","Genți și rucsacuri","Costume de baie","Pijamale","Pachete îmbrăcăminte","Ținute și costume de carnaval","Alte articole de îmbrăcăminte pentru fete"] },
        { name: "Îmbrăcăminte pentru băieți", sub: ["Pantofi","Pulovere și hanorace cu glugă","Pantaloni și salopete","Accesorii","Lenjerie intimă și șosete","Îmbrăcăminte sportivă","Îmbrăcăminte pentru gemeni","Ținute de ocazie","Îmbrăcăminte pentru bebe băiat","Îmbrăcăminte de exterior","Topuri și tricouri","Genți și rucsacuri","Costume de baie","Pijamale","Pachete îmbrăcăminte","Ținute și costume de carnaval","Alte haine pentru băieți"] },
        { name: "Jucării", sub: ["Arte și meșteșuguri","Cuburi și jucării de construit","Costumează-te și intră în rol","Jucării electronice","Noutăți și jucării fidget","Jucării moi și animale de pluș","Figurine și accesorii","Activități și jucării pentru copii","Păpuși și accesorii","Jucării educative","Jucării muzicale și instrumente de jucărie","Jucării pentru exterior și sportive","Mașini, trenuri și alte vehicule de jucărie"] },
        { name: "Cărucioare, landouri și scaune auto", sub: ["Cărucioare","Scaune auto","Accesorii scaune auto","Sisteme de purtare și wrap-uri pentru bebeluși","Accesorii Buggy","Înălțătoare"] },
        { name: "Mobilier și decorațiuni", sub: ["Saltele și covoare de joacă","Șezlonguri și cuiburi","Mobilier pentru camera copilului","Scaune","Rafturi","Șifoniere","Saltele pentru copii","Țarcuri de joacă","Decorațiuni și suveniruri","Covoare și carpete","Mobilier de joacă","Mese și birouri"] },
        { name: "Îmbăiere și înfășare", sub: ["Baie","Scutece","Olițe","Scaune cu trepte","Genți pentru înfășat","Saltele pentru schimbat și huse","Depozitarea și eliminarea scutecelor","Îngrijirea pielii și igienă"] },
        { name: "Echipamente de protecție și siguranță pentru copii", sub: ["Accesorii de protecție pentru copii","Hamuri și centuri de siguranță","Porți și protecții pentru copii","Protecție fonică"] },
        { name: "Sănătate și sarcină", sub: ["Aspiratoare nazale","Perne pentru sarcină","Cântare","Umidificatoare","Îngrijirea postpartum","Centuri de susținere pentru sarcină","Termometre"] },
        { name: "Rechizite școlare", sub: ["Ghiozdane","Cutii și pungi pentru prânz","Rechizite școlare"] },
      ]
    },
    {
      tab: "Casă",
      categories: [
        { name: "Aparate electrocasnice mici", sub: ["Aparate pentru cafea, ceai și espresso","Blendere, mixere și procesoare de alimente","Friteuze","Plite","Dozatoare pentru apă și suc","Accesorii pentru electrocasnice mici de bucătărie","Ceainice","Prăjitoare de pâine","Microunde","Grătare și grătare electrice","Storcătoare","Aparate specializate","Piese pentru electrocasnice mici de bucătărie"] },
        { name: "Ustensile de gătit și de copt", sub: ["Tigăi","Tăvi de cuptor și prăjit","Ustensile de gătit și de copt speciale","Accesorii pentru vase de gătit și de copt","Oale","Tavă de copt","Forme de copt","Ustensile pentru gătit și copt"] },
        { name: "Ustensile de bucătărie", sub: ["Ustensile de gătit","Căni și linguri de măsurat","Boluri de amestecare","Depozitarea alimentelor","Unelte de bucătărie speciale","Tocătoare","Cântar de bucătărie","Termometre alimentare","Sită, strecurătoare","Ustensile pentru bar"] },
        { name: "Articole de masă", sub: ["Veselă","Tacâmuri","Pahare"] },
        { name: "Îngrijirea gospodăriei", sub: ["Fiare de călcat și îngrijire îmbrăcăminte","Încălzire, răcire și aerisire","Aspirare și curățare"] },
        { name: "Textile", sub: ["Pături","Perne decorative","Covoare și covorașe","Tapiserii","Lenjerie de pat","Perdele și jaluzele","Huse","Fețe de masă","Prosoape"] },
        { name: "Accesorii pentru casă", sub: ["Ceasuri","Accesorii decorative","Accesorii pentru șemineu","Rafturi de prezentare","Oglinzi","Vaze","Lumânări și parfumuri pentru casă","Sculpturi și figurine","Plante și flori artificiale","Iluminat","Rame foto și imagini","Depozitare și organizare","Decorațiune de perete"] },
        { name: "Consumabile de birou", sub: ["Caiete și blocuri de scris","Semne de carte","Accesorii pentru birou","Consumabile pentru scris","Bandă adezivă, cleme și elemente de fixare","Materiale pentru prezentări","Seifuri","Planificatoare și agende personale","Penare","Calculatoare","Organizatoare de documente","Instrumente pentru desen tehnic","Capsatoare și perforatoare","Aparate electronice de birou"] },
        { name: "Festivități și sărbători", sub: ["Cărți poștale și plicuri","Decor de sărbători","Decorațiuni de masă","Coronițe","Bannere, steaguri și fanioane","Hârtie și pungi de cadouri","Decorațiuni de petrecere","Decorațiuni pentru copaci"] },
        { name: "Unelte și DIY", sub: ["Unelte manuale","Unelte și accesorii pentru vopsit","Echipament pentru electricieni","Accesorii pentru unelte","Transport și depozitare unelte","Feronerie","Unelte electrice","Instrumente de măsurare","Unelte instalații sanitare","Unelte de zidărie","Echipament de protecție","Echipamente pentru atelier și șantier","Casă inteligentă și securitate"] },
        { name: "Exterior și grădină", sub: ["Accesorii pentru unelte electrice de exterior","Ghivece, jardiniere și accesorii","Decor pentru exterior și grădină","Spa-uri, piscine și echipamente","Unelte pentru îndepărtarea zăpezii","Unelte electrice pentru exterior","Unelte de mână pentru exterior","Echipament de udare","Ustensile pentru grătar și gătit în aer liber","Instrumente meteorologice"] },
        { name: "Animale", sub: ["Pisici","Pești","Reptile","Câini","Animale de companie mici","Păsări"] },
      ]
    },
    {
      tab: "Electronice",
      categories: [
        { name: "Jocuri video și console", sub: ["Jocuri","Căști pentru jocuri","Realitate virtuală","Console","Controlere","Simulatoare","Accesorii"] },
        { name: "Calculatoare și accesorii", sub: ["Calculatoare desktop","Blank media","Accesorii pentru laptop","Tastaturi și accesorii","Mouse pad-uri","Difuzoare pentru computer","Camere web","Imprimante și accesorii","Plăcuțe tactile și stylus","Laptopuri","Piese și componente de calculator","Accesorii pentru computere","Docking stations și hub-uri USB","Mouse-uri","Monitoare și accesorii","Microfoane de calculator","Dispozitive de rețea","Scanere și accesorii"] },
        { name: "Telefoane mobile și comunicare", sub: ["Piese și accesorii pentru telefoane mobile","Faxuri","Telefoane mobile demo","Telefoane mobile","Telefoane fixe","Comunicații radio"] },
        { name: "Audio, căști și hi-fi", sub: ["Playere muzicale portabile","Boxe portabile","Sisteme audio pentru acasă","Piese audio și hi-fi","Căști și earbuds","Radiouri portabile","Difuzoare inteligente","Accesorii pentru dispozitive audio"] },
        { name: "Camere foto și accesorii", sub: ["Obiective","Carduri de memorie","Stabilizatoare și suporturi","Echipament de studio","Accesorii","Alte echipamente fotografice","Camere foto","Blițuri","Trepieduri și monopieduri","Echipament pentru camera obscură","Drone cu cameră și accesorii","Piese de schimb pentru aparat foto"] },
        { name: "Tablete, e-readere și accesorii", sub: ["E-readere","PDAs","Tablete","Agende electronice","Accesorii"] },
        { name: "TV și home cinema", sub: ["Proiectoare","Antene TV","Decodificatoare video","Sisteme home cinema","DVD playere","Alte dispozitive de redare video","Televizoare","Dispozitive de streaming","Antene satelit","Receptoare de televiziune","Playere Blu-ray","Videocasetofoane","Accesorii TV și home cinema"] },
        { name: "Electronice pentru frumusețe și îngrijire personală", sub: ["Instrumente de înfrumusețare","Instrumente de masaj","Instrumente pentru îngrijirea unghiilor","Instrumente de coafură","Bărbierit și îndepărtarea părului","Îngrijire dentară și orală electrică","Cântare pentru uz personal"] },
        { name: "Portabile", sub: ["Monitoare de fitness","Inele inteligente","Carcase pentru ceasuri inteligente","Ceasuri inteligente","Ochelari inteligenți","Benzi de schimb"] },
        { name: "Alte dispozitive și accesorii", sub: ["GPS și dispozitive de navigație prin satelit","Cântare pentru bagaje","Cabluri","Baterii externe","Baterii și surse de alimentare","Imprimare și scanare 3D","Detectoare de obiecte","Adaptoare","Încărcătoare","Protecții la supratensiune și prelungitoare","Alte accesorii"] },
      ]
    },
    {
      tab: "Media și cărți",
      categories: [
        { name: "Cărți", sub: ["Non-ficțiune","Benzi desenate, manga și romane grafice","Cărți de colorat, puzzle și activități","Ficțiune","Copii și tineri adulți","Manuale și materiale de studiu"] },
        { name: "Reviste", sub: [] },
        { name: "Muzică", sub: ["CD-uri","Discuri de vinil","Casete audio","MiniDiscuri"] },
        { name: "Video", sub: ["Betamax","DVD","LaserDisc","4K Blu-ray","Blu-ray","HD DVD","VHS"] },
      ]
    },
    {
      tab: "Hobbyuri și colecții",
      categories: [
        { name: "Carduri de tranzacționare", sub: ["Pachete Booster","Pachete de cărți de joc","Poster cu carduri","Carduri de tranzacționare individuale","Cutii Booster","Loturi de carduri de tranzacționare"] },
        { name: "Jocuri de societate", sub: [] },
        { name: "Puzzle-uri", sub: [] },
        { name: "Jocuri de masă și în miniatură", sub: [] },
        { name: "Suveniruri", sub: ["Suveniruri muzicale","Alte suveniruri","Suvenir sportiv","Suveniruri de film și TV"] },
        { name: "Monede și bancnote", sub: ["Monede","Medalii și recompense","Bancnote","Loturi și seturi","Certificate de acțiuni"] },
        { name: "Timbre", sub: ["Loturi și seturi de timbre","Cataloage și ghiduri de timbre","Timbre individuale","First day covers (FDC)","Instrumente și echipamente pentru timbre"] },
        { name: "Cărți poștale", sub: [] },
        { name: "Instrumente muzicale și echipamente", sub: ["Amplificatoare și pedale","Claviaturi și sintetizatoare","Instrumente de suflat","Echipament DJ","Accesorii pentru creație muzicală","Chitare și chitare bas","Tobe și percuție","Instrumente cu coarde","Echipament de studio și sunet live","Echipament pentru karaoke"] },
        { name: "Arte și meșteșuguri", sub: ["Pictură","Caligrafie","Papercraft","Fabricarea lumânărilor","Materiale pentru artizanat","Cusut, tricotat și broderie","Desene și schițe","Mărgele și accesorii de bijuterii","Tăiere cu matrița","Sculptură și olărit","Unelte de meșteșugărit"] },
        { name: "Depozitare obiecte de colecție", sub: ["Cutii pentru păstrarea obiectelor de colecție","Suporturi de carduri cu șurub","Separatoare pentru albume și clasoare","Covoare pentru puzzle","Albume și clasoare","Huse pentru cărți de joc","Cutii pentru pachete de cărți","Folii pentru albume și clasoare","Depozitarea altor obiecte de colecție"] },
        { name: "Accesorii pentru jocuri", sub: ["Pietre și jetoane de joc","Alte accesorii pentru jocuri","Zar","Covoare pentru jocuri"] },
      ]
    },
    {
      tab: "Sporturi",
      categories: [
        { name: "Ciclism", sub: ["Căști pentru biciclete","Remorci pentru biciclete","Piese de bicicletă","Biciclete pentru copii","Accesorii și unelte pentru ciclism","Scaune pentru biciclete pentru copii"] },
        { name: "Fitness, alergare și yoga", sub: ["Alergare","Accesorii de fitness pentru acasă","Antrenament de forță","Echipament pentru yoga și pilates","Sticle de apă"] },
        { name: "Sporturi în aer liber", sub: ["Pescuit și vânătoare","Rucsacuri pentru drumeții","Alte accesorii pentru sporturi în aer liber","Corturi de camping și echipament de dormit","Torțe, faruri și lanterne","Binocluri și lunete","Mobilier de camping","Cățărare și bouldering","Arzătoare de camping și ustensile de gătit","Răcitoare","Busole","Sisteme și pachete de hidratare","Bețe de trekking"] },
        { name: "Sporturi nautice", sub: ["Înot","Costume, mănuși și ghete de neopren","Accesorii pentru sporturi nautice","Dispozitive personale de plutire","Plute gonflabile","Plăci de paddleboarding","Caiace","Kiteboarduri","Plăci de wakeboard","Căști pentru sporturi nautice","Colac remorcabil","Schiuri de apă","Skimboards"] },
        { name: "Sporturi de echipă", sub: ["Fotbal","Alte echipamente pentru sporturi de echipă","Baschet","Volei","Echipament de antrenament și de arbitraj","Handball","Fotbal american","Baseball și softball","Rugby","Hochei de sală","Lacrosse","Hochei pe iarbă","Sporturi gaelice","Cricket","Netball"] },
        { name: "Sporturi cu rachetă", sub: ["Tenis","Tenis de masă","Padel","Badminton","Squash","Pickleball","Protecție pentru ochi în sporturile cu rachetă","Racquetball"] },
        { name: "Golf", sub: ["Mingi de golf","Crose de golf","Accesorii de golf","Echipament de antrenament pentru golf","Saci de golf","Mănuși de golf","Cărucioare de golf"] },
        { name: "Echitație", sub: ["Șei și accesorii","Veste de protecție pentru călărie","Caschete de echitație","Mănuși de echitație","Huse de mătase pentru căști de echitație"] },
        { name: "Skateboard-uri și scutere", sub: ["Scutere","Skateboarduri","Protecție pentru skateboard","Piese și accesorii pentru skateboard","Căști de skateboarding","Piese și accesorii pentru skate","Plăci de longboard"] },
        { name: "Box și arte marțiale", sub: ["Protecție corporală pentru box și arte marțiale","Mănuși de box și arte marțiale","Centuri de arte marțiale","Saci de box viteză","Protecție pentru cap pentru box și arte marțiale","Protecții pentru lovituri cu pumnul și piciorul","Fășii pentru protecția mâinilor","Saci de box grei","Alte echipamente pentru arte marțiale"] },
        { name: "Sporturi și jocuri ocazionale", sub: ["Echipament pentru darts","Mingi pentru terenul de joacă","Roundnet și spikeball","Boules & alte jocuri","Frisbee și disc golf","Biliard american și snooker","Bowling cu zece popice"] },
        { name: "Sporturi de iarnă", sub: ["Echipament pentru snowboard","Accesorii pentru patinaj artistic","Rachete de zăpadă","Ochelari de schi","Echipament de schi","Hochei pe gheață","Săniuș","Ghetre","Căști pentru sporturi de iarnă"] },
      ]
    },
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

// Optiuni de stare (condition) per platforma — afisate ca checkboxuri in Pasul 3.
const CONDITION_BY_PLATFORM = {
  olx: ["Nou", "Folosit"],
  vinted: ["Nou cu eticheta", "Nou fara eticheta", "Foarte bun", "Bun", "Satisfacator"],
  facebook: ["Nou", "Ca nou", "Bun", "Acceptabil", "Defect"],
  lajumate: ["Nou", "Folosit"],
  publi24: ["Nou", "Folosit"],
  okazii: ["Nou", "Folosit"],
  kleinanzeigen: ["Neu", "Gebraucht"],
};

const FACEBOOK_DISTANCES = [10, 20, 40, 80];
const KLEIN_RADIUS = [10, 25, 50, 100, 200];
const KLEIN_OFFER_TYPES = ["Verkaufen", "Verschenken"];

const JUDETE = [
  "Alba", "Arad", "Arges", "Bacau", "Bihor", "Bistrita-Nasaud", "Botosani", "Braila",
  "Brasov", "Bucuresti", "Buzau", "Calarasi", "Caras-Severin", "Cluj", "Constanta",
  "Covasna", "Dambovita", "Dolj", "Galati", "Giurgiu", "Gorj", "Harghita", "Hunedoara",
  "Ialomita", "Iasi", "Ilfov", "Maramures", "Mehedinti", "Mures", "Neamt", "Olt",
  "Prahova", "Salaj", "Satu Mare", "Sibiu", "Suceava", "Teleorman", "Timis", "Tulcea",
  "Valcea", "Vaslui", "Vrancea",
];

const EMPTY_WIZARD = {
  platform: "",
  keyword: "",
  vintedTab: "",
  category: "",
  subcategory: "",
  filters: {},
};

// MODULE 2k — platforme single-select pentru formularul de keyword (fără auto).
const PLATFORMS = [
  { value: "olx", label: "OLX" },
  { value: "vinted", label: "Vinted" },
  { value: "okazii", label: "Okazii" },
  { value: "facebook", label: "Facebook" },
  { value: "lajumate", label: "LaJumate" },
  { value: "publi24", label: "Publi24" },
];

export default function RadarKeywordsPage() {
  const [keywords, setKeywords] = useState([]);
  const [categories, setCategories] = useState(FALLBACK_CATEGORIES);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  // MODIFICARE 18 — modal confirmare stergere cu impact.
  const [deleteModal, setDeleteModal] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [excludeChips, setExcludeChips] = useState([]);
  const [chipInput, setChipInput] = useState("");
  const [excludeDescChips, setExcludeDescChips] = useState([]);
  const [descChipInput, setDescChipInput] = useState("");
  const [allCategories, setAllCategories] = useState({});
  const [formPlatform, setFormPlatform] = useState("");
  const [formMainCat, setFormMainCat] = useState("");
  const [formSubCat, setFormSubCat] = useState("");
  // Wizard marketplace (3 pasi) pentru adaugare keyword
  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);
  const [wizardData, setWizardData] = useState(EMPTY_WIZARD);
  const [wizardSaving, setWizardSaving] = useState(false);
  const [trendKw, setTrendKw] = useState(null);
  const [trendData, setTrendData] = useState(null);
  const [trendDays, setTrendDays] = useState(30);
  const [trendLoading, setTrendLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [kw, cat] = await Promise.all([
        radarAPI.getKeywords(),
        radarAPI.getCategories().catch(() => null),
      ]);
      setKeywords(kw.data || []);
      setAllCategories(cat?.data || {});
    } catch (e) {
      console.error("[RadarKeywords]", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Sincronizeaza chip-urile de excludere inapoi in form (ca JSON string).
  useEffect(() => {
    setForm((prev) => ({ ...prev, exclude_words: JSON.stringify(excludeChips) }));
  }, [excludeChips]);

  useEffect(() => {
    setForm((prev) => ({ ...prev, exclude_description_words: JSON.stringify(excludeDescChips) }));
  }, [excludeDescChips]);

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setExcludeChips([]);
    setChipInput("");
    setExcludeDescChips([]);
    setDescChipInput("");
    setFormPlatform("");
    setFormMainCat("");
    setFormSubCat("");
    setShowForm(true);
  };

  // ── Wizard marketplace ────────────────────────────────────────────────────────
  const openWizard = () => {
    setWizardData(EMPTY_WIZARD);
    setWizardStep(1);
    setShowWizard(true);
  };

  const closeWizard = () => {
    setShowWizard(false);
    setWizardStep(1);
    setWizardData(EMPTY_WIZARD);
  };

  const setWizardFilter = (key, value) => {
    setWizardData((prev) => ({ ...prev, filters: { ...prev.filters, [key]: value } }));
  };

  const toggleWizardCondition = (value) => {
    setWizardData((prev) => {
      const cur = Array.isArray(prev.filters.condition) ? prev.filters.condition : [];
      const next = cur.includes(value) ? cur.filter((c) => c !== value) : [...cur, value];
      return { ...prev, filters: { ...prev.filters, condition: next } };
    });
  };

  const wizardCanNext = () => {
    if (wizardStep === 1) return !!wizardData.platform;
    if (wizardStep === 2) return !!wizardData.keyword.trim();
    return true;
  };

  const wizardSubmit = async () => {
    const f = wizardData.filters || {};
    const priceMin = f.price_min !== "" && f.price_min != null ? parseFloat(f.price_min) : null;
    const priceMax = f.price_max !== "" && f.price_max != null ? parseFloat(f.price_max) : null;

    // Curata filtrele goale pentru config-ul stocat in JSON
    const cleanFilters = {};
    for (const [k, v] of Object.entries(f)) {
      if (v == null || v === "") continue;
      if (Array.isArray(v) && v.length === 0) continue;
      if ((k === "price_min" || k === "price_max") && Number.isFinite(parseFloat(v))) {
        cleanFilters[k] = parseFloat(v);
      } else {
        cleanFilters[k] = v;
      }
    }

    // Vinted: convenția de filtrare stochează categoria ca "Tab > Categorie".
    const effectiveCategory =
      wizardData.platform === "vinted" && wizardData.vintedTab && wizardData.category
        ? `${wizardData.vintedTab} > ${wizardData.category}`
        : (wizardData.category || null);

    const payload = {
      name: wizardData.keyword.trim(),
      // Backend cere max_price si resale_price > 0; pentru o alerta simpla folosim
      // pretul maxim ca referinta (resale = max) si marja tinta 0.
      max_price: priceMax && priceMax > 0 ? priceMax : 1000000,
      min_price: priceMin && priceMin > 0 ? priceMin : null,
      resale_price: priceMax && priceMax > 0 ? priceMax : 1000000,
      category: effectiveCategory,
      platforms: [wizardData.platform],
      condition: "all",
      judet: f.location_county || null,
      oras: f.location_city || null,
      min_margin_pct: 0,
      marketplace_config: {
        platform: wizardData.platform,
        keyword: wizardData.keyword.trim(),
        vintedTab: wizardData.vintedTab || null,
        category: effectiveCategory,
        subcategory: wizardData.subcategory || null,
        filters: cleanFilters,
      },
    };

    if (!payload.name) {
      alert("Introdu un keyword pentru monitorizare.");
      return;
    }
    setWizardSaving(true);
    try {
      await radarAPI.createKeyword(payload);
      closeWizard();
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvarea keyword-ului.");
    } finally {
      setWizardSaving(false);
    }
  };

  const openEdit = (kw) => {
    setEditingId(kw.id);
    setForm({
      name: kw.name,
      max_price: kw.max_price,
      min_price: kw.min_price ?? "",
      resale_price: kw.resale_price,
      category: kw.category || "",
      exclude_words: kw.exclude_words || [],
      platforms: kw.platforms || [],
      poll_interval_minutes: kw.poll_interval_minutes,
      judet: kw.judet || "",
      oras: kw.oras || "",
      condition: kw.condition,
      is_active: kw.is_active,
      min_margin_pct: kw.min_margin_pct,
      notify_email: kw.notify_email !== false,
      notify_discord: kw.notify_discord !== false,
      use_active_hours: kw.active_hours_start != null && kw.active_hours_end != null,
      active_hours_start: kw.active_hours_start ?? 8,
      active_hours_end: kw.active_hours_end ?? 22,
      car_filters: { ...EMPTY_CAR_FILTERS, ...(kw.car_filters || {}) },
    });
    setExcludeChips(parseExcludeWords(kw.exclude_words));
    setChipInput("");
    const descWords = (() => {
      const raw = kw.exclude_description_words;
      if (Array.isArray(raw)) return raw;
      try { return JSON.parse(raw || "[]"); } catch { return []; }
    })();
    setExcludeDescChips(Array.isArray(descWords) ? descWords : []);
    setDescChipInput("");
    // MODULE 2k — initializeaza platforma + categoria (main/sub) din keyword
    const platformVal = kw.platform
      || (Array.isArray(kw.platforms) ? kw.platforms[0] : (() => { try { return JSON.parse(kw.platforms || "[]")[0]; } catch { return ""; } })())
      || "";
    setFormPlatform(platformVal);
    const cats = allCategories[platformVal] || [];
    let foundMain = "", foundSub = "";
    for (const cat of cats) {
      if (cat.value != null && cat.value === kw.category) { foundMain = catKey(cat); break; }
      let matched = false;
      for (const sub of (cat.subcategories || [])) {
        if (sub.value === kw.category) { foundMain = catKey(cat); foundSub = sub.value; matched = true; break; }
      }
      if (matched) break;
    }
    setFormMainCat(foundMain || "");
    setFormSubCat(foundSub || "");
    setShowForm(true);
  };

  // Cheie de optiune pentru dropdown-ul de categorie principala. Unele platforme
  // (Okazii) au departamente cu value=null (nu-s filtre reale pe site) — le dam o
  // cheie sintetica stabila ca sa fie selectabile in <select>; valoarea reala
  // (null) se rezolva inapoi la submit. Categoriile cu value real se cheie pe ele.
  const catKey = (c) => (c.value != null ? c.value : `__d:${c.label}`);

  const togglePlatform = (p) => {
    setForm((prev) => ({
      ...prev,
      platforms: prev.platforms.includes(p)
        ? prev.platforms.filter((x) => x !== p)
        : [...prev.platforms, p],
    }));
  };

  const submit = async (e) => {
    e?.preventDefault();
    const minPriceVal = form.min_price === "" || form.min_price === null ? null : parseFloat(form.min_price);
    // Compactează filtrele auto: trimite null dacă niciun câmp nu e completat.
    const cfRaw = form.car_filters || {};
    const cfCompact = {};
    for (const [k, v] of Object.entries(cfRaw)) {
      if (v === null || v === undefined) continue;
      if (typeof v === "string" && v.trim() === "") continue;
      if (["an_de_la", "an_pana_la", "km_maxim"].includes(k)) {
        const n = parseInt(v);
        if (!Number.isNaN(n) && n > 0) cfCompact[k] = n;
      } else {
        cfCompact[k] = String(v).trim();
      }
    }
    const carFiltersForSend = Object.keys(cfCompact).length > 0 ? cfCompact : null;
    // Categoria principala poate avea o cheie sintetica (__d:...) pentru
    // departamentele Okazii cu value=null. Rezolvam valoarea reala inainte de submit
    // ca sa NU trimitem cheia sintetica la backend (dept singur => category null).
    const platCatsForSubmit = allCategories[formPlatform] || [];
    const mainCatObjForSubmit = platCatsForSubmit.find((c) => catKey(c) === formMainCat);
    const resolvedMainCatVal = mainCatObjForSubmit ? mainCatObjForSubmit.value : null;
    const payload = {
      name: form.name.trim(),
      max_price: parseFloat(form.max_price),
      min_price: minPriceVal,
      resale_price: parseFloat(form.resale_price),
      category: formSubCat || resolvedMainCatVal || null,
      platform: formPlatform,
      exclude_words: excludeChips,
      exclude_description_words: excludeDescChips,
      platforms: formPlatform ? [formPlatform] : [],
      poll_interval_minutes: parseInt(form.poll_interval_minutes) || 5,
      judet: form.judet || null,
      oras: form.oras || null,
      condition: form.condition,
      is_active: form.is_active,
      min_margin_pct: parseFloat(form.min_margin_pct) || 10.0,
      notify_email: !!form.notify_email,
      notify_discord: !!form.notify_discord,
      active_hours_start: form.use_active_hours ? (form.active_hours_start ?? 8) : null,
      active_hours_end: form.use_active_hours ? (form.active_hours_end ?? 22) : null,
      car_filters: carFiltersForSend,
    };
    if (!payload.name || !payload.max_price || !payload.resale_price) {
      alert("Numele, prețul maxim și prețul de revânzare sunt obligatorii.");
      return;
    }
    if (payload.min_price !== null && payload.min_price > payload.max_price) {
      alert("Prețul minim nu poate fi mai mare decât prețul maxim.");
      return;
    }
    if (payload.platforms.length === 0) {
      alert("Selectează cel puțin o platformă.");
      return;
    }
    try {
      if (editingId) {
        await radarAPI.updateKeyword(editingId, payload);
      } else {
        await radarAPI.createKeyword(payload);
      }
      setShowForm(false);
      setExcludeChips([]);
      setChipInput("");
      setExcludeDescChips([]);
      setDescChipInput("");
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    }
  };

  // MODIFICARE 18 — deschide modalul cu impactul (nr. listinguri asociate).
  const handleDeleteClick = async (kw) => {
    let impact = { listing_count: 0, seen_count: 0 };
    try { impact = (await radarAPI.getKeywordImpact(kw.id)).data; } catch { /* fallback 0 */ }
    setDeleteModal({
      keywordId: kw.id, keywordName: kw.name,
      listingCount: impact.listing_count ?? 0, seenCount: impact.seen_count ?? 0,
    });
  };

  const performDelete = async (id) => {
    try {
      await radarAPI.deleteKeyword(id);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la ștergere.");
    }
  };

  const toggle = async (id) => {
    try {
      await radarAPI.toggleKeyword(id);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la comutare.");
    }
  };

  const bulkSet = async (matcher, isActive) => {
    try {
      for (const kw of keywords) {
        if (matcher(kw) && kw.is_active !== isActive) {
          await radarAPI.updateKeyword(kw.id, { is_active: isActive });
        }
      }
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la actualizare în masă.");
    }
  };

  const openTrend = async (kw, days = 30) => {
    setTrendKw(kw);
    setTrendDays(days);
    setTrendData(null);
    setTrendLoading(true);
    try {
      const r = await radarAPI.keywordPriceTrend(kw.id, days);
      setTrendData(r.data);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la încărcarea trendului.");
      setTrendKw(null);
    } finally {
      setTrendLoading(false);
    }
  };

  const changeTrendDays = (days) => {
    if (!trendKw) return;
    openTrend(trendKw, days);
  };

  const marginPreview = useMemo(() => {
    const mp = parseFloat(form.max_price) || 0;
    const rp = parseFloat(form.resale_price) || 0;
    if (rp <= 0) return null;
    const v = rp - mp;
    const pct = (v / rp) * 100;
    return { value: v, pct };
  }, [form.max_price, form.resale_price]);

  const inputStyle = {
    width: "100%",
    backgroundColor: "var(--bg-dark)",
    border: "1px solid var(--border-color)",
    borderRadius: "0.5rem",
    padding: "0.5rem 0.75rem",
    color: "var(--text-primary)",
    fontSize: "0.875rem",
    outline: "none",
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Target style={{ width: "22px", height: "22px", color: "#2563eb" }} />
            Keyword-uri Urmărite
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Configurează ce caută Radar-ul pe platformele active ({keywords.length} keyword-uri)
          </p>
        </div>
        <button
          onClick={openCreate}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.5rem 0.875rem",
            backgroundColor: "var(--blue-primary)",
            color: "white",
            border: "none",
            borderRadius: "0.5rem",
            fontSize: "0.8125rem",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          <Plus style={{ width: "16px", height: "16px" }} />
          Adaugă keyword
        </button>
      </div>

      {/* Acțiuni în masă */}
      <div style={{
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "0.75rem",
        padding: "0.75rem",
        marginBottom: "1rem",
        display: "flex",
        flexWrap: "wrap",
        gap: "0.5rem",
      }}>
        <button onClick={() => bulkSet(() => true, true)} style={bulkBtn}>Activează toate</button>
        <button onClick={() => bulkSet(() => true, false)} style={bulkBtn}>Dezactivează toate</button>
        <button onClick={() => bulkSet((k) => k.platforms?.includes("olx"), true)} style={bulkBtn}>Activează OLX</button>
        <button onClick={() => bulkSet((k) => k.platforms?.includes("vinted"), true)} style={bulkBtn}>Activează Vinted</button>
        <button onClick={() => bulkSet((k) => k.platforms?.includes("okazii"), true)} style={bulkBtn}>Activează Okazii</button>
      </div>

      {/* Listă keyword-uri */}
      {keywords.length === 0 ? (
        <div style={{
          textAlign: "center",
          padding: "2.5rem",
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          color: "var(--text-secondary)",
        }}>
          Nu ai keyword-uri configurate. Apasă „Adaugă keyword” ca să începi.
        </div>
      ) : (
        <div style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.75rem",
          overflow: "hidden",
        }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
              <thead>
                <tr style={{ backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)" }}>
                  <th style={th}>Keyword</th>
                  <th style={th}>Preț min</th>
                  <th style={th}>Preț max</th>
                  <th style={th}>Revânzare</th>
                  <th style={th}>Marjă țintă</th>
                  <th style={th}>Categorie</th>
                  <th style={th}>Platforme</th>
                  <th style={th}>Interval</th>
                  <th style={th}>Notificări</th>
                  <th style={th}>Status</th>
                  <th style={th}>Acțiuni</th>
                </tr>
              </thead>
              <tbody>
                {keywords.map((k) => {
                  const m = k.resale_price > 0 ? ((k.resale_price - k.max_price) / k.resale_price) * 100 : 0;
                  const excludeWords = (() => {
                    const raw = k.exclude_words;
                    if (Array.isArray(raw)) return raw;
                    try { return JSON.parse(raw || "[]"); }
                    catch { return []; }
                  })();
                  return (
                    <tr key={k.id} style={{ borderTop: "1px solid var(--border-color)" }}>
                      <td style={td}>
                        <div>{k.name}</div>
                        {k.active_hours_start !== null && k.active_hours_start !== undefined &&
                          k.active_hours_end !== null && k.active_hours_end !== undefined && (
                            <span style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.2rem",
                              fontSize: "0.7rem",
                              color: "var(--text-secondary)",
                              marginTop: "0.2rem",
                            }}>
                              🕐 {String(k.active_hours_start).padStart(2, "0")}:00
                              {" – "}
                              {String(k.active_hours_end).padStart(2, "0")}:00
                            </span>
                          )}
                        {k.marketplace_config && (() => {
                          const mc = k.marketplace_config;
                          const plat = WIZARD_PLATFORMS.find((p) => p.value === mc.platform)?.label || mc.platform;
                          const cat = [mc.category, mc.subcategory].filter(Boolean).join(" › ");
                          const ff = mc.filters || {};
                          const parts = [];
                          if (Array.isArray(ff.condition) && ff.condition.length) parts.push(ff.condition.join("/"));
                          if (ff.price_min != null || ff.price_max != null) parts.push(`${ff.price_min ?? "?"}-${ff.price_max ?? "?"} RON`);
                          if (ff.location_county) parts.push(ff.location_county);
                          if (ff.plz) parts.push(`PLZ ${ff.plz}`);
                          return (
                            <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", marginTop: "2px", maxWidth: "260px" }}>
                              <span style={{ color: "var(--blue-light)", fontWeight: 600 }}>{plat}</span>
                              {cat ? ` · ${cat}` : ""}{parts.length ? ` · ${parts.join(" · ")}` : ""}
                            </div>
                          );
                        })()}
                        {excludeWords.length > 0 && (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem", marginTop: "0.25rem" }}>
                            {excludeWords.map((word) => (
                              <span key={word} style={{
                                fontSize: "0.6875rem", padding: "0.125rem 0.4rem",
                                backgroundColor: "rgba(239,68,68,0.12)", color: "#fca5a5",
                                borderRadius: "0.25rem", display: "inline-block"
                              }}>
                                {word}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td style={td}>{k.min_price ? `${Math.round(k.min_price)} RON` : "—"}</td>
                      <td style={td}>{Math.round(k.max_price)} RON</td>
                      <td style={td}>{Math.round(k.resale_price)} RON</td>
                      <td style={{ ...td, color: m >= 25 ? "#4ade80" : m >= 10 ? "#facc15" : "#fb923c" }}>
                        {Math.round(m)}%
                      </td>
                      <td style={td} title={k.category_label || k.category || ""}>
                        <span style={{
                          display: "inline-block",
                          maxWidth: "200px",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          verticalAlign: "bottom",
                        }}>
                          {k.category_label || k.category || "—"}
                        </span>
                      </td>
                      <td style={td}>{(k.platforms || []).join(", ")}</td>
                      <td style={td}>{k.poll_interval_minutes} min</td>
                      <td style={td}>
                        <span style={{ display: "inline-flex", gap: "0.25rem", fontSize: "0.95rem" }}>
                          <span title="Email" style={{ opacity: k.notify_email ? 1 : 0.25 }}>📧</span>
                          <span title="Discord" style={{ opacity: k.notify_discord ? 1 : 0.25 }}>💬</span>
                        </span>
                      </td>
                      <td style={td}>
                        <button onClick={() => toggle(k.id)} style={{ background: "none", border: "none", cursor: "pointer", color: k.is_active ? "#4ade80" : "var(--text-muted)" }}>
                          {k.is_active ? <ToggleRight style={{ width: "22px", height: "22px" }} /> : <ToggleLeft style={{ width: "22px", height: "22px" }} />}
                        </button>
                      </td>
                      <td style={td}>
                        <div style={{ display: "flex", gap: "0.375rem" }}>
                          <button onClick={() => openTrend(k)} style={iconBtn} title="Trend preț">
                            <TrendingUp style={{ width: "14px", height: "14px" }} />
                          </button>
                          <button onClick={() => openEdit(k)} style={iconBtn} title="Editează">
                            <Pencil style={{ width: "14px", height: "14px" }} />
                          </button>
                          <button onClick={() => handleDeleteClick(k)} style={{ ...iconBtn, color: "#f87171" }} title="Șterge">
                            <Trash2 style={{ width: "14px", height: "14px" }} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Wizard marketplace (3 pasi) */}
      {showWizard && (() => {
        const wlabel = { display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" };
        const primaryBtn = { padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600 };
        const secondaryBtn = { padding: "0.5rem 1.25rem", borderRadius: "0.5rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500 };
        const f = wizardData.filters || {};
        const plat = wizardData.platform;
        const platLabel = WIZARD_PLATFORMS.find((p) => p.value === plat)?.label || "";

        const renderCondition = () => (
          <div>
            <label style={wlabel}>Stare</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
              {(CONDITION_BY_PLATFORM[plat] || []).map((c) => {
                const checked = Array.isArray(f.condition) && f.condition.includes(c);
                return (
                  <label key={c} style={{
                    display: "inline-flex", alignItems: "center", gap: "0.375rem", fontSize: "0.8125rem",
                    color: checked ? "var(--blue-light)" : "var(--text-secondary)", cursor: "pointer",
                    padding: "0.3rem 0.6rem", border: `1px solid ${checked ? "var(--blue-primary)" : "var(--border-color)"}`,
                    borderRadius: "0.5rem", backgroundColor: checked ? "var(--blue-dim)" : "transparent",
                  }}>
                    <input type="checkbox" checked={checked} onChange={() => toggleWizardCondition(c)} />
                    {c}
                  </label>
                );
              })}
            </div>
          </div>
        );

        const renderPrice = () => (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={wlabel}>Pret min (RON)</label>
              <input type="number" value={f.price_min ?? ""} onChange={(e) => setWizardFilter("price_min", e.target.value)} placeholder="ex: 500" style={inputStyle} />
            </div>
            <div>
              <label style={wlabel}>Pret max (RON)</label>
              <input type="number" value={f.price_max ?? ""} onChange={(e) => setWizardFilter("price_max", e.target.value)} placeholder="ex: 2000" style={inputStyle} />
            </div>
          </div>
        );

        const renderJudet = () => (
          <div>
            <label style={wlabel}>Judet</label>
            <select value={f.location_county || ""} onChange={(e) => setWizardFilter("location_county", e.target.value)} style={inputStyle}>
              <option value="">Toate judetele</option>
              {JUDETE.map((j) => <option key={j} value={j}>{j}</option>)}
            </select>
          </div>
        );

        return (
          <div onClick={closeWizard} style={{
            position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", zIndex: 100,
            display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "3rem 1rem", overflowY: "auto",
          }}>
            <div onClick={(e) => e.stopPropagation()} style={{
              width: "100%", maxWidth: "640px", backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-color)", borderRadius: "0.875rem", padding: "1.5rem",
            }}>
              {/* Header + pasi */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
                <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                  Adauga keyword — Pasul {wizardStep} din 3
                </h2>
                <button onClick={closeWizard} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}>
                  <X style={{ width: "20px", height: "20px" }} />
                </button>
              </div>
              <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
                {[1, 2, 3].map((s) => (
                  <div key={s} style={{ flex: 1, height: "4px", borderRadius: "2px", backgroundColor: s <= wizardStep ? "var(--blue-primary)" : "var(--border-color)" }} />
                ))}
              </div>

              {/* PAS 1 — platforma */}
              {wizardStep === 1 && (
                <div>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: 0, marginBottom: "0.875rem" }}>
                    Alege platforma pe care vrei sa monitorizezi anunturile.
                  </p>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: "0.625rem" }}>
                    {WIZARD_PLATFORMS.map((p) => {
                      const active = wizardData.platform === p.value;
                      return (
                        <button key={p.value} type="button"
                          onClick={() => setWizardData({ ...EMPTY_WIZARD, platform: p.value })}
                          style={{
                            padding: "0.875rem", borderRadius: "0.625rem", cursor: "pointer", textAlign: "left",
                            fontSize: "0.8125rem", fontWeight: 600,
                            backgroundColor: active ? "var(--blue-dim)" : "var(--bg-dark)",
                            color: active ? "var(--blue-light)" : "var(--text-primary)",
                            border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}`,
                          }}>
                          {p.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* PAS 2 — keyword + categorii */}
              {wizardStep === 2 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                  <div>
                    <label style={wlabel}>Keyword *</label>
                    <input value={wizardData.keyword} onChange={(e) => setWizardData({ ...wizardData, keyword: e.target.value })}
                      placeholder="ex: iPhone 14 Pro" style={inputStyle} autoFocus />
                  </div>
                  {plat === "vinted" ? (
                    <>
                      {/* Vinted — 3 niveluri: Tab > Categorie > Subcategorie */}
                      <div>
                        <label style={wlabel}>Tab principal</label>
                        <select value={wizardData.vintedTab}
                          onChange={(e) => setWizardData({ ...wizardData, vintedTab: e.target.value, category: "", subcategory: "" })}
                          style={inputStyle}>
                          <option value="">Alege tab-ul</option>
                          {(MARKETPLACE_CATEGORIES.vinted || []).map((t) => (
                            <option key={t.tab} value={t.tab}>{t.tab}</option>
                          ))}
                        </select>
                      </div>
                      {wizardData.vintedTab && (
                        <div>
                          <label style={wlabel}>Categorie</label>
                          <select value={wizardData.category}
                            onChange={(e) => setWizardData({ ...wizardData, category: e.target.value, subcategory: "" })}
                            style={inputStyle}>
                            <option value="">Alege categoria</option>
                            {((MARKETPLACE_CATEGORIES.vinted || []).find((t) => t.tab === wizardData.vintedTab)?.categories || []).map((c) => (
                              <option key={c.name} value={c.name}>{c.name}</option>
                            ))}
                          </select>
                        </div>
                      )}
                      {wizardData.category && (() => {
                        const vSubs = (MARKETPLACE_CATEGORIES.vinted || [])
                          .find((t) => t.tab === wizardData.vintedTab)?.categories
                          ?.find((c) => c.name === wizardData.category)?.sub || [];
                        if (vSubs.length === 0) return null;
                        return (
                          <div>
                            <label style={wlabel}>Sub-categorie</label>
                            <select value={wizardData.subcategory}
                              onChange={(e) => setWizardData({ ...wizardData, subcategory: e.target.value })}
                              style={inputStyle}>
                              <option value="">Toate sub-categoriile</option>
                              {vSubs.map((s) => <option key={s} value={s}>{s}</option>)}
                            </select>
                          </div>
                        );
                      })()}
                    </>
                  ) : (
                    <>
                      <div>
                        <label style={wlabel}>Categorie principala</label>
                        <select value={wizardData.category}
                          onChange={(e) => setWizardData({ ...wizardData, category: e.target.value, subcategory: "" })}
                          style={inputStyle}>
                          <option value="">Alege categoria</option>
                          {(MARKETPLACE_CATEGORIES[plat] || []).map((c) => (
                            <option key={c.name} value={c.name}>{c.name}</option>
                          ))}
                        </select>
                      </div>
                      {wizardData.category && (
                        <div>
                          <label style={wlabel}>Sub-categorie</label>
                          <select value={wizardData.subcategory}
                            onChange={(e) => setWizardData({ ...wizardData, subcategory: e.target.value })}
                            style={inputStyle}>
                            <option value="">Toate sub-categoriile</option>
                            {((MARKETPLACE_CATEGORIES[plat] || []).find((c) => c.name === wizardData.category)?.sub || []).map((s) => (
                              <option key={s} value={s}>{s}</option>
                            ))}
                          </select>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* PAS 3 — filtre specifice platformei */}
              {wizardStep === 3 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>
                    Filtre pentru <strong style={{ color: "var(--text-primary)" }}>{platLabel}</strong>
                  </p>

                  {plat === "olx" && (<>
                    {renderCondition()}
                    {renderPrice()}
                    {renderJudet()}
                    <div>
                      <label style={wlabel}>Oras</label>
                      <input value={f.location_city || ""} onChange={(e) => setWizardFilter("location_city", e.target.value)} placeholder="ex: Cluj-Napoca" style={inputStyle} />
                    </div>
                  </>)}

                  {plat === "vinted" && (<>
                    {renderCondition()}
                    <div>
                      <label style={wlabel}>Marime</label>
                      <input value={f.size || ""} onChange={(e) => setWizardFilter("size", e.target.value)} placeholder="ex: M, 42, 9.5" style={inputStyle} />
                    </div>
                    {renderPrice()}
                  </>)}

                  {plat === "facebook" && (<>
                    {renderCondition()}
                    {renderPrice()}
                    <div>
                      <label style={wlabel}>Locatie (oras)</label>
                      <input value={f.location_city || ""} onChange={(e) => setWizardFilter("location_city", e.target.value)} placeholder="ex: Bucuresti" style={inputStyle} />
                    </div>
                    <div>
                      <label style={wlabel}>Distanta</label>
                      <select value={f.distance_km || ""} onChange={(e) => setWizardFilter("distance_km", e.target.value)} style={inputStyle}>
                        <option value="">Oricare</option>
                        {FACEBOOK_DISTANCES.map((d) => <option key={d} value={d}>{d} km</option>)}
                      </select>
                    </div>
                  </>)}

                  {(plat === "lajumate" || plat === "publi24" || plat === "okazii") && (<>
                    {renderCondition()}
                    {renderPrice()}
                    {renderJudet()}
                  </>)}

                  {plat === "kleinanzeigen" && (<>
                    <div>
                      <label style={wlabel}>Tip oferta</label>
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        {KLEIN_OFFER_TYPES.map((t) => {
                          const active = f.offer_type === t;
                          return (
                            <button key={t} type="button" onClick={() => setWizardFilter("offer_type", t)}
                              style={{ flex: 1, padding: "0.5rem", borderRadius: "0.5rem", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600,
                                backgroundColor: active ? "var(--blue-dim)" : "var(--bg-dark)", color: active ? "var(--blue-light)" : "var(--text-primary)",
                                border: `1px solid ${active ? "var(--blue-primary)" : "var(--border-color)"}` }}>
                              {t}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    {renderCondition()}
                    <div>
                      <label style={wlabel}>PLZ (cod postal, 5 cifre)</label>
                      <input value={f.plz || ""} maxLength={5}
                        onChange={(e) => setWizardFilter("plz", e.target.value.replace(/\D/g, "").slice(0, 5))}
                        placeholder="ex: 10115" style={inputStyle} />
                    </div>
                    <div>
                      <label style={wlabel}>Raza</label>
                      <select value={f.radius_km || ""} onChange={(e) => setWizardFilter("radius_km", e.target.value)} style={inputStyle}>
                        <option value="">Oricare</option>
                        {KLEIN_RADIUS.map((r) => <option key={r} value={r}>{r} km</option>)}
                      </select>
                    </div>
                  </>)}
                </div>
              )}

              {/* Footer navigare */}
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1.5rem" }}>
                <button type="button" onClick={() => (wizardStep > 1 ? setWizardStep(wizardStep - 1) : closeWizard())} style={secondaryBtn}>
                  {wizardStep > 1 ? "Inapoi" : "Anuleaza"}
                </button>
                {wizardStep < 3 ? (
                  <button type="button" disabled={!wizardCanNext()}
                    onClick={() => wizardCanNext() && setWizardStep(wizardStep + 1)}
                    style={{ ...primaryBtn, opacity: wizardCanNext() ? 1 : 0.5, cursor: wizardCanNext() ? "pointer" : "not-allowed" }}>
                    Continua
                  </button>
                ) : (
                  <button type="button" onClick={wizardSubmit} disabled={wizardSaving}
                    style={{ ...primaryBtn, opacity: wizardSaving ? 0.7 : 1 }}>
                    {wizardSaving ? "Se salveaza..." : "Salveaza keyword"}
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* Formular modal */}
      {showForm && (
        <div
          onClick={() => setShowForm(false)}
          style={{
            position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 100, padding: "1.5rem",
          }}
        >
          <form
            onClick={(e) => e.stopPropagation()}
            onSubmit={submit}
            style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "0.875rem",
              maxWidth: "620px",
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
              padding: "1.25rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
              <h2 style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                {editingId ? "Editează keyword" : "Adaugă keyword"}
              </h2>
              <button type="button" onClick={() => setShowForm(false)} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}>
                <X style={{ width: "20px", height: "20px" }} />
              </button>
            </div>

            <div style={{ display: "grid", gap: "0.75rem" }}>
              <Field label="Platformă">
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  {PLATFORMS.map((p) => (
                    <button key={p.value} type="button"
                      onClick={() => { setFormPlatform(p.value); setFormMainCat(""); setFormSubCat(""); setForm((prev) => ({ ...prev, platforms: [p.value] })); }}
                      style={{
                        padding: "0.375rem 0.875rem", borderRadius: "0.5rem", fontSize: "0.8125rem",
                        fontWeight: formPlatform === p.value ? 600 : 400, cursor: "pointer",
                        border: formPlatform === p.value ? "2px solid #2563eb" : "1px solid var(--border-color)",
                        backgroundColor: formPlatform === p.value ? "rgba(37,99,235,0.15)" : "var(--bg-dark)",
                        color: formPlatform === p.value ? "#60a5fa" : "var(--text-secondary)",
                      }}
                    >{p.label}</button>
                  ))}
                </div>
              </Field>

              {formPlatform && (() => {
                const currentPlatformCats = allCategories[formPlatform] || [];
                const selectedMainCat = currentPlatformCats.find((c) => catKey(c) === formMainCat);
                const hasSubs = selectedMainCat?.subcategories?.length > 0;
                return (
                  <div style={{ display: "grid", gridTemplateColumns: hasSubs ? "1fr 1fr" : "1fr", gap: "0.75rem" }}>
                    <Field label="Categorie principală">
                      <select value={formMainCat} onChange={(e) => { setFormMainCat(e.target.value); setFormSubCat(""); }} style={inputStyle}>
                        <option value="">Toate categoriile</option>
                        {currentPlatformCats.map((c) => (
                          <option key={catKey(c)} value={catKey(c)}>{c.label}</option>
                        ))}
                      </select>
                    </Field>
                    {hasSubs && (
                      <Field label="Subcategorie">
                        <select value={formSubCat} onChange={(e) => setFormSubCat(e.target.value)} style={inputStyle}>
                          <option value="">Toate</option>
                          {selectedMainCat.subcategories.map((s) => (
                            <option key={s.value ?? s.label} value={s.value ?? ""}>{s.label}</option>
                          ))}
                        </select>
                      </Field>
                    )}
                  </div>
                );
              })()}

              <Field label="Keyword">
                <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="iPhone 13" style={inputStyle} required />
              </Field>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Field label="Preț maxim achiziție (RON)">
                  <input type="number" value={form.max_price} onChange={(e) => setForm({ ...form, max_price: e.target.value })} style={inputStyle} required min="0" step="any" />
                </Field>
                <Field label="Preț estimat revânzare (RON)">
                  <input type="number" value={form.resale_price} onChange={(e) => setForm({ ...form, resale_price: e.target.value })} style={inputStyle} required min="0" step="any" />
                </Field>
              </div>

              <Field label="Preț minim achiziție (RON) — opțional">
                <input
                  type="number"
                  value={form.min_price}
                  onChange={(e) => setForm({ ...form, min_price: e.target.value })}
                  placeholder="ex: 100"
                  style={inputStyle}
                  min="0"
                  step="any"
                />
                <small style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>
                  Util pentru a exclude accesorii ieftine (huse, cabluri etc.)
                </small>
              </Field>

              {marginPreview && (
                <div style={{ padding: "0.5rem 0.75rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem" }}>
                  Marjă estimată: <strong style={{ color: marginPreview.pct >= 25 ? "#4ade80" : marginPreview.pct >= 10 ? "#facc15" : "#fb923c" }}>
                    {Math.round(marginPreview.value)} RON ({Math.round(marginPreview.pct)}%)
                  </strong>
                  {parseFloat(form.min_price) > 0 && (
                    <div style={{ marginTop: "0.25rem", color: "var(--text-secondary)", fontSize: "0.75rem" }}>
                      Interval preț: {Math.round(parseFloat(form.min_price))} — {Math.round(parseFloat(form.max_price) || 0)} RON
                    </div>
                  )}
                  {form.platforms.length > 0 && (
                    <div style={{ marginTop: "0.375rem", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                      Fee ceiling: {form.platforms.map((p) => `${p.toUpperCase()}: ${Math.round(feeCeiling(form.resale_price, p))} RON`).join(" · ")}
                    </div>
                  )}
                </div>
              )}

              <Field label="Exclude cuvinte din titlu (Enter pentru a adăuga)">
                <div style={{
                  border: "1px solid var(--border-color)",
                  borderRadius: "0.5rem",
                  backgroundColor: "var(--bg-dark)",
                  padding: "0.375rem 0.5rem",
                  display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.375rem",
                  minHeight: "2.5rem",
                }}>
                  {excludeChips.map((chip) => (
                    <span key={chip} style={{
                      display: "inline-flex", alignItems: "center", gap: "0.25rem",
                      backgroundColor: "rgba(37,99,235,0.15)",
                      border: "1px solid rgba(37,99,235,0.3)",
                      color: "#60a5fa",
                      fontSize: "0.75rem",
                      padding: "0.125rem 0.5rem",
                      borderRadius: "0.375rem",
                    }}>
                      {chip}
                      <button
                        type="button"
                        onClick={() => setExcludeChips(excludeChips.filter((c) => c !== chip))}
                        style={{ background: "none", border: "none", color: "#60a5fa", cursor: "pointer", padding: 0, display: "flex" }}
                      >
                        <X style={{ width: "12px", height: "12px" }} />
                      </button>
                    </span>
                  ))}
                  <input
                    type="text"
                    value={chipInput}
                    onChange={(e) => setChipInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const w = chipInput.trim();
                        if (w && !excludeChips.includes(w)) {
                          setExcludeChips([...excludeChips, w]);
                        }
                        setChipInput("");
                      }
                    }}
                    placeholder="Adaugă cuvânt sau frază... (Enter)"
                    style={{
                      flex: 1, minWidth: "140px",
                      backgroundColor: "transparent",
                      border: "none",
                      color: "var(--text-primary)",
                      fontSize: "0.8125rem", outline: "none", padding: "0.25rem",
                    }}
                  />
                </div>
              </Field>

              <Field label={<>Exclude cuvinte din descriere (Enter pentru a adăuga)<span style={{ fontSize: "0.7rem", color: "var(--text-secondary)", fontWeight: 400, marginLeft: "0.5rem" }}>— funcționează pe OLX și Vinted</span></>}>
                <div style={{
                  border: "1px solid var(--border-color)",
                  borderRadius: "0.5rem",
                  backgroundColor: "var(--bg-dark)",
                  padding: "0.375rem 0.5rem",
                  display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.375rem",
                  minHeight: "2.5rem",
                }}>
                  {excludeDescChips.map((chip) => (
                    <span key={chip} style={{
                      display: "inline-flex", alignItems: "center", gap: "0.25rem",
                      backgroundColor: "rgba(37,99,235,0.15)",
                      border: "1px solid rgba(37,99,235,0.3)",
                      color: "#60a5fa",
                      fontSize: "0.75rem",
                      padding: "0.125rem 0.5rem",
                      borderRadius: "0.375rem",
                    }}>
                      {chip}
                      <button
                        type="button"
                        onClick={() => setExcludeDescChips(excludeDescChips.filter((c) => c !== chip))}
                        style={{ background: "none", border: "none", color: "#60a5fa", cursor: "pointer", padding: 0, display: "flex" }}
                      >
                        <X style={{ width: "12px", height: "12px" }} />
                      </button>
                    </span>
                  ))}
                  <input
                    type="text"
                    value={descChipInput}
                    onChange={(e) => setDescChipInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const w = descChipInput.trim();
                        if (w && !excludeDescChips.includes(w)) {
                          setExcludeDescChips([...excludeDescChips, w]);
                        }
                        setDescChipInput("");
                      }
                    }}
                    placeholder="Adaugă cuvânt sau frază... (Enter)"
                    style={{
                      flex: 1, minWidth: "140px",
                      backgroundColor: "transparent",
                      border: "none",
                      color: "var(--text-primary)",
                      fontSize: "0.8125rem", outline: "none", padding: "0.25rem",
                    }}
                  />
                </div>
              </Field>

              {(form.platforms.includes("autovit") || form.platforms.includes("mobilede")) && (
                <CarFiltersSection
                  value={form.car_filters || EMPTY_CAR_FILTERS}
                  onChange={(cf) => setForm({ ...form, car_filters: cf })}
                  inputStyle={inputStyle}
                />
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Field label="Interval polling">
                  <select value={form.poll_interval_minutes} onChange={(e) => setForm({ ...form, poll_interval_minutes: parseInt(e.target.value) })} style={inputStyle}>
                    {POLL_OPTIONS.map((m) => <option key={m} value={m}>{m} min</option>)}
                  </select>
                </Field>
                <Field label="Stare produs">
                  <select value={form.condition} onChange={(e) => setForm({ ...form, condition: e.target.value })} style={inputStyle}>
                    {CONDITION_OPTIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </Field>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Field label="Județ (opțional)">
                  <input type="text" value={form.judet} onChange={(e) => setForm({ ...form, judet: e.target.value })} placeholder="București, Cluj..." style={inputStyle} />
                </Field>
                <Field label="Oraș (opțional)">
                  <input type="text" value={form.oras} onChange={(e) => setForm({ ...form, oras: e.target.value })} placeholder="București, Cluj-Napoca..." style={inputStyle} />
                </Field>
              </div>

              <Field label="Marjă minimă AI Filter (%)">
                <input type="number" value={form.min_margin_pct} onChange={(e) => setForm({ ...form, min_margin_pct: e.target.value })} step="any" min="0" style={inputStyle} />
                <small style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>
                  Listingurile cu marjă sub acest procent sunt ascunse implicit din feed.
                </small>
              </Field>

              <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", padding: "0.375rem 0.5rem", color: "var(--text-primary)", fontSize: "0.8125rem", cursor: "pointer" }}>
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} style={{ width: "auto" }} />
                Activ
              </label>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                  <input
                    type="checkbox"
                    id="use-hours"
                    checked={form.use_active_hours || false}
                    onChange={(e) => setForm((prev) => ({ ...prev, use_active_hours: e.target.checked }))}
                    style={{ width: "15px", height: "15px", cursor: "pointer" }}
                  />
                  <label htmlFor="use-hours" style={{ fontSize: "0.875rem", color: "var(--text-primary)", cursor: "pointer" }}>
                    Activ doar în interval orar
                  </label>
                </div>

                {form.use_active_hours && (
                  <div style={{ marginTop: "0.625rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                    <div>
                      <label style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", display: "block", marginBottom: "0.25rem" }}>
                        De la (ora)
                      </label>
                      <select
                        value={form.active_hours_start ?? 8}
                        onChange={(e) => setForm((prev) => ({ ...prev, active_hours_start: parseInt(e.target.value) }))}
                        style={inputStyle}
                      >
                        {Array.from({ length: 24 }, (_, i) => (
                          <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", display: "block", marginBottom: "0.25rem" }}>
                        Până la (ora)
                      </label>
                      <select
                        value={form.active_hours_end ?? 22}
                        onChange={(e) => setForm((prev) => ({ ...prev, active_hours_end: parseInt(e.target.value) }))}
                        style={inputStyle}
                      >
                        {Array.from({ length: 24 }, (_, i) => (
                          <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
                        ))}
                      </select>
                    </div>
                    <p style={{ gridColumn: "1/-1", fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "-0.25rem" }}>
                      Keyword-ul nu va fi scanat în afara acestui interval. Suportă intervale peste miezul nopții (ex: 22:00–06:00).
                    </p>
                  </div>
                )}
              </div>

              <div style={{
                backgroundColor: "transparent",
                border: "1px solid var(--border-color)",
                borderRadius: "0.5rem",
                padding: "1rem",
                display: "flex",
                flexDirection: "column",
                gap: "0.75rem",
              }}>
                <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  Canale de notificare
                </div>

                <NotifToggle
                  label="Notificări Email"
                  subtitle="Primești email pentru dealuri cu scor A și B"
                  value={form.notify_email}
                  onChange={(v) => setForm({ ...form, notify_email: v })}
                />
                <NotifToggle
                  label="Notificări Discord"
                  subtitle="Trimite la webhook-urile configurate în Setări Radar"
                  value={form.notify_discord}
                  onChange={(v) => setForm({ ...form, notify_discord: v })}
                />

                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                  Notificările in-app sunt întotdeauna active indiferent de selecție.
                </div>
              </div>
            </div>

            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button type="button" onClick={() => setShowForm(false)} style={{ padding: "0.5rem 0.875rem", backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem", cursor: "pointer" }}>
                Anulează
              </button>
              <button type="submit" style={{ padding: "0.5rem 0.875rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                <Save style={{ width: "14px", height: "14px" }} />
                Salvează
              </button>
            </div>
          </form>
        </div>
      )}

      {trendKw && (
        <TrendModal
          kw={trendKw}
          data={trendData}
          days={trendDays}
          loading={trendLoading}
          onClose={() => { setTrendKw(null); setTrendData(null); }}
          onDaysChange={changeTrendDays}
        />
      )}

      {/* MODIFICARE 18 — modal confirmare stergere cu impact */}
      <DeleteKeywordModal
        data={deleteModal}
        onCancel={() => setDeleteModal(null)}
        onConfirm={() => { performDelete(deleteModal.keywordId); setDeleteModal(null); }}
      />

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function TrendModal({ kw, data, days, loading, onClose, onDaysChange }) {
  const trendColors = {
    crescator: { bg: "rgba(239,68,68,0.15)", border: "#ef4444", text: "#fca5a5", label: "↑ Crescător" },
    descrescator: { bg: "rgba(22,163,74,0.15)", border: "#16a34a", text: "#4ade80", label: "↓ Descrescător" },
    stabil: { bg: "rgba(100,116,139,0.15)", border: "#64748b", text: "#94a3b8", label: "→ Stabil" },
  };
  const trendCfg = trendColors[data?.trend_direction] || trendColors.stabil;
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 100, padding: "1.5rem",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "0.875rem",
          maxWidth: "900px", width: "100%",
          maxHeight: "90vh", overflowY: "auto",
          padding: "1.25rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem", flexWrap: "wrap", gap: "0.5rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>
            Evoluție preț — {kw.name}
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}>
            <X style={{ width: "20px", height: "20px" }} />
          </button>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.875rem" }}>
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => onDaysChange(d)}
              style={{
                padding: "0.375rem 0.75rem",
                backgroundColor: days === d ? "var(--blue-primary)" : "var(--bg-dark)",
                color: days === d ? "white" : "var(--text-secondary)",
                border: "1px solid var(--border-color)",
                borderRadius: "0.5rem",
                fontSize: "0.8125rem",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Ultimele {d} zile
            </button>
          ))}
        </div>

        {loading ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "300px" }}>
            <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
          </div>
        ) : !data || data.series.length === 0 ? (
          <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
            Nu există date suficiente pentru intervalul selectat.
          </div>
        ) : (
          <>
            <div style={{ height: "320px", width: "100%" }}>
              <ResponsiveContainer>
                <LineChart data={data.series} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border-color)" strokeDasharray="3 3" />
                  <XAxis dataKey="date" stroke="var(--text-muted)" style={{ fontSize: "0.7rem" }} />
                  <YAxis stroke="var(--text-muted)" style={{ fontSize: "0.7rem" }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.75rem" }}
                    labelStyle={{ color: "var(--text-primary)" }}
                  />
                  <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
                  <Line type="monotone" dataKey="avg_price" name="Preț mediu" stroke="#60a5fa" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="min_price" name="Cel mai mic" stroke="#4ade80" strokeDasharray="4 3" strokeWidth={1.5} dot={false} />
                  <Line type="monotone" dataKey="max_price" name="Cel mai mare" stroke="#f87171" strokeDasharray="4 3" strokeWidth={1.5} dot={false} />
                  {kw.max_price ? (
                    <ReferenceLine y={kw.max_price} stroke="#facc15" strokeDasharray="6 4" label={{ value: "Bugetul tău max", position: "right", fontSize: 10, fill: "#facc15" }} />
                  ) : null}
                  {kw.resale_price ? (
                    <ReferenceLine y={kw.resale_price} stroke="#a78bfa" strokeDasharray="6 4" label={{ value: "Preț revânzare", position: "right", fontSize: 10, fill: "#a78bfa" }} />
                  ) : null}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem", marginTop: "0.875rem" }}>
              <StatCard label="Preț mediu" value={`${Math.round(data.overall_avg)} RON`} color="#60a5fa" />
              <StatCard label="Cel mai mic găsit" value={`${Math.round(data.overall_min)} RON`} color="#4ade80" />
              <div style={{
                padding: "0.75rem", backgroundColor: "var(--bg-dark)",
                border: `1px solid ${trendCfg.border}`, borderRadius: "0.5rem", textAlign: "center",
              }}>
                <div style={{ fontSize: "1rem", fontWeight: 700, color: trendCfg.text }}>{trendCfg.label}</div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>Tendință</div>
              </div>
            </div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic", marginTop: "0.5rem" }}>
              Graficul se bazează pe listingurile găsite de FlipRadar. Primele zile pot avea date incomplete.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{ padding: "0.75rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", textAlign: "center" }}>
      <div style={{ fontSize: "1rem", fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>{label}</div>
    </div>
  );
}

function NotifToggle({ label, subtitle, value, onChange }) {
  const on = !!value;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "0.8125rem", color: "var(--text-primary)", fontWeight: 500 }}>{label}</div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>{subtitle}</div>
      </div>
      <button
        type="button"
        onClick={() => onChange(!on)}
        aria-pressed={on}
        style={{
          width: 44, height: 24, borderRadius: 12,
          backgroundColor: on ? "var(--blue-primary)" : "var(--border-color)",
          border: "none", padding: 2, cursor: "pointer",
          position: "relative",
          transition: "background-color 0.15s ease",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: on ? 22 : 2,
            width: 20, height: 20, borderRadius: "50%",
            backgroundColor: "#ffffff",
            transition: "left 0.15s ease",
            boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
          }}
        />
      </button>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label style={{ display: "block" }}>
      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>{label}</div>
      {children}
    </label>
  );
}

const th = { textAlign: "left", padding: "0.625rem 0.75rem", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" };
const td = { padding: "0.625rem 0.75rem", color: "var(--text-primary)" };
const iconBtn = {
  padding: "0.375rem",
  backgroundColor: "var(--bg-dark)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.375rem",
  color: "var(--text-secondary)",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
};

const bulkBtn = {
  padding: "0.375rem 0.75rem",
  backgroundColor: "var(--bg-dark)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.5rem",
  color: "var(--text-secondary)",
  fontSize: "0.75rem",
  fontWeight: 500,
  cursor: "pointer",
};

function CarFiltersSection({ value, onChange, inputStyle }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div style={{
      backgroundColor: "var(--bg-dark)",
      border: "1px solid var(--border-color)",
      borderRadius: "0.5rem",
      padding: "0.875rem",
      display: "flex",
      flexDirection: "column",
      gap: "0.625rem",
    }}>
      <div>
        <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "0.375rem" }}>
          🚗 Filtre specifice platformelor auto
        </div>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
          Aceste filtre se aplică doar pentru Autovit și Mobile.de.
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.625rem" }}>
        <Field label="Marcă">
          <input type="text" value={value.marca || ""} onChange={(e) => set("marca", e.target.value)} placeholder="ex: BMW, Audi, Dacia..." style={inputStyle} />
        </Field>
        <Field label="Model">
          <input type="text" value={value.model || ""} onChange={(e) => set("model", e.target.value)} placeholder="ex: X5, Golf, Logan..." style={inputStyle} />
        </Field>
        <Field label="An fabricație de la">
          <input type="number" min="1980" max="2030" value={value.an_de_la || ""} onChange={(e) => set("an_de_la", e.target.value)} placeholder="ex: 2018" style={inputStyle} />
        </Field>
        <Field label="An fabricație până la">
          <input type="number" min="1980" max="2030" value={value.an_pana_la || ""} onChange={(e) => set("an_pana_la", e.target.value)} placeholder="ex: 2023" style={inputStyle} />
        </Field>
        <Field label="Kilometri maximi">
          <input type="number" min="0" value={value.km_maxim || ""} onChange={(e) => set("km_maxim", e.target.value)} placeholder="ex: 150000" style={inputStyle} />
        </Field>
        <Field label="Combustibil">
          <select value={value.combustibil || ""} onChange={(e) => set("combustibil", e.target.value)} style={inputStyle}>
            {CAR_FUEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Caroserie">
          <select value={value.caroserie || ""} onChange={(e) => set("caroserie", e.target.value)} style={inputStyle}>
            {CAR_BODY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Cutie viteze">
          <select value={value.cutie_viteze || ""} onChange={(e) => set("cutie_viteze", e.target.value)} style={inputStyle}>
            {CAR_GEARBOX_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
      </div>

      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
        Câmpurile de mai sus nu sunt obligatorii. Cu cât adaugi mai multe filtre, cu atât rezultatele vor fi mai precise și mai puțin zgomot în feed.
      </div>
    </div>
  );
}
