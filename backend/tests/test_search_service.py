"""SEARCH-1b — serviciul generic de cautare.

Fara retea: poarta (`_fetch_shop_url_guarded`) si scraperele custom se
monkeypatcheaza IN `search_service`, nu in modulele de origine — asa se testeaza
exact legatura pe care o foloseste serviciul, si nu se scurge nimic in alte teste.

Fixture-urile sunt fragmente MICI scrise dupa forma MASURATA la SEARCH-0
(`scripts/diagnostics/search0_raport.md`), nu dump-uri copiate: un payload de 2 MB
n-ar spune mai mult decat doua produse alese pentru cazurile care conteaza.
"""
import json

import pytest

from app.services import search_service as S


class _Raspuns:
    """Minimul din `curl_cffi.Response` pe care il atinge serviciul."""

    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


@pytest.fixture(autouse=True)
def fara_jurnal(monkeypatch):
    """`_emit_catalog` scrie in jurnalul global; il inlocuim cu un recorder, ca
    testele sa nu depinda de starea lui si sa poata verifica apelurile."""
    apeluri = []
    monkeypatch.setattr(S, "_emit_catalog",
                        lambda label, query, produse: apeluri.append(
                            (label, query, list(produse or []))))
    return apeluri


class _JurnalFals:
    """Recorder pentru `log_manager.emit`, cu aceeasi semnatura."""

    def __init__(self):
        self.linii = []

    def emit(self, modul, nivel, mesaj):
        self.linii.append((modul, nivel, mesaj))


@pytest.fixture(autouse=True)
def jurnal(monkeypatch):
    """SEARCH-1c — `log_manager` e global; fara recorder, testele de eroare ar scrie
    in bufferul real si s-ar scurge unele in altele."""
    fals = _JurnalFals()
    monkeypatch.setattr(S, "log_manager", fals)
    return fals


def _poarta(monkeypatch, raspuns):
    """Fixeaza raspunsul portii si inregistreaza URL-urile cerute."""
    cerute = []

    def fals(url, *, headers, timeout):
        cerute.append(url)
        return raspuns

    monkeypatch.setattr(S, "_fetch_shop_url_guarded", fals)
    return cerute


# ── shopify ──────────────────────────────────────────────────────────────────

def _payload_shopify(produse):
    return json.dumps({"resources": {"results": {"products": produse}}})


# Forma exacta masurata la SEARCH-0: `price` e STRING, referinta e
# `compare_at_price_min` (NU `compare_at_price`, care nu exista), iar "0.00"
# inseamna „fara reducere".
_SHOPIFY_CU_REDUCERE = {
    "title": "Pokemon TCG - World Champions Decks 2025 - Pult Bomb",
    "handle": "pokemon-tcg-world-champions-decks-2025-pult-bomb",
    "price": "134.10",
    "compare_at_price_min": "149.00",
    "compare_at_price_max": "149.00",
    "available": True,
    "url": "/products/pokemon-tcg-wcd-2025-pult-bomb?_pos=1&_psq=pokemon&_ss=e",
    "image": "https://cdn.shopify.com/s/files/1/x/pult.jpg",
}
_SHOPIFY_FARA_REDUCERE = {
    "title": "Pokemon TCG - Surging Sparks Booster",
    "handle": "pokemon-tcg-surging-sparks-booster",
    "price": "29.90",
    "compare_at_price_min": "0.00",
    "compare_at_price_max": "0.00",
    "available": False,
    "url": "/products/pokemon-tcg-surging-sparks?_pos=2&_psq=pokemon&_ss=e",
    "image": "https://cdn.shopify.com/s/files/1/x/sparks.jpg",
}


