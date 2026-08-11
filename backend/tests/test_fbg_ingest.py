"""FBG-2 (M1, M3, M4, M6, m5, M5) — ingestul postarilor de grup in feedul
Imobiliare si semnalizarea sesiunilor.

Teste la nivel de serviciu pe baza de test (conftest), fara retea: AI-ul e
dezactivat (ai=None) sau spionat, iar cleanup-ul nu atinge HTTP (listingurile
non-Facebook din teste nu au URL).
"""
from datetime import datetime, timedelta, timezone

import app.services.real_estate_scanner as res
from app.services.real_estate_scanner import (
    RealEstateListing,
    _save_fb_group_post,
    run_cleanup,
)


def _user(db, email="fbg_ingest@example.com"):
    from app.models.user import User
    u = User(email=email, username=email.split("@")[0],
             hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    return u


def _kw(db, user_id, **over):
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword
    base = dict(user_id=user_id, name="FBG kw", platform="facebook_groups",
                city="București", is_active=True, tip_anunt="vanzare")
    base.update(over)
    kw = RealEstateMonitorKeyword(**base)
    db.add(kw)
    db.flush()
    return kw


def _post(**over):
    """post_dict minimal, cum il produce bucla de ingest (coloanele tabelului)."""
    base = dict(
        id=1, post_id="998877", group_url="https://facebook.com/groups/imob",
        post_url=None, text="Vand apartament 3 camere, 70 mp, Titan",
        pret=None, moneda=None, tip_anunt="vanzare", tip_proprietate="3 camere",
        suprafata_mp=None, etaj=None, zona=None, termen=None, facilitati=None,
        posted_at=None, created_at=datetime(2026, 8, 1, 10, 0, 0),
    )
    base.update(over)
    return base


# ── M1: pret de vanzare peste plafonul extract_all + moneda din post ───────────
def test_vanzare_peste_50000_pastreaza_pretul_si_moneda_din_ingest():
    """"400.000 lei" iesea cu price=None din extract_all (plafon 50-50.000 pentru
    chirii); fallback-ul vechi lua pretul din post["pret"] dar moneda din
    default-ul "EUR" -> 400.000 RON ajungea in feed ca 400.000 EUR."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        u = _user(db)
        kw = _kw(db, u.id)
        post = _post(id=11, post_id="p11",
                     text="Vand apartament 3 camere, 70 mp, Titan, 400.000 lei",
                     pret=400000, moneda="RON")
        listing = _save_fb_group_post(db, post, kw, None, {}, eur_ron=5.0)
        assert listing is not None
        assert float(listing.price) == 400000.0
        assert listing.currency == "RON"
        # price_per_sqm se calculeaza acum si pe fallback (aria din text: 70 mp)
        assert listing.price_per_sqm is not None
    finally:
        db.close()


def test_filtrul_de_pret_al_keywordului_nu_mai_e_ocolit_la_vanzari():
    """Control negativ M1: cu pretul din ingest INTRAT in extracted, price_max al
    keyword-ului respinge postarea — inainte price=None facea filtrul inert."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        u = _user(db, "fbg_m1b@example.com")
        kw = _kw(db, u.id, price_max=80000, price_currency="EUR")
        post = _post(id=12, post_id="p12",
                     text="Vand apartament 3 camere, 70 mp, Titan, 89.000 euro",
                     pret=89000, moneda="EUR")
        assert _save_fb_group_post(db, post, kw, None, {}, eur_ron=5.0) is None
    finally:
        db.close()


# ── M3 + M4: listed_at din posted_at, url din permalink ────────────────────────
def test_listed_at_e_data_postarii_nu_a_insertului():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        u = _user(db, "fbg_m3@example.com")
        kw = _kw(db, u.id)
        posted = datetime(2026, 7, 30, 8, 30, 0)
        post = _post(id=13, post_id="p13", posted_at=posted,
                     created_at=datetime(2026, 8, 1, 10, 0, 0))
        listing = _save_fb_group_post(db, post, kw, None, {}, None)
        assert listing.listed_at == posted
    finally:
        db.close()


def test_listed_at_fallback_created_at_cand_posted_lipseste():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        u = _user(db, "fbg_m3b@example.com")
        kw = _kw(db, u.id)
        post = _post(id=14, post_id="p14", posted_at=None)
        listing = _save_fb_group_post(db, post, kw, None, {}, None)
        assert listing.listed_at == post["created_at"]
    finally:
        db.close()


def test_url_e_permalinkul_postarii_cu_fallback_pe_grup():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        u = _user(db, "fbg_m4@example.com")
        kw = _kw(db, u.id)
        pl = "https://facebook.com/groups/imob/posts/998877/"
        listing = _save_fb_group_post(
            db, _post(id=15, post_id="998877", post_url=pl), kw, None, {}, None)
        assert listing.url == pl
        listing2 = _save_fb_group_post(
            db, _post(id=16, post_id="txt_abc", post_url=None), kw, None, {}, None)
        assert listing2.url == "https://facebook.com/groups/imob"
    finally:
        db.close()


# ── M6: filtrul ieftin de query INAINTEA apelului LLM ──────────────────────────
def test_postarea_care_nu_potriveste_query_nu_arde_apel_llm(monkeypatch):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        u = _user(db, "fbg_m6@example.com")
        kw = _kw(db, u.id, query="garsoniera")
        apeluri = []

        def _spy(text, existing, ai_client=None, model=None):
            apeluri.append(text)
            return existing

        monkeypatch.setattr(res, "groq_extract", _spy)
        # ai != None ca sa se vada ca NU query-ul de AI decide, ci ordinea
        post = _post(id=17, post_id="p17")  # text de 3 camere, nu garsoniera
        assert _save_fb_group_post(db, post, kw, ("client", "model"), {}, None) is None
        assert apeluri == [], "groq_extract nu trebuie apelat pe postari respinse de query"

        # controlul pozitiv: o postare care POTRIVESTE query-ul apeleaza LLM-ul
        post_ok = _post(id=18, post_id="p18",
                        text="Inchiriez garsoniera Militari, 350 euro, 30 mp")
        _save_fb_group_post(db, post_ok, kw, ("client", "model"), {}, None)
        assert len(apeluri) == 1
    finally:
        db.close()


# ── m5: expirarea pe varsta a listingurilor Facebook in cleanup ────────────────
def _listing(db, user_id, platform, status="active", days_old=0, **over):
    row = RealEstateListing(
        user_id=user_id, platform=platform, external_id=f"{platform}_{days_old}_{status}",
        status=status, title="t", url=over.pop("url", None),
        found_at=datetime.now(timezone.utc) - timedelta(days=days_old),
    )
    for k, v in over.items():
        setattr(row, k, v)
    db.add(row)
    db.flush()
    return row


def test_cleanup_expira_listingurile_facebook_vechi_de_30_zile():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        u = _user(db, "fbg_m5cleanup@example.com")
        vechi_fbg = _listing(db, u.id, "facebook_groups", days_old=35)
        vechi_mkt = _listing(db, u.id, "facebook_marketplace", days_old=35)
        proaspat = _listing(db, u.id, "facebook_groups", days_old=5)
        salvat_vechi = _listing(db, u.id, "facebook_groups", status="saved", days_old=90)
        vechi_olx = _listing(db, u.id, "olx", days_old=90)  # fara URL -> fara HEAD/GET
        db.commit()

        run_cleanup(db)

        db.refresh(vechi_fbg); db.refresh(vechi_mkt); db.refresh(proaspat)
        db.refresh(salvat_vechi); db.refresh(vechi_olx)
        assert vechi_fbg.status == "removed"
        assert vechi_mkt.status == "removed"
        assert proaspat.status == "active", "sub 30 de zile ramane in feed"
        assert salvat_vechi.status == "saved", "salvatele nu se expira"
        assert vechi_olx.status == "active", "expirarea pe varsta e DOAR pentru Facebook"
    finally:
        db.close()


# ── M5: /stats separa sesiunea Marketplace de cookie-urile FBG ─────────────────
def _fbg_config(db, user_id, status):
    from app.models.facebook_group_config import FacebookGroupConfig
    c = FacebookGroupConfig(user_id=user_id, group_name="G",
                            group_url="https://facebook.com/groups/g",
                            is_active=True, cookies_encrypted="x",
                            last_run_status=status)
    db.add(c)
    db.flush()
    return c


def test_stats_user_doar_cu_fbg_nu_mai_primeste_bannerul_marketplace():
    """Inainte: has_facebook_keywords includea facebook_groups, dar validarea se
    facea pe storage_state-ul Marketplace -> banner permanent fals."""
    from app.database import SessionLocal
    from app.routers.real_estate_keywords import get_stats
    db = SessionLocal()
    try:
        u = _user(db, "fbg_stats1@example.com")
        _kw(db, u.id)                      # doar facebook_groups
        _fbg_config(db, u.id, "ok")
        db.commit()
        stats = get_stats(db=db, current_user=u)
        assert stats["has_facebook_keywords"] is False        # fara kw Marketplace
        assert stats["facebook_session_valid"] is None        # bannerul vechi tace
        assert stats["has_facebook_groups_keywords"] is True
        assert stats["fbg_cookies_invalid"] is False
    finally:
        db.close()


def test_stats_cookies_de_grup_expirate_aprind_semnalul_fbg():
    from app.database import SessionLocal
    from app.routers.real_estate_keywords import get_stats
    db = SessionLocal()
    try:
        u = _user(db, "fbg_stats2@example.com")
        _kw(db, u.id)
        _fbg_config(db, u.id, "cookies_expirate")
        db.commit()
        assert get_stats(db=db, current_user=u)["fbg_cookies_invalid"] is True
    finally:
        db.close()


def test_stats_cookies_invalide_aprind_si_ele_semnalul():
    from app.database import SessionLocal
    from app.routers.real_estate_keywords import get_stats
    db = SessionLocal()
    try:
        u = _user(db, "fbg_stats3@example.com")
        _kw(db, u.id)
        _fbg_config(db, u.id, "cookies_invalide")
        db.commit()
        assert get_stats(db=db, current_user=u)["fbg_cookies_invalid"] is True
    finally:
        db.close()
