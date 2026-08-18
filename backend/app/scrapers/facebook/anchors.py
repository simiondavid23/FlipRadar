"""Registrul de ancore geografice si rezolvatorul de scope (FB-2).

51 de puncte care acopera Romania la raza de 65 km. Ancora e singurul mod de a
alege geografia pe calea logat-out: raza e ignorata de Facebook, paginarea nu
merge, iar slug-urile de oras din URL sunt aproape toate invalide (FB-0: 1 din 51).
Deci acoperirea nationala = multe cereri, cate una per ancora, nu una mare.

Date PURE: niciun consumator nu se atinge aici, nicio coloana de DB, nicio migrare.
`fb_scope` pe tabelele de keyword-uri vine la FB-3/FB-7.

DESPRE `city_page_id` — si de ce NU mai exista `fb_slug`:

Slugurile textuale de oras sunt MOARTE, si logat-out (FB-0: 1 valid din 51) si
AUTENTIFICAT (FBS-0b: `cluj-napoca`, `iasi` si `timisoara` au primit toate trei
ACELASI set bucurestean, cu Jaccard 1.000 intre ele). Campul a fost STERS, nu lasat
pe None: un camp care arata utilizabil si nu e a costat deja o runda intreaga.

Ce merge in schimb e ID-ul NUMERIC de locatie, `city_page.id`, citit din
`listing.location.reverse_geocode.city_page`. Masurat ca ancoreaza corect pe patru
orase din regiuni diferite — Cluj, Iasi, Timisoara, Brasov — plus Constanta, gasita
prin bucla de descoperire (GraphQL pe lat/lon -> `city_page` -> SSR pe ID).

ACOPERIREA DE AZI: 47 din 51 de ancore au ID. Cele 4 fara ID pornesc scara direct de
la GraphQL, exact ca inainte de FBS-2.

STATUTUL ID-URILOR NU E UNIFORM, si asta conteaza mai mult decat numarul:

  ·  5 MASURATE DIRECT ca ancoreaza corect — Cluj-Napoca, Iasi, Timisoara, Brasov
     (FBS-0b/0c) si Constanta (prin bucla de descoperire).
  · 12 VALIDATE la FBS-2b faza A: cate o cerere SSR pe fiecare, cu Jaccard MAXIM
     0.171 pe 78 de perechi si ZERO localitati din semnatura de „ignorat".
  ·  1 NEVALIDABIL geografic — Bucuresti. Nu e o scapare, e o imposibilitate: acolo
     setul corect si setul implicit COINCID, deci nicio masuratoare geografica nu le
     poate deosebi. ID-ul rezolva la o pagina valida, atat.
  · 29 RECOLTATE la FBS-2b faza B si NEVALIDATE individual. Prior-ul e bun — metoda
     de recoltare a dat 13 din 13 corecte cand a fost verificata — dar un prior NU e
     o masuratoare. Cine se bazeaza pe ele trebuie sa stie asta.

DE CE CELE 4 RAMAN FARA ID (nu e rest de lucru, e rezultat masurat):

  `campeni`, `miercurea-ciuc`, `moldova-noua` au fost interogate DIRECT pe lat/lon-ul
  propriu la FBS-2b si tot nu si-au gasit `city_page`-ul: rezultatele din zona lor vin
  din orase vecine mai mari. Interpretarea e ca acele localitati nu au `city_page`
  propriu in Marketplace, sau au unul fara oferta. NU le mai cauta — s-au cheltuit
  deja cereri ca sa aflam asta.

  `satu-mare` e alt caz, si mai instructiv: ROMANIA ARE DOUA LOCALITATI „Satu Mare".
  Recolta a produs AMBELE — `104009386303557` pentru „Satu Mare, Harghita" (comuna,
  la 272 km de ancora) si `112768845403364` pentru „Satu Mare" (resedinta de judet,
  recoltat langa Sighetu Marmatiei). Potrivirea pe nume le confunda, iar tie-break-ul
  „primul castiga" l-a ales pe cel GRESIT. Niciunul nu s-a scris: al doilea e
  plauzibil, dar plauzibil nu e masurat. Se rezolva cu o singura cerere de validare.

REGULA CARE A PRINS-O, si care nu se scoate: cand `display_name` poarta si judetul,
el se verifica INCRUCISAT cu `Ancora.judet`. Potrivirea doar pe nume trece peste
omonime, iar un ID gresit ancoreaza TACIT in alt oras — modul de esec pe care l-au
masurat trei sonde.

NU SE ATRIBUIE NICIODATA UN ID PRIN PROXIMITATE GEOGRAFICA. Pentru un oras mic,
rezultatele vin din orase vecine mai mari, deci un `city_page` recoltat langa ancora X
poate fi foarte bine al lui Y. Fara potrivire exacta pe nume (plus judet, cand exista),
ancora ramane fara ID.

Niciun ID nu e retastat din memorie: toate vin din dump-urile sondelor
(`dumps_fbs0c/reconciliere.json`, `dumps_fbs0c/raport.json`,
`dumps_fbs2b/descoperite.json`), scrise de un script care verifica la scriere.
"""
import math
from dataclasses import dataclass
from typing import Iterable, Optional