def test_shopify_mapeaza_forma_masurata(monkeypatch):
    cerute = _poarta(monkeypatch, _Raspuns(_payload_shopify(
        [_SHOPIFY_CU_REDUCERE, _SHOPIFY_FARA_REDUCERE])))

    raspuns = S.search("redgoblin.ro", "pokemon")

    assert raspuns["status"] == "ok"
    assert raspuns["count"] == 2
    assert raspuns["kind"] == "shopify"
    # Plafonul e 10; doua rezultate nu inseamna „mai sunt".
    assert raspuns["truncated"] is False

    primul, al_doilea = raspuns["results"]
    assert primul["price"] == 134.10
    assert primul["original_price"] == 149.0
    assert primul["is_on_sale"] is True
    # Moneda vine din REGISTRU: payload-ul Shopify nu o poarta.
    assert primul["currency"] == "RON"
    assert primul["source"] == "redgoblin.ro"
    assert primul["source_url"] == (
        "https://redgoblin.ro/products/pokemon-tcg-wcd-2025-pult-bomb"
        "?_pos=1&_psq=pokemon&_ss=e")
    assert primul["in_stock"] is True
    assert (primul["ean"], primul["sku"],
            primul["category"], primul["subcategory"]) == (None, None, None, None)

    # "0.00" NU e o reducere de 100%.
    assert al_doilea["original_price"] is None
    assert al_doilea["is_on_sale"] is False
    assert al_doilea["in_stock"] is False

    assert cerute == [
        "https://redgoblin.ro/search/suggest.json?q=pokemon"
        "&resources[type]=product&resources[limit]=10"]
    assert raspuns["more_url"] == "https://redgoblin.ro/search?q=pokemon&type=product"


def test_shopify_zece_rezultate_e_trunchiat(monkeypatch):
    """Plafonul e FIX la 10 (masurat: limit=50 da acelasi raspuns), deci exact 10
    rezultate inseamna „magazinul are probabil mai multe"."""
    _poarta(monkeypatch, _Raspuns(_payload_shopify(
        [dict(_SHOPIFY_CU_REDUCERE, title=f"Produs {i}") for i in range(10)])))

    raspuns = S.search("redgoblin.ro", "pokemon")
    assert raspuns["count"] == 10
    assert raspuns["truncated"] is True


def test_shopify_zero_produse_e_empty(monkeypatch):
    """Controlul negativ masurat: `products: []` pe 200, nu 4xx."""
    _poarta(monkeypatch, _Raspuns(_payload_shopify([])))

    raspuns = S.search("redgoblin.ro", "xqzvwk7731")
    assert raspuns["status"] == "empty"
    assert raspuns["results"] == [] and raspuns["count"] == 0


# ── vtex ─────────────────────────────────────────────────────────────────────

def _produs_vtex(nume, pret, list_price, disponibil):
    return {
        "productName": nume,
        "linkText": nume.lower().replace(" ", "-"),
        "link": f"https://www.f64.ro/{nume.lower().replace(' ', '-')}/p",
        "items": [{
            "images": [{"imageUrl": f"https://f64.example/{nume}.jpg"}],
            "sellers": [{"commertialOffer": {
                "Price": pret, "ListPrice": list_price,
                "IsAvailable": disponibil, "AvailableQuantity": 10,
            }}],
        }],
    }


def test_vtex_pastreaza_produsele_indisponibile(monkeypatch):
    """Controlul ca NU s-a folosit `_extrage_produse`.

    Acela sare produsele indisponibile, fiindca e scris pentru feed-ul de deal-uri.
    La o cautare, un produs epuizat e informatie: userul vrea sa stie ca magazinul il
    are in catalog. Daca refactorizarea ar trece pe `_extrage_produse`, testul asta
    pica — si asta e tot rostul lui.
    """
    _poarta(monkeypatch, _Raspuns(json.dumps([
        _produs_vtex("Sony Alpha A", 2699.99, 2999.99, True),
        _produs_vtex("Sony Alpha B", 89.0, 89.0, False),
    ]), status_code=206))                      # 206 e normal pe fereastra plina

    raspuns = S.search("f64.ro", "sony alpha")

    assert raspuns["status"] == "ok" and raspuns["count"] == 2
    primul, al_doilea = raspuns["results"]
    assert primul["price"] == 2699.99 and primul["original_price"] == 2999.99
    assert primul["currency"] == "RON"        # din catalog_api, nu din payload
    assert primul["source_url"] == "https://www.f64.ro/sony-alpha-a/p"
    assert primul["image_url"] == "https://f64.example/Sony Alpha A.jpg"

    assert al_doilea["in_stock"] is False, "produsul epuizat trebuie sa RAMANA"
    # ListPrice == Price nu e reducere.
    assert al_doilea["original_price"] is None


