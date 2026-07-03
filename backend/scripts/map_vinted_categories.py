"""Mapare Vinted catalog_id -> (tab, categorie, subcategorie) FlipRadar.

Rulare (din backend/, cu venv):
    python -m scripts.map_vinted_categories

Strategie: Vinted expune INTREGUL arbore de categorii intr-un singur request, in
homepage (`GET https://www.vinted.ro/`). Arborele e serializat in stream-ul RSC
Next.js (`self.__next_f.push([1,"..."])`), sub cheia `catalogTree`. E un arbore
NESTED: fiecare nod = {id (=catalog_id), title, code, url, catalogs:[copii]}.

Pentru fiecare (tab, categorie, subcategorie) din VINTED_STRUCTURE, cauta nodul
Vinted cu titlul potrivit (potrivire tolerant la diacritice/caractere speciale),
scoped pe subarborele parintelui, si stocheaza catalog_id-ul. Emite maparea cu 3
niveluri de granularitate: (tab, cat, sub) -> frunza, (tab, cat, "") -> categorie,
(tab, "", "") -> tab. Standalone — nu se importa in app, nu ruleaza la startup.

Output: raport de acoperire + dict-ul `VINTED_CATALOG_ID_MAP` gata de copiat in
`app/services/radar/vinted_scraper.py`.
"""
import json
import re
import sys
from datetime import date

# Consola Windows (cp1252) nu poate afisa diacritice — fortam UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from curl_cffi import requests as curl_requests
from app.services.radar.base_scraper import build_headers

_IMPERSONATE = "chrome110"

# Taburi unde numele FlipRadar difera de titlul Vinted.
TAB_ALIAS = {
    "Media și cărți": "Divertisment",
}

