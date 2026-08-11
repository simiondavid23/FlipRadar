"""FBG-2 (C2 + M2) — identitatea postarii de grup pe PERMALINK si filtrul de
keywords per grup cu diacritice pliate. Functii PURE, fara retea/DB.

C2: vechiul post_id (aria-label | data-ft | pos_N) nu era un identificator:
data-ft e din Facebook clasic (mort), aria-label lipseste pe postarile comet
(apare pe COMENTARII), iar fallback-ul pos_{len(seen_ids)} era un index
POZITIONAL per rulare — la rularea 2, postari COMPLET NOI primeau aceleasi
pos_N si erau aruncate TACUT de dedup. Acum: pid numeric din permalink,
fallback hash pe text.
"""
from app.scrapers.facebook_group_scraper import (
    _permalink_url,
    _post_id_from_hrefs,
    _text_fingerprint,
)
from app.services.real_estate.extractor import passes_keyword_filter


# ── C2: _post_id_from_hrefs ─────────────────────────────────────────────────────
def test_permalink_forma_canonica_posts():
    hrefs = ["/groups/123456/user/789/",
             "https://www.facebook.com/groups/123456/posts/998877665544/?__cft__=x"]
    assert _post_id_from_hrefs(hrefs) == "998877665544"


def test_permalink_forma_veche_permalink():
    assert _post_id_from_hrefs(["/groups/imobiliare.buc/permalink/112233/"]) == "112233"


def test_permalink_multi_permalinks_si_story_fbid():
    assert _post_id_from_hrefs(
        ["/groups/123/?multi_permalinks=445566&notif_id=9"]) == "445566"
    assert _post_id_from_hrefs(
        ["/permalink.php?story_fbid=778899&id=123"]) == "778899"


def test_permalink_de_comentariu_se_sare():
    """Ancorele cu comment_id sunt permalink-uri de COMENTARIU — nu identifica
    postarea; urmatoarea ancora valida castiga."""
    hrefs = [
        "/groups/123/posts/555/?comment_id=666",
        "/groups/123/posts/555/",
    ]
    assert _post_id_from_hrefs(hrefs) == "555"


def test_fara_permalink_intoarce_none():
    assert _post_id_from_hrefs(["/groups/123/user/9/", None, "#", "/marketplace/"]) is None
    assert _post_id_from_hrefs([]) is None
    assert _post_id_from_hrefs(None) is None


# ── C2: _text_fingerprint (fallback) ────────────────────────────────────────────
def test_fingerprint_stabil_si_insensibil_la_spatii_diacritice():
    a = _text_fingerprint("Închiriez garsonieră   Militari, 350 €\n\nmobilată")
    b = _text_fingerprint("inchiriez garsoniera militari, 350 €  mobilata")
    assert a == b                      # NFKD + lower + spatii pliate
    assert a.startswith("txt_")
    assert len(a) == 4 + 16


def test_fingerprint_diferit_pentru_texte_diferite():
    assert (_text_fingerprint("Garsoniera Militari 350 EUR")
            != _text_fingerprint("Apartament Titan 500 EUR"))


def test_fingerprint_nu_mai_e_pozitional():
    """Controlul anti-regresie pe bugul-radacina: acelasi text -> acelasi id,
    indiferent de pozitia in pagina / rulare (nu mai exista pos_N)."""
    ids = {_text_fingerprint("Acelasi anunt repetat") for _ in range(5)}
    assert len(ids) == 1


# ── C2/M4: _permalink_url ───────────────────────────────────────────────────────
def test_permalink_url_din_grup_si_pid():
    assert (_permalink_url("https://www.facebook.com/groups/imobiliare/", "998")
            == "https://www.facebook.com/groups/imobiliare/posts/998/")
    # query string-ul grupului nu intra in permalink
    assert (_permalink_url("https://facebook.com/groups/123?ref=share", "55")
            == "https://facebook.com/groups/123/posts/55/")


def test_permalink_url_none_pe_fingerprint_sau_grup_gol():
    assert _permalink_url("https://facebook.com/groups/123", "txt_abc123") is None
    assert _permalink_url("https://facebook.com/groups/123", None) is None
    assert _permalink_url("", "998") is None


# ── M2: passes_keyword_filter cu diacritice pliate ─────────────────────────────
def test_keyword_fara_diacritice_prinde_text_cu_diacritice():
    text = "Închiriez garsonieră în Militari, 350 € pe lună"
    assert passes_keyword_filter(text, ["garsoniera"], []) is True


def test_keyword_cu_diacritice_prinde_text_fara_diacritice():
    text = "Inchiriez garsoniera in Militari, 350 € pe luna"
    assert passes_keyword_filter(text, ["garsonieră"], []) is True


def test_negative_keyword_cu_diacritice_respinge():
    text = "Închiriez cameră în apartament, 200 €"
    assert passes_keyword_filter(text, [], ["camera"]) is False


def test_control_negativ_keyword_absent_respinge():
    """Control negativ M2: plierea NU inmoaie filtrul — un keyword care chiar
    nu apare in text respinge in continuare postarea."""
    text = "Închiriez apartament 2 camere Titan, 500 €"
    assert passes_keyword_filter(text, ["garsoniera"], []) is False


def test_santinela_pret_cu_simbol_euro_supravietuieste_plierii():
    """€ dispare la plierea ascii — santinela de pret trebuie sa-l caute pe
    textul brut (bug potential introdus chiar de fixul M2, prins la implementare)."""
    assert passes_keyword_filter("Super oferta buna astazi la pretul de 350 €", [], []) is True


def test_santinela_proprietate_prinde_formele_flexionate():
    """Bonus M2: \\b-ul FINAL de dupa prefixe ("garsonier", "inchir", "vânz")
    cerea sfarsit de cuvant imediat dupa prefix — "garsonieră"/"închiriez"/
    "vânzare" nu treceau NICIODATA de santinela."""
    assert passes_keyword_filter("Dau spre închiriere ceva frumos aici", [], []) is True
    assert passes_keyword_filter("De vânzare proprietate frumoasa zona buna", [], []) is True
    assert passes_keyword_filter("Garsonieră luminoasă, zonă centrală, merită văzută", [], []) is True
    # controlul negativ: text fara pret si fara vocabular imobiliar -> respins
    assert passes_keyword_filter("Ofer bilete la concert, detalii in privat la mesaje", [], []) is False