def test_vtex_fereastra_si_status_200(monkeypatch):
    cerute = _poarta(monkeypatch, _Raspuns(json.dumps(
        [_produs_vtex("X", 10.0, 10.0, True)]), status_code=200))

    S.search("f64.ro", "sony alpha", max_results=50)
    assert cerute == [
        "https://www.f64.ro/api/catalog_system/pub/products/search"
        "?ft=sony%20alpha&_from=0&_to=49"]


def test_vtex_lista_goala_e_empty(monkeypatch):
    _poarta(monkeypatch, _Raspuns("[]", status_code=200))
    raspuns = S.search("f64.ro", "xqzvwk7731")
    assert raspuns["status"] == "empty" and raspuns["count"] == 0


# ── descriptor ───────────────────────────────────────────────────────────────

# Fragment MIC, scris dupa markup-ul real al bergfreunde (SEARCH-0 §5c): pretul in
# `[data-codecept='currentPrice']`, referinta in `[data-codecept='strokePrice']`,
# cu spatiu insecabil si virgula zecimala, exact ca in dump.
_FRAGMENT_BERGFREUNDE = """
<ul>
  <li class="product-item">
    <a class="product-link" href="https://www.bergfreunde.eu/salomon-xa-pro-v8/"></a>
    <img src="https://www.bfgcdn.com/x/sol_702_pic1_1.jpg"/>
    <div class="product-title">Xa Pro V8 Winter CSWP Junior Winter boots</div>
    <span class="price high-light" data-codecept="currentPrice">€ 40,48</span>
    <span class="uvp" data-codecept="strokePrice">€ 89,95</span>
  </li>
  <li class="product-item">
    <a class="product-link" href="https://www.bergfreunde.eu/salomon-cross-8/"></a>
    <img src="https://www.bfgcdn.com/x/sol_502_pic1_1.jpg"/>
    <div class="product-title">Cross 8 Walking backpack</div>
    <span class="price high-light" data-codecept="currentPrice">€ 69,95</span>
  </li>
</ul>
"""


def test_descriptor_citeste_cardurile_reale(monkeypatch):
    cerute = _poarta(monkeypatch, _Raspuns(_FRAGMENT_BERGFREUNDE))

    raspuns = S.search("bergfreunde.eu", "salomon")

    assert raspuns["status"] == "ok" and raspuns["count"] == 2
    cu_reducere, fara_reducere = raspuns["results"]
    assert cu_reducere["name"] == "Xa Pro V8 Winter CSWP Junior Winter boots"
    assert cu_reducere["price"] == 40.48
    assert cu_reducere["original_price"] == 89.95
    assert cu_reducere["is_on_sale"] is True
    assert cu_reducere["currency"] == "EUR"     # mostenita din `listing`
    assert cu_reducere["source_url"] == "https://www.bergfreunde.eu/salomon-xa-pro-v8/"
    # Descriptorul de listare nu poarta stocul -> necunoscut, nu True.
    assert cu_reducere["in_stock"] is None

    assert fara_reducere["original_price"] is None
    assert fara_reducere["is_on_sale"] is False

    assert cerute == [
        "https://www.bergfreunde.eu/index.php?lang=10&cl=search&searchparam=salomon"]
    assert raspuns["more_url"] == cerute[0]


