"""REG-1/REG-2 — registrul declarativ de magazine.

Un test pe FORMA registrului (fiecare intrare isi respecta contractul de campuri)
si unul pe IZOLAREA derivarilor. Testele de egalitate cu structurile istorice au
existat doar cat timp registrul a mers in paralel cu literalele (REG-1); dupa
comutarea de la REG-2 ele ar compara derivarea cu ea insasi, deci s-au sters.
"""
import re

import pytest

from app.services import product_page_extractor as ppe
from app.services import scraper_service as ss
from app.services.shop_registry import (
    SHOP_REGISTRY,
    domain_overrides,
    impersonate_overrides,
    shopify_domains,
    validated_domains,
)

_CAMPURI_OBLIGATORII = ("label", "category", "country", "delivery", "method", "status", "notes")

_CATEGORII = {"electronice", "fashion", "sneakers", "incaltaminte", "tcg",
              "outdoor", "jucarii", "foto", "beauty",
              "general",    # ELF-2 — magazine generaliste (elefant)
              "bricolaj",   # G2F-2 — unelte/atelier (toolnation; hornbach/action urmeaza)
              "pet",        # G2F-4 — pet shop (zooplus; fressnapf e in valul de browser)
              "biciclete",  # G2F-8 — biciclete & piese (biciclop vinde piese; veloteca e inaccesibil)
              "bijuterii-ceasuri"}  # G2F-8 — bijuterii & ceasuri (cellini; bbcollection parcat)
_LIVRARI = {"ro_confirmed", "ro_storefront", "b2b_only", "unconfirmed"}
_METODE = {"jsonld", "og", "microdata", "custom", "shopify", "browser"}
_STARI = {"validated", "probed", "planned", "watchlist"}


def test_registru_intrari_valide():
    assert SHOP_REGISTRY, "registrul nu poate fi gol"

    for domain, meta in SHOP_REGISTRY.items():
        # Cheia e domeniul in forma folosita de _domain_of, care taie doar "www.".
        assert not domain.startswith("www."), f"{domain}: cheia nu poate incepe cu www."

        for camp in _CAMPURI_OBLIGATORII:
            assert camp in meta, f"{domain}: lipseste campul {camp}"
            assert isinstance(meta[camp], str) and meta[camp].strip(), \
                f"{domain}: campul {camp} trebuie sa fie str nevid"

        assert meta["category"] in _CATEGORII, f"{domain}: category={meta['category']}"
        assert meta["delivery"] in _LIVRARI, f"{domain}: delivery={meta['delivery']}"
        assert meta["method"] in _METODE, f"{domain}: method={meta['method']}"
        assert meta["status"] in _STARI, f"{domain}: status={meta['status']}"

        if "impersonate" in meta:
            assert isinstance(meta["impersonate"], str) and meta["impersonate"].strip(), \
                f"{domain}: impersonate trebuie sa fie str nevid"
        if "overrides" in meta:
            assert isinstance(meta["overrides"], dict) and meta["overrides"], \
                f"{domain}: overrides trebuie sa fie dict nevid"
        if "currency" in meta:
            assert isinstance(meta["currency"], str) and re.fullmatch(r"[A-Z]{3}", meta["currency"]), \
                f"{domain}: currency trebuie sa fie cod ISO din 3 litere mari"
        # LOT1 — singura politica de identitate definita deocamdata.
        if "url_identity" in meta:
            assert meta["url_identity"] == "exact", \
                f"{domain}: url_identity accepta doar \"exact\" (are {meta['url_identity']!r})"
        if "vat_prices" in (meta.get("overrides") or {}):
            assert isinstance(meta["overrides"]["vat_prices"], bool), \
                f"{domain}: overrides.vat_prices trebuie sa fie boolean"
        # BR-1 — profilul de rulare al harness-ului are sens DOAR pe method
        # "browser". Pe orice alta metoda campurile ar fi moarte: nimeni nu le
        # citeste, iar prezenta lor ar sugera fals ca domeniul se deschide in
        # browser (exact genul de divergenta tacuta pentru care exista registrul).
        if "headed" in meta:
            assert meta["method"] == "browser", \
                f"{domain}: headed e permis doar pe method=browser"
            assert isinstance(meta["headed"], bool), \
                f"{domain}: headed trebuie sa fie boolean"
        # RATE-1 — `min_fetch_interval_s` NU mai e limitat la browser, iar garda
        # s-a schimbat ODATA cu mecanismul, in acelasi commit.
        #
        # Istoria conteaza, ca sa nu para o relaxare: la BR-1 campul a fost inchis
        # pe method=browser fiindca ACOLO era singurul consumator
        # (`browser_fetch.fetch_browser_html`), iar pe alte metode ar fi fost un
        # camp MORT — prezenta lui ar fi sugerat fals o protectie inexistenta.
        # Argumentul acela era despre CONSUM, nu despre semantica: „secunde minime
        # intre cereri" are inteles pe orice cale. La RATE-1 consumatorul HTTP
        # exista (poarta `_fetch_shop_url_guarded`), deci campul nu mai e mort
        # nicaieri si restrictia si-a pierdut temeiul. `headed` ramane browser-only:
        # el chiar n-are inteles fara browser.
        if "min_fetch_interval_s" in meta:
            assert isinstance(meta["min_fetch_interval_s"], int) \
                and not isinstance(meta["min_fetch_interval_s"], bool) \
                and meta["min_fetch_interval_s"] > 0, \
                f"{domain}: min_fetch_interval_s trebuie sa fie int pozitiv"
        # G2F-6 — spre deosebire de cele doua de mai sus, flagul asta NU se
        # restrange la o metoda: e consumat de `parse_product_html`, care ruleaza
        # pe orice cale (inclusiv pe HTML-ul randat al unui domeniu "browser").
        # Se valideaza deci doar valoarea, ca sa nu intre scrieri gresite tacute.
        if "ldjson_availability" in meta:
            assert meta["ldjson_availability"] == "untrusted",                 (f"{domain}: ldjson_availability accepta doar \"untrusted\" "
                 f"(are {meta['ldjson_availability']!r})")