from app.services.log_manager import log_manager

RAZA_KM: float = 65.0


@dataclass(frozen=True)
class Ancora:
    slug: str            # identificator intern stabil (cheie in fb_scan_state la FB-3)
    nume: str
    judet: str           # cod de doua litere; "B" pentru Bucuresti
    lat: float
    lon: float
    tier: int            # 1 metropola, 2 resedinta de judet, 3 umplere
    # ID-ul NUMERIC de locatie Facebook (`city_page.id`), pentru calea SSR — care de
    # la FBS-2 e treapta 1, nu rezerva. `None` = ancora merge doar pe GraphQL.
    city_page_id: Optional[str] = None


ANCORE: tuple[Ancora, ...] = (
    # ── Tier 1: metropole (15) ───────────────────────────────────────────────
    Ancora("bucuresti", "București", "B", 44.4325, 26.1025, 1, city_page_id="114304211920174"),
    Ancora("cluj-napoca", "Cluj-Napoca", "CJ", 46.7712, 23.6236, 1, city_page_id="109529709065736"),
    Ancora("timisoara", "Timișoara", "TM", 45.7489, 21.2087, 1, city_page_id="107982459236366"),
    Ancora("iasi", "Iași", "IS", 47.1585, 27.6014, 1, city_page_id="101882609853782"),
    Ancora("constanta", "Constanța", "CT", 44.1598, 28.6348, 1, city_page_id="110967512261687"),
    Ancora("craiova", "Craiova", "DJ", 44.3302, 23.7949, 1, city_page_id="109365729090108"),
    Ancora("brasov", "Brașov", "BV", 45.6427, 25.5887, 1, city_page_id="114791928537378"),
    Ancora("galati", "Galați", "GL", 45.4353, 28.0080, 1, city_page_id="109927892369958"),
    Ancora("ploiesti", "Ploiești", "PH", 44.9469, 26.0367, 1, city_page_id="114992985184906"),
    Ancora("oradea", "Oradea", "BH", 47.0465, 21.9189, 1, city_page_id="109394502411507"),
    Ancora("braila", "Brăila", "BR", 45.2692, 27.9575, 1, city_page_id="106551422714439"),
    Ancora("arad", "Arad", "AR", 46.1866, 21.3123, 1, city_page_id="106334316072023"),
    Ancora("pitesti", "Pitești", "AG", 44.8565, 24.8692, 1, city_page_id="107982395900869"),
    Ancora("sibiu", "Sibiu", "SB", 45.7983, 24.1256, 1, city_page_id="106314962738289"),
    Ancora("bacau", "Bacău", "BC", 46.5670, 26.9146, 1, city_page_id="111819922169363"),

    # ── Tier 2: resedinte de judet (26) ──────────────────────────────────────
    Ancora("targu-mures", "Târgu Mureș", "MS", 46.5425, 24.5579, 2, city_page_id="114955601850928"),
    Ancora("baia-mare", "Baia Mare", "MM", 47.6573, 23.5681, 2, city_page_id="107823719245239"),
    Ancora("buzau", "Buzău", "BZ", 45.1500, 26.8333, 2, city_page_id="111612365532672"),
    Ancora("botosani", "Botoșani", "BT", 47.7486, 26.6694, 2, city_page_id="108107975889775"),
    Ancora("satu-mare", "Satu Mare", "SM", 47.7900, 22.8858, 2),
    Ancora("ramnicu-valcea", "Râmnicu Vâlcea", "VL", 45.1047, 24.3754, 2, city_page_id="109401689086893"),
    Ancora("suceava", "Suceava", "SV", 47.6514, 26.2556, 2, city_page_id="104058669632145"),
    Ancora("piatra-neamt", "Piatra Neamț", "NT", 46.9275, 26.3708, 2, city_page_id="115600705120096"),
    Ancora("drobeta", "Drobeta-Turnu Severin", "MH", 44.6369, 22.6597, 2, city_page_id="113411705337021"),
    Ancora("focsani", "Focșani", "VN", 45.6966, 27.1863, 2, city_page_id="116325158378085"),
    Ancora("targu-jiu", "Târgu Jiu", "GJ", 45.0353, 23.2745, 2, city_page_id="108259509195550"),
    Ancora("tulcea", "Tulcea", "TL", 45.1710, 28.7910, 2, city_page_id="112075222143137"),
    Ancora("targoviste", "Târgoviște", "DB", 44.9250, 25.4567, 2, city_page_id="113035492056720"),
    Ancora("deva", "Deva", "HD", 45.8833, 22.9000, 2, city_page_id="108543549177138"),
    Ancora("zalau", "Zalău", "SJ", 47.1911, 23.0572, 2, city_page_id="110614302293305"),
    Ancora("sfantu-gheorghe", "Sfântu Gheorghe", "CV", 45.8667, 25.7833, 2, city_page_id="108381545848629"),
    Ancora("vaslui", "Vaslui", "VS", 46.6407, 27.7276, 2, city_page_id="107958172559999"),
    Ancora("giurgiu", "Giurgiu", "GR", 43.9037, 25.9699, 2, city_page_id="109547692396313"),
    # COLIZIUNE INTERNATIONALA (masurat la FB-0): `alexandria` era slug valid pe
    # Facebook, dar rezolva spre ALTA Alexandria si dadea 0 rezultate la termen
    # romanesc. NU se revalideaza ca slug — documentat ca sa nu-l "redescopere"
    # cineva. Un `city_page_id` NUMERIC nu are insa cum sa aiba coliziunea asta,
    # deci Alexandria intra normal in descoperirea de la FBS-2b.
    Ancora("alexandria", "Alexandria", "TR", 43.9800, 25.3339, 2, city_page_id="106314682740651"),
    Ancora("miercurea-ciuc", "Miercurea Ciuc", "HR", 46.3600, 25.8017, 2),
    Ancora("slobozia", "Slobozia", "IL", 44.5639, 27.3661, 2, city_page_id="104976886205479"),
    Ancora("calarasi", "Călărași", "CL", 44.2058, 27.3306, 2, city_page_id="110489242312814"),
    Ancora("resita", "Reșița", "CS", 45.3008, 21.8892, 2, city_page_id="105802619460381"),
    Ancora("bistrita", "Bistrița", "BN", 47.1350, 24.4967, 2, city_page_id="106530449382782"),
    Ancora("slatina", "Slatina", "OT", 44.4300, 24.3708, 2, city_page_id="114830468529948"),
    Ancora("alba-iulia", "Alba Iulia", "AB", 46.0667, 23.5833, 2, city_page_id="106088726089413"),

    # ── Tier 3: umplere (10) — judetul e cel in care se afla localitatea ─────
    Ancora("calafat", "Calafat", "DJ", 43.9900, 22.9400, 3, city_page_id="105595172806556"),
    Ancora("corabia", "Corabia", "OT", 43.7700, 24.5000, 3, city_page_id="106144929416759"),
    Ancora("moldova-noua", "Moldova Nouă", "CS", 44.7300, 21.6600, 3),
    Ancora("nadlac", "Nădlac", "AR", 46.1667, 20.7500, 3, city_page_id="108611502502567"),
    Ancora("stei", "Ștei", "BH", 46.5400, 22.4600, 3, city_page_id="110240315665911"),
    Ancora("campeni", "Câmpeni", "AB", 46.3700, 23.0500, 3),
    Ancora("petrosani", "Petroșani", "HD", 45.4167, 23.3667, 3, city_page_id="108471015850658"),
    Ancora("sighetu-marmatiei", "Sighetu Marmației", "MM", 47.9300, 23.8900, 3, city_page_id="111843095501216"),
    Ancora("borsa", "Borșa", "MM", 47.6553, 24.6620, 3, city_page_id="100240690017068"),
    Ancora("vatra-dornei", "Vatra Dornei", "SV", 47.3480, 25.3600, 3, city_page_id="109489152402375"),
)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanta pe sfera intre doua puncte, in km (R = 6371.0)."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def dupa_slug(slug: str) -> Optional[Ancora]:
    """Ancora cu slug-ul dat, sau None."""
    if not slug:
        return None
    tinta = slug.strip().lower()
    for a in ANCORE:
        if a.slug == tinta:
            return a
    return None