def test_descriptor_fara_selector_de_pret_pierde_tot(monkeypatch):
    """Esecul noriel din SEARCH-0, reprodus si pinuit.

    `extrage_carduri` arunca orice card fara pret valid. Daca descriptorul de cautare
    n-are selectorul potrivit — cazul real: selectorul paginii de REDUCERI aplicat pe
    o pagina de cautare — cardurile dispar in TACERE, chiar daca grila e plina.
    Rezultatul e `empty`, adica nedistinctibil de „magazinul n-are produsul", si de
    asta pretul se declara explicit in `search` (D6).
    """
    _poarta(monkeypatch, _Raspuns(_FRAGMENT_BERGFREUNDE))

    ciung = S.search_descriptor("bergfreunde.eu")
    ciung.pop("price_text")
    monkeypatch.setattr(S, "search_descriptor", lambda domain: ciung)

    raspuns = S.search("bergfreunde.eu", "salomon")
    assert raspuns["status"] == "empty"
    assert raspuns["count"] == 0


# ── custom ───────────────────────────────────────────────────────────────────

_PRODUS_CUSTOM = {
    "name": "Placa video RTX 5070", "price": 3499.0, "original_price": None,
    "is_on_sale": False, "currency": "RON", "source": "altex.ro",
    "source_url": "https://altex.ro/x", "image_url": None, "in_stock": True,
    "ean": None, "sku": "RTX5070", "category": "electronice", "subcategory": None,
}


def _scraper(monkeypatch, intoarce):
    monkeypatch.setitem(S._SCRAPERS_BY_SOURCE, "altex.ro",
                        lambda query, max_results: intoarce)


def test_custom_sentinela_message_devine_empty(monkeypatch):
    _scraper(monkeypatch, [{"message": "Nu s-au gasit produse pentru aceasta cautare.",
                            "source": "altex.ro"}])
    raspuns = S.search("altex.ro", "xqzvwk7731")
    assert raspuns["status"] == "empty"
    assert raspuns["results"] == [], "nicio sentinela nu are voie sa iasa din search()"


def test_custom_sentinela_error_devine_error(monkeypatch):
    _scraper(monkeypatch, [{"error": "Altex a returnat status 503"}])
    raspuns = S.search("altex.ro", "rtx 5070")
    assert raspuns["status"] == "error"
    assert raspuns["reason"] == "Altex a returnat status 503"
    assert raspuns["results"] == []


def test_custom_scoate_sentinelele_dintre_produse(monkeypatch):
    """Sentinela amestecata cu produse reale: produsele raman, sentinela pleaca."""
    _scraper(monkeypatch, [_PRODUS_CUSTOM, {"message": "ceva"}])
    raspuns = S.search("altex.ro", "rtx 5070")
    assert raspuns["status"] == "ok" and raspuns["count"] == 1
    assert raspuns["results"] == [_PRODUS_CUSTOM]


def test_custom_nu_atinge_poarta(monkeypatch):
    """Scraperele au fetch-ul lor (RETAIL-GATE-2); serviciul nu-l dubleaza."""
    cerute = _poarta(monkeypatch, _Raspuns("{}"))
    _scraper(monkeypatch, [_PRODUS_CUSTOM])
    S.search("altex.ro", "rtx 5070")
    assert cerute == []


# ── stari de esec ────────────────────────────────────────────────────────────

def test_poarta_none_da_blocked(monkeypatch):
    """Poarta NU distinge blocaj de timeout de eroare de retea — toate ies `None`,
    deci `blocked` e cel mai precis lucru care se poate spune."""
    _poarta(monkeypatch, None)
    raspuns = S.search("redgoblin.ro", "pokemon")
    assert raspuns["status"] == "blocked"
    assert raspuns["reason"] == "magazinul a blocat cererea sau nu a raspuns"
    assert raspuns["results"] == []


def test_exceptie_de_parsare_da_error_fara_traceback(monkeypatch):
    _poarta(monkeypatch, _Raspuns("{ asta nu e json"))
    raspuns = S.search("redgoblin.ro", "pokemon")
    assert raspuns["status"] == "error"
    assert raspuns["results"] == []
    assert len(raspuns["reason"]) <= 120
    assert "Traceback" not in raspuns["reason"]