# Structura completa de mapat — exact cele 3 niveluri din MARKETPLACE_CATEGORIES.vinted.
VINTED_STRUCTURE = {
    "Femei": {
        "Haine": ["Pulovere", "Rochii", "Fustă-pantaloni scurtă", "Blugi",
                  "Pantaloni scurți și pantaloni trei sferturi", "Costume de baie",
                  "Haine maternitate", "Costume și ținute speciale",
                  "Îmbrăcăminte de exterior", "Costume și blazere", "Fuste",
                  "Topuri și tricouri", "Pantaloni și colanți", "Salopete lungi și scurte",
                  "Lenjerie intimă și pijamale", "Îmbrăcăminte pentru sport",
                  "Alte articole de îmbrăcăminte"],
        "Pantofi": ["Pantofi tip boat shoe, loaferi și mocasini", "Saboți",
                    "Flip-flops și șlapi", "Pantofi cu șiret", "Sandale",
                    "Încălțăminte sport", "Balerini", "Cizme și ghete", "Espadrile",
                    "Pantofi cu toc", "Pantofi Mary Jane și T-bar", "Papuci de casă",
                    "Pantofi sport"],
        "Genți": ["Genți plajă", "Genți bucket", "Plicuri", "Genți sport", "Genți hobo",
                  "Genți de călătorie și valize", "Genți tip poștas", "Sacoșe",
                  "Poșete de mână", "Rucsacuri", "Serviete", "Borsete",
                  "Saci protecție haine", "Genți de mână", "Genți și saci de voiaj",
                  "Genți pentru cosmetice", "Genți de umăr", "Poșete și portofele"],
        "Accesorii": ["Curele", "Accesorii pentru păr", "Pălării și șepci", "Brelocuri",
                      "Ochelari de soare", "Ceasuri", "Bandane și panglici", "Mănuși",
                      "Batiste", "Bijuterii", "Fulare și eșarfe", "Umbrele", "Alte accesorii"],
        "Frumusețe": ["Parfum", "Instrumente pentru înfrumusețare", "Îngrijirea unghiilor",
                      "Îngrijirea părului", "Machiaj", "Îngrijirea tenului",
                      "Îngrijirea mâinilor", "Îngrijirea corpului",
                      "Alte articole de frumusețe"],
    },
    "Bărbați": {
        "Haine": ["Îmbrăcăminte de exterior", "Costume și blazere", "Pantaloni",
                  "Șosete și lenjerie intimă", "Costume de baie",
                  "Costume și ținute speciale", "Blugi", "Topuri și tricouri",
                  "Pulovere", "Pantaloni scurți", "Haine de dormit",
                  "Îmbrăcăminte pentru sport", "Alte articole de îmbrăcăminte"],
        "Pantofi": ["Cizme și ghete", "Espadrile", "Pantofi eleganți", "Papuci de casă",
                    "Pantofi sport", "Pantofi tip boat shoe, loaferi și mocasini",
                    "Saboți și papuci", "Flip-flops și șlapi", "Sandale", "Încălțăminte sport"],
        "Accesorii": ["Bandane și eșarfe de păr", "Bretele", "Batiste", "Bijuterii",
                      "Fulare și eșarfe", "Cravate și papioane", "Genți și rucsacuri",
                      "Curele", "Mănuși", "Pălării și șepci", "Batiste buzunar",
                      "Ochelari de soare", "Ceasuri", "Altele"],
        "Îngrijire": ["Instrumente și accesorii", "Îngrijirea corpului",
                      "Aftershave și apă de colonie", "Seturi de îngrijire",
                      "Îngrijirea tenului", "Îngrijirea părului",
                      "Îngrijirea mâinilor și a unghiilor", "Machiaj",
                      "Alte articole de îngrijire"],
    },
    "Designer": {
        "Designer femei": ["Pantofi de designer", "Îmbrăcăminte de designer",
                           "Genți de designer", "Accesorii de designer"],
        "Designer bărbați": ["Accesorii de designer", "Pantofi de designer",
                             "Îmbrăcăminte de designer"],
    },
    "Copii": {
        "Îmbrăcăminte pentru fete": ["Pantofi", "Pulovere și hanorace cu glugă", "Rochii",
                                     "Pantaloni și pantaloni scurți", "Accesorii",
                                     "Lenjerie intimă și șosete", "Îmbrăcăminte sportivă",
                                     "Îmbrăcăminte pentru gemeni", "Ținute de ocazie",
                                     "Îmbrăcăminte pentru bebe fată", "Îmbrăcăminte de exterior",
                                     "Topuri și tricouri", "Fuste", "Genți și rucsacuri",
                                     "Costume de baie", "Pijamale", "Pachete îmbrăcăminte",
                                     "Ținute și costume de carnaval",
                                     "Alte articole de îmbrăcăminte pentru fete"],
        "Îmbrăcăminte pentru băieți": ["Pantofi", "Pulovere și hanorace cu glugă",
                                       "Pantaloni și salopete", "Accesorii",
                                       "Lenjerie intimă și șosete", "Îmbrăcăminte sportivă",
                                       "Îmbrăcăminte pentru gemeni", "Ținute de ocazie",
                                       "Îmbrăcăminte pentru bebe băiat", "Îmbrăcăminte de exterior",
                                       "Topuri și tricouri", "Genți și rucsacuri",
                                       "Costume de baie", "Pijamale", "Pachete îmbrăcăminte",
                                       "Ținute și costume de carnaval", "Alte haine pentru băieți"],
        "Jucării": ["Arte și meșteșuguri", "Cuburi și jucării de construit",
                    "Costumează-te și intră în rol", "Jucării electronice",
                    "Noutăți și jucării fidget", "Jucării moi și animale de pluș",
                    "Figurine și accesorii", "Activități și jucării pentru copii",
                    "Păpuși și accesorii", "Jucării educative",
                    "Jucării muzicale și instrumente de jucărie",
                    "Jucării pentru exterior și sportive",
                    "Mașini, trenuri și alte vehicule de jucărie"],
        "Cărucioare, landouri și scaune auto": ["Cărucioare", "Scaune auto",
                                                "Accesorii scaune auto",
                                                "Sisteme de purtare și wrap-uri pentru bebeluși",
                                                "Accesorii Buggy", "Înălțătoare"],
        "Mobilier și decorațiuni": ["Saltele și covoare de joacă", "Șezlonguri și cuiburi",
                                    "Mobilier pentru camera copilului", "Scaune", "Rafturi",
                                    "Șifoniere", "Saltele pentru copii", "Țarcuri de joacă",
                                    "Decorațiuni și suveniruri", "Covoare și carpete",
                                    "Mobilier de joacă", "Mese și birouri"],
        "Îmbăiere și înfășare": ["Baie", "Scutece", "Olițe", "Scaune cu trepte",
                                 "Genți pentru înfășat", "Saltele pentru schimbat și huse",
                                 "Depozitarea și eliminarea scutecelor",
                                 "Îngrijirea pielii și igienă"],
        "Echipamente de protecție și siguranță pentru copii": [
            "Accesorii de protecție pentru copii",
            "Hamuri și centuri de siguranță",
            "Porți și protecții pentru copii", "Protecție fonică"],
        "Sănătate și sarcină": ["Aspiratoare nazale", "Perne pentru sarcină", "Cântare",
                                "Umidificatoare", "Îngrijirea postpartum",
                                "Centuri de susținere pentru sarcină", "Termometre"],
        "Rechizite școlare": ["Ghiozdane", "Cutii și pungi pentru prânz", "Rechizite școlare"],
    },
    "Casă": {
        "Aparate electrocasnice mici": ["Aparate pentru cafea, ceai și espresso",
                                        "Blendere, mixere și procesoare de alimente",
                                        "Friteuze", "Plite", "Dozatoare pentru apă și suc",
                                        "Accesorii pentru electrocasnice mici de bucătărie",
                                        "Ceainice", "Prăjitoare de pâine", "Microunde",
                                        "Grătare și grătare electrice", "Storcătoare",
                                        "Aparate specializate",
                                        "Piese pentru electrocasnice mici de bucătărie"],
        "Ustensile de gătit și de copt": ["Tigăi", "Tăvi de cuptor și prăjit",
                                          "Ustensile de gătit și de copt speciale",
                                          "Accesorii pentru vase de gătit și de copt",
                                          "Oale", "Tavă de copt", "Forme de copt",
                                          "Ustensile pentru gătit și copt"],
        "Ustensile de bucătărie": ["Ustensile de gătit", "Căni și linguri de măsurat",
                                   "Boluri de amestecare", "Depozitarea alimentelor",
                                   "Unelte de bucătărie speciale", "Tocătoare",
                                   "Cântar de bucătărie", "Termometre alimentare",
                                   "Sită, strecurătoare", "Ustensile pentru bar"],
        "Articole de masă": ["Veselă", "Tacâmuri", "Pahare"],
        "Îngrijirea gospodăriei": ["Fiare de călcat și îngrijire îmbrăcăminte",
                                   "Încălzire, răcire și aerisire", "Aspirare și curățare"],
        "Textile": ["Pături", "Perne decorative", "Covoare și covorașe", "Tapiserii",
                    "Lenjerie de pat", "Perdele și jaluzele", "Huse", "Fețe de masă", "Prosoape"],
        "Accesorii pentru casă": ["Ceasuri", "Accesorii decorative", "Accesorii pentru șemineu",
                                  "Rafturi de prezentare", "Oglinzi", "Vaze",
                                  "Lumânări și parfumuri pentru casă", "Sculpturi și figurine",
                                  "Plante și flori artificiale", "Iluminat",
                                  "Rame foto și imagini", "Depozitare și organizare",
                                  "Decorațiune de perete"],
        "Consumabile de birou": ["Caiete și blocuri de scris", "Semne de carte",
                                 "Accesorii pentru birou", "Consumabile pentru scris",
                                 "Bandă adezivă, cleme și elemente de fixare",
                                 "Materiale pentru prezentări", "Seifuri",
                                 "Planificatoare și agende personale", "Penare",
                                 "Calculatoare", "Organizatoare de documente",
                                 "Instrumente pentru desen tehnic",
                                 "Capsatoare și perforatoare", "Aparate electronice de birou"],
        "Festivități și sărbători": ["Cărți poștale și plicuri", "Decor de sărbători",
                                     "Decorațiuni de masă", "Coronițe",
                                     "Bannere, steaguri și fanioane",
                                     "Hârtie și pungi de cadouri",
                                     "Decorațiuni de petrecere", "Decorațiuni pentru copaci"],
        "Unelte și DIY": ["Unelte manuale", "Unelte și accesorii pentru vopsit",
                          "Echipament pentru electricieni", "Accesorii pentru unelte",
                          "Transport și depozitare unelte", "Feronerie", "Unelte electrice",
                          "Instrumente de măsurare", "Unelte instalații sanitare",
                          "Unelte de zidărie", "Echipament de protecție",
                          "Echipamente pentru atelier și șantier",
                          "Casă inteligentă și securitate"],
        "Exterior și grădină": ["Accesorii pentru unelte electrice de exterior",
                                "Ghivece, jardiniere și accesorii",
                                "Decor pentru exterior și grădină",
                                "Spa-uri, piscine și echipamente",
                                "Unelte pentru îndepărtarea zăpezii",
                                "Unelte electrice pentru exterior",
                                "Unelte de mână pentru exterior", "Echipament de udare",
                                "Ustensile pentru grătar și gătit în aer liber",
                                "Instrumente meteorologice"],
        "Animale": ["Pisici", "Pești", "Reptile", "Câini", "Animale de companie mici", "Păsări"],
    },
    "Electronice": {
        "Jocuri video și console": ["Jocuri", "Căști pentru jocuri", "Realitate virtuală",
                                    "Console", "Controlere", "Simulatoare", "Accesorii"],
        "Calculatoare și accesorii": ["Calculatoare desktop", "Blank media",
                                      "Accesorii pentru laptop", "Tastaturi și accesorii",
                                      "Mouse pad-uri", "Difuzoare pentru computer",
                                      "Camere web", "Imprimante și accesorii",
                                      "Plăcuțe tactile și stylus", "Laptopuri",
                                      "Piese și componente de calculator",
                                      "Accesorii pentru computere",
                                      "Docking stations și hub-uri USB", "Mouse-uri",
                                      "Monitoare și accesorii", "Microfoane de calculator",
                                      "Dispozitive de rețea", "Scanere și accesorii"],
        "Telefoane mobile și comunicare": ["Piese și accesorii pentru telefoane mobile",
                                           "Faxuri", "Telefoane mobile demo", "Telefoane mobile",
                                           "Telefoane fixe", "Comunicații radio"],
        "Audio, căști și hi-fi": ["Playere muzicale portabile", "Boxe portabile",
                                  "Sisteme audio pentru acasă", "Piese audio și hi-fi",
                                  "Căști și earbuds", "Radiouri portabile",
                                  "Difuzoare inteligente", "Accesorii pentru dispozitive audio"],
        "Camere foto și accesorii": ["Obiective", "Carduri de memorie",
                                     "Stabilizatoare și suporturi", "Echipament de studio",
                                     "Accesorii", "Alte echipamente fotografice", "Camere foto",
                                     "Blițuri", "Trepieduri și monopieduri",
                                     "Echipament pentru camera obscură",
                                     "Drone cu cameră și accesorii",
                                     "Piese de schimb pentru aparat foto"],
        "Tablete, e-readere și accesorii": ["E-readere", "PDAs", "Tablete",
                                            "Agende electronice", "Accesorii"],
        "TV și home cinema": ["Proiectoare", "Antene TV", "Decodificatoare video",
                              "Sisteme home cinema", "DVD playere",
                              "Alte dispozitive de redare video", "Televizoare",
                              "Dispozitive de streaming", "Antene satelit",
                              "Receptoare de televiziune", "Playere Blu-ray",
                              "Videocasetofoane", "Accesorii TV și home cinema"],
        "Electronice pentru frumusețe și îngrijire personală": [
            "Instrumente de înfrumusețare", "Instrumente de masaj",
            "Instrumente pentru îngrijirea unghiilor",
            "Instrumente de coafură", "Bărbierit și îndepărtarea părului",
            "Îngrijire dentară și orală electrică",
            "Cântare pentru uz personal"],
        "Portabile": ["Monitoare de fitness", "Inele inteligente",
                      "Carcase pentru ceasuri inteligente", "Ceasuri inteligente",
                      "Ochelari inteligenți", "Benzi de schimb"],
        "Alte dispozitive și accesorii": ["GPS și dispozitive de navigație prin satelit",
                                          "Cântare pentru bagaje", "Cabluri", "Baterii externe",
                                          "Baterii și surse de alimentare",
                                          "Imprimare și scanare 3D", "Detectoare de obiecte",
                                          "Adaptoare", "Încărcătoare",
                                          "Protecții la supratensiune și prelungitoare",
                                          "Alte accesorii"],
    },
    "Media și cărți": {
        "Cărți": ["Non-ficțiune", "Benzi desenate, manga și romane grafice",
                  "Cărți de colorat, puzzle și activități", "Ficțiune",
                  "Copii și tineri adulți", "Manuale și materiale de studiu"],
        "Reviste": [],
        "Muzică": ["CD-uri", "Discuri de vinil", "Casete audio", "MiniDiscuri"],
        "Video": ["Betamax", "DVD", "LaserDisc", "4K Blu-ray", "Blu-ray", "HD DVD", "VHS"],
    },
    "Hobbyuri și colecții": {
        "Carduri de tranzacționare": ["Pachete Booster", "Pachete de cărți de joc",
                                      "Poster cu carduri", "Carduri de tranzacționare individuale",
                                      "Cutii Booster", "Loturi de carduri de tranzacționare"],
        "Jocuri de societate": [],
        "Puzzle-uri": [],
        "Jocuri de masă și în miniatură": [],
        "Suveniruri": ["Suveniruri muzicale", "Alte suveniruri", "Suvenir sportiv",
                       "Suveniruri de film și TV"],
        "Monede și bancnote": ["Monede", "Medalii și recompense", "Bancnote",
                               "Loturi și seturi", "Certificate de acțiuni"],
        "Timbre": ["Loturi și seturi de timbre", "Cataloage și ghiduri de timbre",
                   "Timbre individuale", "First day covers (FDC)",
                   "Instrumente și echipamente pentru timbre"],
        "Cărți poștale": [],
        "Instrumente muzicale și echipamente": ["Amplificatoare și pedale",
                                                "Claviaturi și sintetizatoare",
                                                "Instrumente de suflat", "Echipament DJ",
                                                "Accesorii pentru creație muzicală",
                                                "Chitare și chitare bas", "Tobe și percuție",
                                                "Instrumente cu coarde",
                                                "Echipament de studio și sunet live",
                                                "Echipament pentru karaoke"],
        "Arte și meșteșuguri": ["Pictură", "Caligrafie", "Papercraft", "Fabricarea lumânărilor",
                                "Materiale pentru artizanat", "Cusut, tricotat și broderie",
                                "Desene și schițe", "Mărgele și accesorii de bijuterii",
                                "Tăiere cu matrița", "Sculptură și olărit",
                                "Unelte de meșteșugărit"],
        "Depozitare obiecte de colecție": ["Cutii pentru păstrarea obiectelor de colecție",
                                           "Suporturi de carduri cu șurub",
                                           "Separatoare pentru albume și clasoare",
                                           "Covoare pentru puzzle", "Albume și clasoare",
                                           "Huse pentru cărți de joc",
                                           "Cutii pentru pachete de cărți",
                                           "Folii pentru albume și clasoare",
                                           "Depozitarea altor obiecte de colecție"],
        "Accesorii pentru jocuri": ["Pietre și jetoane de joc", "Alte accesorii pentru jocuri",
                                    "Zar", "Covoare pentru jocuri"],
    },
    "Sporturi": {
        "Ciclism": ["Căști pentru biciclete", "Remorci pentru biciclete", "Piese de bicicletă",
                    "Biciclete pentru copii", "Accesorii și unelte pentru ciclism",
                    "Scaune pentru biciclete pentru copii"],
        "Fitness, alergare și yoga": ["Alergare", "Accesorii de fitness pentru acasă",
                                      "Antrenament de forță", "Echipament pentru yoga și pilates",
                                      "Sticle de apă"],
        "Sporturi în aer liber": ["Pescuit și vânătoare", "Rucsacuri pentru drumeții",
                                  "Alte accesorii pentru sporturi în aer liber",
                                  "Corturi de camping și echipament de dormit",
                                  "Torțe, faruri și lanterne", "Binocluri și lunete",
                                  "Mobilier de camping", "Cățărare și bouldering",
                                  "Arzătoare de camping și ustensile de gătit",
                                  "Răcitoare", "Busole", "Sisteme și pachete de hidratare",
                                  "Bețe de trekking"],
        "Sporturi nautice": ["Înot", "Costume, mănuși și ghete de neopren",
                             "Accesorii pentru sporturi nautice",
                             "Dispozitive personale de plutire", "Plute gonflabile",
                             "Plăci de paddleboarding", "Caiace", "Kiteboarduri",
                             "Plăci de wakeboard", "Căști pentru sporturi nautice",
                             "Colac remorcabil", "Schiuri de apă", "Skimboards"],
        "Sporturi de echipă": ["Fotbal", "Alte echipamente pentru sporturi de echipă",
                               "Baschet", "Volei", "Echipament de antrenament și de arbitraj",
                               "Handball", "Fotbal american", "Baseball și softball", "Rugby",
                               "Hochei de sală", "Lacrosse", "Hochei pe iarbă",
                               "Sporturi gaelice", "Cricket", "Netball"],
        "Sporturi cu rachetă": ["Tenis", "Tenis de masă", "Padel", "Badminton", "Squash",
                                "Pickleball", "Protecție pentru ochi în sporturile cu rachetă",
                                "Racquetball"],
        "Golf": ["Mingi de golf", "Crose de golf", "Accesorii de golf",
                 "Echipament de antrenament pentru golf", "Saci de golf",
                 "Mănuși de golf", "Cărucioare de golf"],
        "Echitație": ["Șei și accesorii", "Veste de protecție pentru călărie",
                      "Caschete de echitație", "Mănuși de echitație",
                      "Huse de mătase pentru căști de echitație"],
        "Skateboard-uri și scutere": ["Scutere", "Skateboarduri", "Protecție pentru skateboard",
                                      "Piese și accesorii pentru skateboard",
                                      "Căști de skateboarding", "Piese și accesorii pentru skate",
                                      "Plăci de longboard"],
        "Box și arte marțiale": ["Protecție corporală pentru box și arte marțiale",
                                 "Mănuși de box și arte marțiale", "Centuri de arte marțiale",
                                 "Saci de box viteză",
                                 "Protecție pentru cap pentru box și arte marțiale",
                                 "Protecții pentru lovituri cu pumnul și piciorul",
                                 "Fășii pentru protecția mâinilor", "Saci de box grei",
                                 "Alte echipamente pentru arte marțiale"],
        "Sporturi și jocuri ocazionale": ["Echipament pentru darts",
                                          "Mingi pentru terenul de joacă",
                                          "Roundnet și spikeball", "Boules & alte jocuri",
                                          "Frisbee și disc golf", "Biliard american și snooker",
                                          "Bowling cu zece popice"],
        "Sporturi de iarnă": ["Echipament pentru snowboard",
                              "Accesorii pentru patinaj artistic", "Rachete de zăpadă",
                              "Ochelari de schi", "Echipament de schi", "Hochei pe gheață",
                              "Săniuș", "Ghetre", "Căști pentru sporturi de iarnă"],
    },
}