def _fara_dezactivate(alese: Iterable[Ancora],
                      dezactivate: Iterable[str]) -> tuple[Ancora, ...]:
    """Scade slug-urile dezactivate, pastrand ordinea din ANCORE."""
    scoase = {str(s).strip().lower() for s in (dezactivate or ()) if s}
    return tuple(a for a in alese if a.slug not in scoase)


def _judet(cod: str, dezactivate) -> tuple[Ancora, ...]:
    cod = cod.strip().upper()
    in_judet = [a for a in ANCORE if a.judet == cod]
    if not in_judet:
        # Cod necunoscut: acelasi tratament ca un scope stricat — se scaneaza
        # national, nu se tace. Vezi nota de fail-open din `selecteaza`.
        log_manager.emit("radar", "WARN",
            f"Facebook ancore: judetul '{cod}' nu are nicio ancora in registru — "
            f"cad pe 'national'")
        return _fara_dezactivate(ANCORE, dezactivate)

    alese = []
    for a in ANCORE:
        if a.judet == cod or any(
                haversine_km(a.lat, a.lon, b.lat, b.lon) < RAZA_KM for b in in_judet):
            alese.append(a)
    return _fara_dezactivate(alese, dezactivate)


def _ancore_explicite(lista: str, dezactivate) -> tuple[Ancora, ...]:
    cerute, necunoscute = set(), []
    for bucata in lista.split(","):
        bucata = bucata.strip().lower()
        if not bucata:
            continue
        if dupa_slug(bucata) is None:
            necunoscute.append(bucata)
        else:
            cerute.add(bucata)
    if necunoscute:
        log_manager.emit("radar", "WARN",
            f"Facebook ancore: slug-uri necunoscute, ignorate: {', '.join(necunoscute)}")
    alese = _fara_dezactivate([a for a in ANCORE if a.slug in cerute], dezactivate)
    if not alese:
        # Nu se cade pe national: aici utilizatorul a numit EXPLICIT ancore, deci o
        # lista goala e o cerere goala, nu un scope neinteligibil. Dar nu tace.
        log_manager.emit("radar", "WARN",
            "Facebook ancore: lista explicita nu a lasat nicio ancora valida")
    return alese