def test_browser_e_unsupported_fara_nicio_cerere(monkeypatch):
    cerute = _poarta(monkeypatch, _Raspuns("{}"))
    raspuns = S.search("sephora.ro", "parfum")
    assert raspuns["status"] == "unsupported"
    assert raspuns["reason"] == "necesita browser — exclus din cautare"
    assert cerute == [], "un domeniu de browser nu are voie sa atinga poarta"


def test_domeniu_fara_search_e_unsupported(monkeypatch):
    cerute = _poarta(monkeypatch, _Raspuns("{}"))
    raspuns = S.search("cel.ro", "telefon")
    assert raspuns["status"] == "unsupported"
    assert raspuns["reason"] == "doar prin link"
    assert cerute == []


def test_domeniu_inexistent_ridica_valueerror():
    """E o greseala de APELANT, nu o stare a magazinului — router-ul o face 404."""
    with pytest.raises(ValueError, match="Magazin necunoscut"):
        S.search("nu-exista.example", "x")


# ── jurnal si sources() ──────────────────────────────────────────────────────

def test_emit_catalog_o_data_pe_fiecare_mecanism(monkeypatch, fara_jurnal):
    """O singura linie de jurnal per magazin, indiferent de mecanism."""
    _poarta(monkeypatch, _Raspuns(_payload_shopify([_SHOPIFY_CU_REDUCERE])))
    S.search("redgoblin.ro", "pokemon")
    assert len(fara_jurnal) == 1 and fara_jurnal[0][0] == "Red Goblin"

    fara_jurnal.clear()
    _poarta(monkeypatch, _Raspuns(json.dumps(
        [_produs_vtex("X", 10.0, 10.0, True)]), status_code=206))
    S.search("f64.ro", "sony alpha")
    assert len(fara_jurnal) == 1

    fara_jurnal.clear()
    _poarta(monkeypatch, _Raspuns(_FRAGMENT_BERGFREUNDE))
    S.search("bergfreunde.eu", "salomon")
    assert len(fara_jurnal) == 1

    fara_jurnal.clear()
    _scraper(monkeypatch, [_PRODUS_CUSTOM])
    S.search("altex.ro", "rtx 5070")
    assert len(fara_jurnal) == 1


def test_sources_descrie_tot_registrul():
    from app.services.shop_registry import (
        SHOP_REGISTRY, browser_domains, search_domains)

    surse = S.sources()
    assert len(surse) == len(SHOP_REGISTRY)

    cautabile = {s["domain"] for s in surse if s["searchable"]}
    assert cautabile == search_domains() - browser_domains()

    dupa_domeniu = {s["domain"]: s for s in surse}
    assert dupa_domeniu["redgoblin.ro"]["truncated_at"] == 10
    assert dupa_domeniu["redgoblin.ro"]["currency"] == "RON"
    # Plafonul e specific Shopify; celelalte mecanisme n-au unul.
    assert dupa_domeniu["f64.ro"]["truncated_at"] is None
    assert dupa_domeniu["f64.ro"]["currency"] == "RON"        # din catalog_api
    assert dupa_domeniu["bergfreunde.eu"]["currency"] == "EUR"  # din listing
    assert dupa_domeniu["sephora.ro"]["reason"] == "necesita browser — exclus din cautare"
    assert dupa_domeniu["cel.ro"]["reason"] == "doar prin link"

    etichete = [(s["label"] or "").lower() for s in surse]
    assert etichete == sorted(etichete), "sortare dupa label"


# ── SEARCH-1c: `truncated` uniform ───────────────────────────────────────────

# Trei carduri, ca sa se poata cere mai putine decat exista.
_FRAGMENT_3_CARDURI = """
<ul>
  <li class="product-item">
    <a class="product-link" href="https://www.bergfreunde.eu/unu/"></a>
    <div class="product-title">Unu</div>
    <span data-codecept="currentPrice">€ 10,00</span>
  </li>
  <li class="product-item">
    <a class="product-link" href="https://www.bergfreunde.eu/doi/"></a>
    <div class="product-title">Doi</div>
    <span data-codecept="currentPrice">€ 20,00</span>
  </li>
  <li class="product-item">
    <a class="product-link" href="https://www.bergfreunde.eu/trei/"></a>
    <div class="product-title">Trei</div>
    <span data-codecept="currentPrice">€ 30,00</span>
  </li>
</ul>
"""


