"""CLEAN-1/CLEAN-2 — checker-ul de anunturi disparute: clasificare + terminarea buclei zilnice.

Teste pure pe `_classify` / `_check_url` (fara retea — curl_requests e stubuit cu
AssertionError acolo unde NU trebuie atins) + un test la nivel de serviciu pe
`cleanup_removed_listings_daily`, care dovedeste ca bucla se termina si nu mai sare
randuri (bugul de offset). `_check_url` si `time.sleep` sunt neutralizate acolo.

CLEAN-2: HEAD-ul nu mai decide singur (Publi24 raspunde 404 la HEAD pe anunturi vii),
iar OLX a ramas fara markeri text (paginile active contin frazele de sold in i18n).
Okazii e acum SINGURA platforma "cu markeri", deci testele de body o folosesc pe ea.
"""
from datetime import datetime, timedelta, timezone

import pytest

import app.services.radar.cleanup_service as cs


# ── _classify (pur) ─────────────────────────────────────────────────────────────
def test_404_e_removed():
    assert cs._classify(404, "", "olx") == "removed"


def test_410_e_removed():
    assert cs._classify(410, "", "olx") == "removed"


def test_200_cu_marker_okazii_e_sold():
    assert cs._classify(200, "<html>Anunț expirat</html>", "okazii") == "sold"


def test_200_fara_marker_e_active():
    assert cs._classify(200, "<html>Anunț normal, de vânzare</html>", "okazii") == "active"


def test_200_vinted_e_active_fara_markeri():
    # Vinted nu mai are markeri text (produceau stergeri false) -> 200 inseamna activ.
    assert cs._classify(200, "<html>sold vandut</html>", "vinted") == "active"


def test_200_olx_cu_fraza_de_sold_e_active():
    # CLEAN-2 — paginile OLX ACTIVE contin frazele de sold in bundle-urile i18n
    # (dovedit de sonda pe pagini de 1.7MB) -> markerii OLX au fost eliminati.
    assert cs._classify(200, "<html>anunț expirat · vândut · dezactivat</html>", "olx") == "active"


def test_olx_nu_mai_are_markeri():
    assert "olx" not in cs._SOLD_MARKERS
    assert set(cs._SOLD_MARKERS) == {"okazii"}


def test_403_e_unknown():
    # Blocat != disparut. Inainte, orice eroare era mascata ca 'active'.
    assert cs._classify(403, "", "olx") == "unknown"


def test_500_e_unknown():
    assert cs._classify(500, "", "olx") == "unknown"


def test_body_none_pe_platforma_cu_markeri_e_active():
    # 200 la HEAD, fara body cerut -> nu putem decide sold, dar anuntul exista.
    assert cs._classify(200, None, "okazii") == "active"


def test_platforma_necunoscuta_e_active_pe_200():
    assert cs._classify(200, "orice", "platforma_noua") == "active"


def test_marker_case_insensitive():
    assert cs._classify(200, "<div>ANUNT EXPIRAT</div>", "okazii") == "sold"


# ── _check_url ──────────────────────────────────────────────────────────────────
@pytest.fixture
def fara_http(monkeypatch):
    """Orice apel HTTP din _check_url = eroare de test."""
    def _boom(*a, **k):
        raise AssertionError("_check_url a facut HTTP desi nu trebuia")
    monkeypatch.setattr(cs.curl_requests, "head", _boom)
    monkeypatch.setattr(cs.curl_requests, "get", _boom)


def test_facebook_e_unknown_fara_http(fara_http):
    # Login-wall: 200 neautentificat pentru orice anunt -> neverificabil, nu-l atingem.
    assert cs._check_url("https://facebook.com/marketplace/item/1", "facebook") == "unknown"


