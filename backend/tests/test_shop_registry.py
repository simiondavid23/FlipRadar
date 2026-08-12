"""REG-1 — registrul declarativ de magazine.

Doua feluri de teste: unul pe FORMA registrului (fiecare intrare isi respecta
contractul de campuri) si trei de EGALITATE cu structurile istorice. Cele de
egalitate sunt plasa de siguranta a introducerii in paralel: registrul e sursa
noua, dar pana la comutare cele trei structuri raman literalele de dinainte, deci
derivarile trebuie sa dea exact acelasi lucru. La REG-2, dupa comutare, ele
compara derivarea cu ea insasi si se sterg.
"""
from app.services.product_page_extractor import DOMAIN_OVERRIDES, VALIDATED_DOMAINS
from app.services.scraper_service import _IMPERSONATE_OVERRIDES
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


def test_derivare_validated_egala_cu_istoric():
    assert validated_domains() == VALIDATED_DOMAINS


def test_derivare_overrides_egala_cu_istoric():
    assert domain_overrides() == DOMAIN_OVERRIDES


def test_derivare_impersonate_egala_cu_istoric():
    assert impersonate_overrides() == _IMPERSONATE_OVERRIDES