def test_derivarile_intorc_obiecte_proaspete():
    """Fiecare apel da un obiect NOU, iar mutarea lui nu atinge consumatorii.

    Suita existenta monkeypatcheaza copiile de la nivel de modul (ex. adauga un
    domeniu de test in VALIDATED_DOMAINS). Daca derivarea ar intoarce o referinta
    in registru, mutatia s-ar propaga in registru si de acolo in ceilalti
    consumatori, scurgandu-se intre teste.
    """
    for derivare in (validated_domains, domain_overrides, impersonate_overrides):
        intai, apoi = derivare(), derivare()
        assert intai == apoi, f"{derivare.__name__}: apeluri succesive dau valori diferite"
        assert intai is not apoi, f"{derivare.__name__}: a intors aceeasi referinta"

    domenii = validated_domains()
    domenii.add("magazin-de-test.example")
    assert "magazin-de-test.example" not in ppe.VALIDATED_DOMAINS
    assert "magazin-de-test.example" not in validated_domains()

    overrides = domain_overrides()
    overrides["magazin-de-test.example"] = {"price_selector": ".fals"}
    for payload in overrides.values():
        payload["currency"] = "XXX"  # si payload-ul interior trebuie sa fie o copie
    assert "magazin-de-test.example" not in ppe.DOMAIN_OVERRIDES
    assert all("currency" not in p for p in ppe.DOMAIN_OVERRIDES.values())
    assert all("currency" not in p for p in domain_overrides().values())

    trepte = impersonate_overrides()
    trepte["magazin-de-test.example"] = "firefox135"
    assert "magazin-de-test.example" not in ss._IMPERSONATE_OVERRIDES
    assert "magazin-de-test.example" not in impersonate_overrides()


def test_shopify_cere_moneda():
    """Moneda e OBLIGATORIE pe intrarile shopify: payload-ul Ajax nu o poarta, deci
    registrul e singura ei sursa. O intrare shopify fara `currency` ar produce un
    rezultat cu currency=None, adica un pret fara unitate — exact bugul tacut pe
    care campul il previne."""
    shopify = shopify_domains()
    assert shopify, "registrul trebuie sa aiba cel putin un magazin shopify"

    for domain in shopify:
        meta = SHOP_REGISTRY[domain]
        moneda = meta.get("currency")
        assert isinstance(moneda, str) and re.fullmatch(r"[A-Z]{3}", moneda), \
            f"{domain}: intrare shopify fara currency valid (are {moneda!r})"

    intai, apoi = shopify_domains(), shopify_domains()
    assert intai == apoi
    assert intai is not apoi