def selecteaza(scope: str, dezactivate: Iterable[str] = ()) -> tuple[Ancora, ...]:
    """Ancorele pentru un scope, in ordinea din registru.

    Formate: `national` (sau gol/None), `tier1`, `judet:COD`, `ancore:slug,slug`.

    FAIL-OPEN pe acoperire: un scope pe care nu-l intelegem cade pe `national`, cu
    WARN. Un keyword cu scope stricat trebuie sa scaneze, nu sa taca — o scanare
    prea larga se vede in log si se corecteaza, una care nu se intampla deloc nu se
    vede pana cand cineva observa ca lipsesc anunturi.
    """
    s = (scope or "").strip().lower()

    if not s or s == "national":
        return _fara_dezactivate(ANCORE, dezactivate)
    if s == "tier1":
        return _fara_dezactivate([a for a in ANCORE if a.tier == 1], dezactivate)
    if s.startswith("judet:"):
        return _judet(s[len("judet:"):], dezactivate)
    if s.startswith("ancore:"):
        return _ancore_explicite(s[len("ancore:"):], dezactivate)

    log_manager.emit("radar", "WARN",
        f"Facebook ancore: scope necunoscut '{scope}' — cad pe 'national'")
    return _fara_dezactivate(ANCORE, dezactivate)