def test_descriptor_taiat_de_max_results_e_trunchiat(monkeypatch):
    """Taierea `carduri[:max_results]` e a NOASTRA, deci trebuie semnalata.

    Inainte de SEARCH-1c, bergfreunde intorcea 50 din 72 de carduri cu
    `truncated: False` — UI-ul n-avea de unde sti ca mai exista 22.
    """
    _poarta(monkeypatch, _Raspuns(_FRAGMENT_3_CARDURI))
    raspuns = S.search("bergfreunde.eu", "salomon", max_results=2)
    assert raspuns["count"] == 2
    assert raspuns["truncated"] is True


def test_descriptor_sub_plafon_nu_e_trunchiat(monkeypatch):
    """Control negativ: 3 carduri cerute cu plafon 50 — nimic nearatat."""
    _poarta(monkeypatch, _Raspuns(_FRAGMENT_3_CARDURI))
    raspuns = S.search("bergfreunde.eu", "salomon", max_results=50)
    assert raspuns["count"] == 3
    assert raspuns["truncated"] is False


def test_vtex_fereastra_plina_e_trunchiat(monkeypatch):
    """Fereastra ceruta umpluta complet = lista taiata la sursa."""
    _poarta(monkeypatch, _Raspuns(json.dumps([
        _produs_vtex("A", 10.0, 10.0, True),
        _produs_vtex("B", 20.0, 20.0, True),
    ]), status_code=206))
    raspuns = S.search("f64.ro", "sony alpha", max_results=2)
    assert raspuns["count"] == 2
    assert raspuns["truncated"] is True


def test_custom_exact_max_results_e_trunchiat(monkeypatch):
    """Un scraper care da fix cat i s-a cerut probabil avea si mai mult."""
    _scraper(monkeypatch, [_PRODUS_CUSTOM, dict(_PRODUS_CUSTOM, name="Alta placa")])
    raspuns = S.search("altex.ro", "rtx 5070", max_results=2)
    assert raspuns["count"] == 2
    assert raspuns["truncated"] is True


# ── SEARCH-1c: jurnal onest pe error/blocked ─────────────────────────────────

def test_error_emite_WARN_nu_SCAN(monkeypatch, fara_jurnal, jurnal):
    """O linie SCAN pe `error` ar afirma o interogare normala cu 0 rezultate,
    ascunzand exceptia — jurnalul ar arata identic cu „magazinul n-are produsul"."""
    _poarta(monkeypatch, _Raspuns("{ asta nu e json"))

    raspuns = S.search("redgoblin.ro", "pokemon")

    assert raspuns["status"] == "error"
    assert fara_jurnal == [], "SCAN nu are voie sa se emita pe error"
    assert len(jurnal.linii) == 1
    modul, nivel, mesaj = jurnal.linii[0]
    assert (modul, nivel) == ("catalog", "WARN")
    assert mesaj.startswith("Red Goblin: cautare esuata pentru 'pokemon' — ")


def test_blocked_nu_emite_nimic(monkeypatch, fara_jurnal, jurnal):
    """Poarta a scris deja WARN-ul ei la clasificare; a doua linie ar fi duplicat."""
    _poarta(monkeypatch, None)

    assert S.search("redgoblin.ro", "pokemon")["status"] == "blocked"
    assert fara_jurnal == []
    assert jurnal.linii == []


def test_empty_emite_SCAN_nu_WARN(monkeypatch, fara_jurnal, jurnal):
    """Control negativ: `empty` e o interogare REUSITA cu 0 rezultate, deci primeste
    exact aceeasi linie ca `ok` — nu un avertisment."""
    _poarta(monkeypatch, _Raspuns(_payload_shopify([])))

    assert S.search("redgoblin.ro", "xqzvwk7731")["status"] == "empty"
    assert len(fara_jurnal) == 1
    assert jurnal.linii == []