def test_harta_de_impersonate_e_pinuita():
    """ELF-2: harta COMPLETA de override-uri de amprenta, domeniu cu domeniu.

    De ce pinuita si nu doar validata ca forma: un override sters trece suita fara
    sa clipeasca (suita e offline) si reapare abia in PRODUCTIE, ca
    `ProductExtractionError(reason="challenge")` pe fiecare extractie de pe
    domeniul respectiv. Exact asa s-a manifestat elefant.ro la ELF-2 — sonda il
    validase de cinci ori in aceeasi zi, fiindca sondele merg pe `chrome`
    (DEFAULT_IMPERSONATE), iar productia pe alt profil implicit.

    Literalele de profil sunt permise AICI: garda
    test_niciun_profil_hardcodat_vechi_in_app scaneaza doar `backend/app/**`.
    """
    assert impersonate_overrides() == {
        "43einhalb.com": "firefox135",   # ACCESS-2
        "flanco.ro": "firefox135",       # CONTENT-2
        "notino.ro": "firefox135",       # LOT4
        "elefant.ro": "chrome",          # ELF-2 — 403 Cloudflare pe implicit, 200 pe chrome
        "cyberport.at": "chrome",        # G2B-2 — challenge Cloudflare pe implicit, 200 pe chrome
        # IMP-2 — 0/4 blocat pe chrome131 vs 2/4 pe chrome146: INTERMITENT, nu
        # determinist. Singurul domeniu din 73 care a regresat la alinierea
        # poartei pe profilul centralizat. De RE-MASURAT la urmatorul profil:
        # daca intre timp devine stabil, override-ul iese.
        "sivasdescalzo.com": "chrome131",
    }

    # Si harta chiar ajunge la fetch: rezolvarea per-URL a productiei o onoreaza,
    # inclusiv pe subdomeniu. Fara asta, harta ar putea fi corecta si ocolita.
    assert ss._impersonate_for("https://www.elefant.ro/produs_abc") == "chrome"
    assert ss._impersonate_for("https://elefant.ro/produs_abc") == "chrome"


# ── RATE-1: intervalul minim pe poarta HTTP ──────────────────────────────────
#
# Testele stau AICI, langa garda pe care o insotesc, ca perechea „mecanism +
# contract" sa se citeasca dintr-o bucata. Ceasul si somnul sunt AMBELE
# monkeypatch-uite: suita nu are voie sa doarma nici macar o secunda reala.


@pytest.fixture
def ceas_fals(monkeypatch):
    """Ceas monoton controlat + `sleep` care doar avanseaza ceasul."""
    from app.services import scraper_service as ss

    stare = {"acum": 1_000.0, "dormit": []}

    def _monotonic():
        return stare["acum"]

    def _sleep(secunde):
        stare["dormit"].append(secunde)
        stare["acum"] += secunde

    monkeypatch.setattr(ss.time, "monotonic", _monotonic)
    monkeypatch.setattr(ss.time, "sleep", _sleep)
    monkeypatch.setattr(ss, "_ULTIMA_CERERE_PE_DOMENIU", {})
    stare["modul"] = ss
    return stare


def test_rate_a_doua_cerere_pe_acelasi_domeniu_asteapta_diferenta(ceas_fals,
                                                                  monkeypatch):
    """Doua cereri consecutive pe un domeniu cu interval: a doua asteapta restul."""
    ss = ceas_fals["modul"]
    monkeypatch.setattr(ss, "_MIN_FETCH_INTERVALE", {"action.com": 90})

    assert ss._asteapta_intervalul("https://www.action.com/ro-ro/p/1/x/") == 0.0
    ceas_fals["acum"] += 10          # au trecut 10s din 90
    asteptat = ss._asteapta_intervalul("https://www.action.com/ro-ro/p/2/y/")

    assert asteptat == pytest.approx(80.0)
    assert ceas_fals["dormit"] == [pytest.approx(80.0)]


