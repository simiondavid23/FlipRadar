"""REG-1/REG-2 — registrul declarativ de magazine.

Un test pe FORMA registrului (fiecare intrare isi respecta contractul de campuri)
si unul pe IZOLAREA derivarilor. Testele de egalitate cu structurile istorice au
existat doar cat timp registrul a mers in paralel cu literalele (REG-1); dupa
comutarea de la REG-2 ele ar compara derivarea cu ea insasi, deci s-au sters.
"""
from app.services import product_page_extractor as ppe
from app.services import scraper_service as ss
from app.services.shop_registry import (
    SHOP_REGISTRY,
    domain_overrides,
    impersonate_overrides,
    validated_domains,
)

_CAMPURI_OBLIGATORII = ("label", "category", "country", "delivery", "method", "status", "notes")

_CATEGORII = {"electronice", "fashion", "sneakers"}
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