def _norm(s: str) -> str:
    """lowercase + fara diacritice + fara caractere speciale (spatii colapsate)."""
    s = (s or "").lower().strip()
    for a, b in (("ă", "a"), ("â", "a"), ("î", "i"), ("ș", "s"), ("ş", "s"),
                 ("ț", "t"), ("ţ", "t")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def _fetch_vinted_tree() -> list:
    """Extrage catalogTree (arbore nested) din homepage-ul Vinted. Un singur request."""
    resp = curl_requests.get(
        "https://www.vinted.ro/",
        headers=build_headers({"Referer": "https://www.vinted.ro/"}),
        impersonate=_IMPERSONATE,
        timeout=25,
    )
    if resp.status_code != 200:
        print(f"[VintedCategoryMapper] homepage HTTP {resp.status_code}")
        return []
    html = resp.text
    # Reconstruieste stream-ul RSC Next.js: fiecare <script>self.__next_f.push([n,"..."])</script>
    flight = []
    for chunk in re.findall(r'self\.__next_f\.push\((\[.*?\])\)</script>', html, re.DOTALL):
        try:
            arr = json.loads(chunk)
            if len(arr) >= 2 and isinstance(arr[1], str):
                flight.append(arr[1])
        except Exception:
            pass
    flight = "".join(flight)
    pos = flight.find('"catalogTree":')
    if pos < 0:
        print("[VintedCategoryMapper] catalogTree absent din flight")
        return []
    start = flight.index("[", pos)
    depth = 0
    in_str = False
    esc = False
    end = None
    for j in range(start, len(flight)):
        c = flight[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
    if end is None:
        print("[VintedCategoryMapper] array catalogTree neinchis")
        return []
    try:
        return json.loads(flight[start:end])
    except Exception as e:
        print(f"[VintedCategoryMapper] parse catalogTree esuat: {e}")
        return []


def _match(candidates: list, name: str):
    """Gaseste nodul cu titlul potrivit intr-o lista de candidati (tolerant)."""
    t = _norm(name)
    if not t:
        return None
    # 1) exact normalizat
    for c in candidates:
        if _norm(c.get("title")) == t:
            return c
    # 2) unul prefix al celuilalt (diferente de tip plural / sufix)
    for c in candidates:
        ct = _norm(c.get("title"))
        if ct and (ct.startswith(t) or t.startswith(ct)):
            return c
    # 3) subset de tokeni (toti tokenii cautarii se regasesc in titlu)
    nt = set(t.split())
    for c in candidates:
        ct = set(_norm(c.get("title")).split())
        if nt and nt <= ct:
            return c
    return None


def _descendants(node: dict) -> list:
    out = []
    for ch in (node.get("catalogs") or []):
        out.append(ch)
        out.extend(_descendants(ch))
    return out


def main() -> int:
    tree = _fetch_vinted_tree()
    if not tree:
        print("EROARE: nu am putut obtine arborele de categorii Vinted.")
        return 1
    total = 1
    def _count(n):
        nonlocal total
        for ch in (n.get("catalogs") or []):
            total += 1
            _count(ch)
    for t in tree:
        _count(t)
    print(f"[VintedCategoryMapper] arbore incarcat: {len(tree)} taburi, {total} noduri total\n")

    catalog_map = {}    # (tab, cat, sub) -> id
    ok_sub = miss_sub = 0
    unresolved = []

    for tab, cats in VINTED_STRUCTURE.items():
        tab_title = TAB_ALIAS.get(tab, tab)
        tab_node = _match(tree, tab_title)
        if not tab_node:
            print(f"[MAP] {tab:<28} → TAB NEGĂSIT ⚠️")
            unresolved.append(f"{tab} (tab)")
            for cat in cats:
                for sub in cats[cat]:
                    unresolved.append(f"{tab} > {cat} > {sub}")
                    miss_sub += 1
            continue
        catalog_map[(tab, "", "")] = tab_node["id"]
        print(f"[MAP] {tab:<28} → catalog_id={tab_node['id']}  ✅  (tab)")

        for cat, subs in cats.items():
            cat_node = _match(tab_node.get("catalogs") or [], cat)
            if not cat_node:
                # fallback: cauta in tot subarborele tabului
                cat_node = _match(_descendants(tab_node), cat)
            if not cat_node:
                print(f"  [MAP] {tab} > {cat:<38} → CATEGORIE NEGĂSITĂ ⚠️")
                unresolved.append(f"{tab} > {cat}")
                for sub in subs:
                    unresolved.append(f"{tab} > {cat} > {sub}")
                    miss_sub += 1
                continue
            catalog_map[(tab, cat, "")] = cat_node["id"]

            for sub in subs:
                # cauta subcategoria: intai copii directi, apoi tot subarborele categoriei
                sub_node = _match(cat_node.get("catalogs") or [], sub)
                if not sub_node:
                    sub_node = _match(_descendants(cat_node), sub)
                if sub_node:
                    catalog_map[(tab, cat, sub)] = sub_node["id"]
                    ok_sub += 1
                else:
                    print(f"[MAP] {tab} > {cat} > {sub:<45} → NEGĂSIT ⚠️")
                    unresolved.append(f"{tab} > {cat} > {sub}")
                    miss_sub += 1

    total_sub = ok_sub + miss_sub
    print(f"\nAcoperire subcategorii: {ok_sub}/{total_sub} mapate.")
    print(f"Intrari totale in map (3 niveluri): {len(catalog_map)}")
    if unresolved:
        print(f"Nemapate ({len(unresolved)}):")
        for u in unresolved:
            print(f"   - {u}")

    # verificare coerenta
    print("\n=== Verificare coerenta ===")
    for key, exp in ((("Femei", "Haine", "Rochii"), 10),
                     (("Femei", "Haine", "Blugi"), 183),
                     (("Femei", "Genți", ""), 19),
                     (("Femei", "", ""), 1904)):
        print(f"  {key} -> {catalog_map.get(key)!r} (asteptat {exp})")

    # dict final gata de copiat
    print("\n" + "=" * 70)
    print("# Generat automat — map_vinted_categories.py — " + date.today().isoformat())
    print(f"# Acoperire: {ok_sub}/{total_sub} subcategorii · {len(catalog_map)} intrari (tab/categorie/subcategorie)")
    print("VINTED_CATALOG_ID_MAP: dict[tuple[str, str, str], int] = {")
    # sortare: tab, apoi categorie, apoi subcategorie (nivelurile agregate primele)
    def sort_key(k):
        tab, cat, sub = k
        tab_i = list(VINTED_STRUCTURE.keys()).index(tab) if tab in VINTED_STRUCTURE else 99
        return (tab_i, cat != "", cat, sub != "", sub)
    for k in sorted(catalog_map, key=sort_key):
        tab, cat, sub = k
        print(f'    ({json.dumps(tab, ensure_ascii=False)}, {json.dumps(cat, ensure_ascii=False)}, {json.dumps(sub, ensure_ascii=False)}): {catalog_map[k]},')
    print("}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