def test_rate_domeniul_fara_camp_nu_asteapta_niciodata(ceas_fals, monkeypatch):
    """Zero cost pe restul catalogului — nici somn, nici stampila."""
    ss = ceas_fals["modul"]
    monkeypatch.setattr(ss, "_MIN_FETCH_INTERVALE", {"action.com": 90})

    for _ in range(5):
        assert ss._asteapta_intervalul("https://www.forit.ro/produs-x") == 0.0

    assert ceas_fals["dormit"] == []
    assert "forit.ro" not in ss._ULTIMA_CERERE_PE_DOMENIU


def test_rate_domenii_diferite_sunt_independente(ceas_fals, monkeypatch):
    """Intervalul e PER DOMENIU: unul care asteapta nu tine celalalt pe loc."""
    ss = ceas_fals["modul"]
    monkeypatch.setattr(ss, "_MIN_FETCH_INTERVALE",
                        {"action.com": 90, "sephora.ro": 180})

    assert ss._asteapta_intervalul("https://www.action.com/a") == 0.0
    assert ss._asteapta_intervalul("https://www.sephora.ro/b") == 0.0
    assert ceas_fals["dormit"] == []

    assert ss._asteapta_intervalul("https://www.action.com/c") == pytest.approx(90.0)


def test_rate_dupa_scurgerea_naturala_a_intervalului_nu_se_asteapta(ceas_fals,
                                                                    monkeypatch):
    """Daca timpul a trecut oricum (alte domenii, parsare, retea), nu se doarme."""
    ss = ceas_fals["modul"]
    monkeypatch.setattr(ss, "_MIN_FETCH_INTERVALE", {"action.com": 90})

    ss._asteapta_intervalul("https://www.action.com/a")
    ceas_fals["acum"] += 120         # mai mult decat intervalul

    assert ss._asteapta_intervalul("https://www.action.com/b") == 0.0
    assert ceas_fals["dormit"] == []


def test_rate_subdomeniul_mosteneste_dar_sufixul_inselator_nu(ceas_fals,
                                                              monkeypatch):
    """Potrivire suffix-safe, ca la `_impersonate_for` si la allow-list-ul C-14."""
    ss = ceas_fals["modul"]
    monkeypatch.setattr(ss, "_MIN_FETCH_INTERVALE", {"action.com": 90})

    assert ss._asteapta_intervalul("https://shop.action.com/x") == 0.0
    # Acelasi domeniu de baza -> a doua cerere asteapta.
    assert ss._asteapta_intervalul("https://www.action.com/y") == pytest.approx(90.0)
    # Sufix inselator: alt domeniu, deci nicio asteptare mostenita.
    ceas_fals["dormit"].clear()
    assert ss._asteapta_intervalul("https://evil-action.com.attacker.net/z") == 0.0
    assert ceas_fals["dormit"] == []


def test_rate_harta_derivata_din_registru_contine_action():
    """Legatura registru -> mecanism e reala, nu doar documentata."""
    from app.services import scraper_service as ss
    from app.services.shop_registry import SHOP_REGISTRY

    assert SHOP_REGISTRY["action.com"]["min_fetch_interval_s"] == 90
    assert ss._MIN_FETCH_INTERVALE.get("action.com") == 90
    # Derivarea ia TOATE intrarile cu camp, indiferent de metoda (contractul nou).
    asteptat = {d: m["min_fetch_interval_s"] for d, m in SHOP_REGISTRY.items()
                if m.get("min_fetch_interval_s")}
    assert ss._MIN_FETCH_INTERVALE == asteptat


def test_rate_calea_browser_ramane_neatinsa():
    """Browser-ul isi citeste campul prin `browser_profile_of`, ca inainte.

    Mecanismul HTTP e PARALEL, nu inlocuitor: sephora ramane pe refuz-sub-prag,
    action pe asteapta-diferenta.
    """
    from app.services.shop_registry import browser_profile_of

    assert browser_profile_of("sephora.ro") == {"headed": True,
                                                "min_fetch_interval_s": 180}
    # action nu e domeniu de browser: profilul lui de harness ramane cel implicit.
    assert browser_profile_of("action.com")["headed"] is False