def test_exceptie_la_head_e_unknown(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("retea picata")
    monkeypatch.setattr(cs.curl_requests, "head", _boom)
    assert cs._check_url("https://olx.ro/x", "olx") == "unknown"


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def _http(monkeypatch, head=None, get=None):
    """Stub pe head/get + numaratoare de apeluri GET (ca sa putem dovedi ca NU e apelat).

    `head`/`get` = _Resp sau exceptie de ridicat. Returneaza lista apelurilor GET.
    """
    get_calls = []

    def _mk(val, record=None):
        def _fn(*a, **k):
            if record is not None:
                record.append(a[0] if a else None)
            if isinstance(val, Exception):
                raise val
            return val
        return _fn

    if head is not None:
        monkeypatch.setattr(cs.curl_requests, "head", _mk(head))
    if get is not None:
        monkeypatch.setattr(cs.curl_requests, "get", _mk(get, get_calls))
    return get_calls


# CLEAN-2 — SANTINELA: Publi24 raspunde 404 la HEAD pe anunturi VII (GET 200).
# Inainte, HEAD-ul decidea singur -> "removed" -> cleanup-ul zilnic STERGEA anuntul.
def test_publi24_head_minte_404_dar_get_200_e_active(monkeypatch):
    _http(monkeypatch, head=_Resp(404), get=_Resp(200, "<html>anunt viu</html>"))
    assert cs._check_url("https://publi24.ro/x", "publi24") == "active"


def test_head_404_confirmat_de_get_404_e_removed(monkeypatch):
    _http(monkeypatch, head=_Resp(404), get=_Resp(404, ""))
    assert cs._check_url("https://olx.ro/x", "olx") == "removed"


def test_head_410_confirmat_de_get_410_e_removed(monkeypatch):
    # Mortii OLX raspund 410 — singurul semnal de disparitie pe OLX acum.
    _http(monkeypatch, head=_Resp(410), get=_Resp(410, ""))
    assert cs._check_url("https://olx.ro/x", "olx") == "removed"


def test_platforma_fara_markeri_se_opreste_la_head_200(monkeypatch):
    # Singura decizie luata direct din HEAD: 200 fara markeri -> activ, fara GET.
    get_calls = _http(monkeypatch, head=_Resp(200), get=_Resp(200, "irelevant"))
    assert cs._check_url("https://vinted.ro/items/1", "vinted") == "active"
    assert get_calls == [], "GET apelat degeaba dupa HEAD 200 pe platforma fara markeri"


def test_olx_head_200_nu_mai_face_get(monkeypatch):
    # OLX a ramas fara markeri -> intra pe calea ieftina (HEAD 200 = activ).
    get_calls = _http(monkeypatch, head=_Resp(200), get=_Resp(200, "anunt expirat"))
    assert cs._check_url("https://olx.ro/x", "olx") == "active"
    assert get_calls == []


def test_platforma_cu_markeri_cere_body_dupa_head_200(monkeypatch):
    # Okazii are markeri -> HEAD 200 nu e suficient, se face GET pentru body.
    get_calls = _http(monkeypatch, head=_Resp(200), get=_Resp(200, "<html>anunt expirat</html>"))
    assert cs._check_url("https://okazii.ro/x", "okazii") == "sold"
    assert len(get_calls) == 1


def test_head_403_face_fallback_pe_get(monkeypatch):
    monkeypatch.setattr(cs.curl_requests, "head", lambda *a, **k: _Resp(403))
    monkeypatch.setattr(cs.curl_requests, "get", lambda *a, **k: _Resp(200, "<html>ok</html>"))
    assert cs._check_url("https://vinted.ro/items/1", "vinted") == "active"


def test_get_esuat_dupa_head_blocat_e_unknown(monkeypatch):
    monkeypatch.setattr(cs.curl_requests, "head", lambda *a, **k: _Resp(403))
    monkeypatch.setattr(cs.curl_requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timeout")))
    assert cs._check_url("https://vinted.ro/items/1", "vinted") == "unknown"


def test_get_esuat_dupa_head_404_e_unknown(monkeypatch):
    # Fara confirmare, 404-ul de la HEAD nu are voie sa devina "removed".
    monkeypatch.setattr(cs.curl_requests, "head", lambda *a, **k: _Resp(404))
    monkeypatch.setattr(cs.curl_requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timeout")))
    assert cs._check_url("https://publi24.ro/x", "publi24") == "unknown"


def test_exceptie_la_head_nu_face_get(monkeypatch):
    get_calls = _http(monkeypatch, head=RuntimeError("retea picata"), get=_Resp(404))
    assert cs._check_url("https://olx.ro/x", "olx") == "unknown"
    assert get_calls == [], "HEAD a crapat — nu decidem nimic, nici macar prin GET"


# ── Bucla zilnica: terminare + zero sarituri (bugul de offset) ───────────────────
N_LISTINGURI = 120


@pytest.fixture
def _fara_retea(monkeypatch):
    monkeypatch.setattr(cs, "_check_url", lambda url, platform: "active")
    monkeypatch.setattr(cs.time, "sleep", lambda s: None)


def _seed(db, n):
    """Un user + un keyword + n listinguri eligibile (found_at peste cutoff-ul de 6h)."""
    from app.models.radar_keyword import RadarKeyword
    from app.models.radar_listing import RadarListing
    from app.models.user import User

    user = User(email="clean1@example.com", username="clean1", hashed_password="x")
    db.add(user)
    db.flush()
    kw = RadarKeyword(user_id=user.id, name="clean1", max_price=100, resale_price=200)
    db.add(kw)
    db.flush()
    vechi = datetime.now(timezone.utc) - timedelta(hours=12)
    for i in range(n):
        db.add(RadarListing(
            user_id=user.id, keyword_id=kw.id, external_id=f"clean1_{i}",
            platform="olx", title=f"Anunt {i}", price=10.0,
            url=f"https://olx.ro/{i}", found_at=vechi, status="active",
        ))
    db.commit()
    return user.id


def test_bucla_zilnica_verifica_toate_randurile_si_se_termina(_fara_retea):
    """Cu offset-ul vechi, ~jumatate din randuri erau sarite: randurile verificate
    primeau last_checked_at=now si sareau la coada ordonarii, iar offset-ul aplicat
    peste ordinea re-amestecata trecea peste ele. Aici verificam ca TOATE cele 120
    sunt atinse si ca bucla se termina."""
    from app.database import SessionLocal
    from app.models.radar_listing import RadarListing

    db = SessionLocal()
    try:
        _seed(db, N_LISTINGURI)
        start = datetime.now(timezone.utc)

        sterse = cs.cleanup_removed_listings_daily(db)

        assert sterse == 0  # _check_url -> "active", nimic nu se sterge
        randuri = db.query(RadarListing).all()
        assert len(randuri) == N_LISTINGURI
        neatinse = [r for r in randuri if r.last_checked_at is None]
        assert neatinse == [], f"{len(neatinse)} randuri sarite (bugul de offset)"
        # Fiecare rand a fost atins in ACEASTA rulare, nu intr-una anterioara.
        start_naiv = start.replace(tzinfo=None)
        vechi = [r.id for r in randuri
                 if (r.last_checked_at.replace(tzinfo=None) if r.last_checked_at.tzinfo
                     else r.last_checked_at) < start_naiv]
        assert vechi == [], f"randuri cu last_checked_at inainte de start: {vechi}"
    finally:
        db.close()


def test_bucla_zilnica_sterge_ce_a_disparut(monkeypatch):
    """Randurile clasificate removed/sold se sterg; 'unknown' NU se sterge."""
    from app.database import SessionLocal
    from app.models.radar_listing import RadarListing

    monkeypatch.setattr(cs.time, "sleep", lambda s: None)
    # Primele 10 dispar, urmatoarele 10 sunt nedecidabile, restul sunt active.
    def _fals_check(url, platform):
        idx = int(url.rsplit("/", 1)[1])
        if idx < 10:
            return "removed"
        if idx < 20:
            return "unknown"
        return "active"
    monkeypatch.setattr(cs, "_check_url", _fals_check)

    db = SessionLocal()
    try:
        _seed(db, 30)
        sterse = cs.cleanup_removed_listings_daily(db)
        assert sterse == 10
        ramase = db.query(RadarListing).all()
        assert len(ramase) == 20
        # 'unknown' nu sterge si nu schimba statusul — doar marcheaza randul ca atins.
        assert all(r.status == "active" for r in ramase)
        assert all(r.last_checked_at is not None for r in ramase)
    finally:
        db.close()
