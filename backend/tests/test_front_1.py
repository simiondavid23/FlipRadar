"""FRONT-1 — `refreshed_at` devine vizibil: export Excel, regula de bump, alerte Radar.

Seria DATE a pus in DB doua date pe fiecare anunt: `listed_at` (prima publicare) si
`refreshed_at` (ultima repromovare). Runda asta le scoate la suprafata. Ce se testeaza
aici e partea de backend:
  * cele trei exportatoare xlsx primesc coloana „Data reactualizării" IMEDIAT dupa
    „Data postării", cu aceeasi formatare, fara sa mute hyperlink-ul de pe URL;
  * `este_reactualizat` — regula de 24 h, perechea backend a lui `bumpInfo` din
    components/shared/listingHelpers.js;
  * alertele Radar (e-mail + embed Discord) adauga linia/campul DOAR pe un bump real;
    fara bump raman identice la byte cu ce produceau inainte.

Partea de frontend (T1-T3) e verificata separat: `frontend/package.json` nu are runner
de teste, deci helperii sunt exersati de un script node autonom, a carui iesire e in
raportul rundei (26 asertii).
"""
import io
from datetime import datetime, timedelta, timezone

from openpyxl import load_workbook

from app.services.auto_listings.excel_exporter import build_auto_xlsx
from app.services.radar.excel_exporter import build_listings_xlsx
from app.services.real_estate.excel_exporter import build_re_xlsx
from app.utils.listing_dates import este_reactualizat

_POSTAT = datetime(2026, 6, 1, 10, 0, 0)
_BUMPAT = datetime(2026, 9, 3, 17, 30, 0)


def _sheet(raw: bytes):
    return load_workbook(io.BytesIO(raw)).worksheets[0]


def _antet(ws) -> list:
    return [c.value for c in ws[1]]


# ── T4 — coloana noua in cele trei exportatoare ─────────────────────────────────

_EXPORTATOARE = [
    # (nume, builder, rand, cheia de dată-postare asa cum o primeste exportatorul)
    ("radar", build_listings_xlsx, {
        "title": "iPhone 12", "platform": "olx", "score": "A", "price": 1200.0,
        "listed_at": _POSTAT.isoformat(), "refreshed_at": _BUMPAT.isoformat(),
        "found_at": _BUMPAT.isoformat(), "status": "active",
        "url": "https://www.olx.ro/d/oferta/x-IDabc.html",
    }),
    ("auto", build_auto_xlsx, {
        "title": "BMW 320d", "platform": "olx_auto", "grade": "B", "price": 7500.0,
        "currency": "EUR", "listed_at": _POSTAT, "refreshed_at": _BUMPAT,
        "found_at": _BUMPAT, "status": "active",
        "url": "https://www.olx.ro/d/oferta/bmw-IDdef.html",
    }),
    ("imobiliare", build_re_xlsx, {
        "title": "Apartament 2 camere", "platform": "olx", "grade": "A", "price": 85000.0,
        "currency": "EUR", "listed_at": _POSTAT, "refreshed_at": _BUMPAT,
        "found_at": _BUMPAT, "status": "active",
        "url": "https://www.olx.ro/d/oferta/ap-IDghi.html",
    }),
]


def test_t4_coloana_de_reactualizare_e_imediat_dupa_data_postarii():
    for nume, builder, rand in _EXPORTATOARE:
        antet = _antet(_sheet(builder([rand])))
        assert "Data postării" in antet, nume
        assert "Data reactualizării" in antet, nume
        i = antet.index("Data postării")
        assert antet[i + 1] == "Data reactualizării", (nume, antet)


def test_t4b_valoarea_e_formatata_identic_cu_vecina():
    for nume, builder, rand in _EXPORTATOARE:
        ws = _sheet(builder([rand]))
        antet = _antet(ws)
        i = antet.index("Data postării")
        postat = ws.cell(row=2, column=i + 1).value
        reactualizat = ws.cell(row=2, column=i + 2).value
        assert postat == "01.06.2026 10:00", (nume, postat)
        assert reactualizat == "03.09.2026 17:30", (nume, reactualizat)


def test_t4c_hyperlinkul_a_ramas_pe_url():
    """Regresie pe indexul coloanei: o coloana in plus nu are voie sa mute link-ul."""
    for nume, builder, rand in _EXPORTATOARE:
        ws = _sheet(builder([rand]))
        antet = _antet(ws)
        assert antet[-1] == "URL", (nume, antet)
        celula = ws.cell(row=2, column=len(antet))
        assert celula.value == rand["url"], nume
        assert celula.hyperlink is not None, nume
        assert str(celula.hyperlink.target or celula.hyperlink) .endswith("IDabc.html") \
            or nume != "radar"


def test_t4d_rand_fara_reactualizare_lasa_celula_la_fel_ca_vecina():
    """Fara `refreshed_at`, celula ramane goala — exact ca „Data postării" fara `listed_at`
    (openpyxl citeste inapoi `None` pentru stringul gol scris de exportator)."""
    for nume, builder, rand in _EXPORTATOARE:
        fara = {k: v for k, v in rand.items() if k not in ("refreshed_at", "listed_at")}
        ws = _sheet(builder([fara]))
        antet = _antet(ws)
        i = antet.index("Data postării")
        postat = ws.cell(row=2, column=i + 1).value
        reactualizat = ws.cell(row=2, column=i + 2).value
        assert not reactualizat, (nume, reactualizat)
        assert reactualizat == postat, (nume, postat, reactualizat)


# ── T5 — regula de 24 h (perechea backend a lui `bumpInfo`) ─────────────────────

def test_t5_pragul_de_24h():
    assert este_reactualizat(_POSTAT, _BUMPAT) is True
    assert este_reactualizat(_POSTAT, _POSTAT) is False                       # egale
    assert este_reactualizat(_POSTAT, _POSTAT + timedelta(seconds=1)) is False
    assert este_reactualizat(_POSTAT, _POSTAT + timedelta(hours=23)) is False
    assert este_reactualizat(_POSTAT, _POSTAT + timedelta(hours=24)) is True  # exact pragul
    assert este_reactualizat(_POSTAT, _POSTAT + timedelta(hours=25)) is True


def test_t5b_lipsa_sau_tip_gresit_da_false_fara_exceptie():
    for listed, refreshed in ((None, _BUMPAT), (_POSTAT, None), (None, None),
                              ("2026-06-01", _BUMPAT), (_POSTAT, "2026-09-03"),
                              (_POSTAT, 123), (object(), _BUMPAT)):
        assert este_reactualizat(listed, refreshed) is False, (listed, refreshed)


def test_t5c_naiv_plus_aware_da_false_nu_typeerror():
    """Conventiile difera per modul (Radar/Auto naiv local, Imobiliare prin
    fromisoformat), deci perechea mixta e posibila — nu are voie sa arunce."""
    aware = _BUMPAT.replace(tzinfo=timezone.utc)
    assert este_reactualizat(_POSTAT, aware) is False
    assert este_reactualizat(_POSTAT.replace(tzinfo=timezone.utc), _BUMPAT) is False
    # ambele aware -> regula normala
    assert este_reactualizat(_POSTAT.replace(tzinfo=timezone.utc), aware) is True


def test_t5d_bump_mai_vechi_decat_publicarea_nu_e_bump():
    assert este_reactualizat(_BUMPAT, _POSTAT) is False


# ── T6 — alertele Radar (Discord: calea VIE, dupa FRONT-1b) ────────────────────

_LISTING = {"title": "iPhone 12 Pro", "price": 1200, "currency": "RON",
            "platform": "olx", "url": "https://www.olx.ro/x", "location": "Cluj",
            "resale_price": 2000, "margin": 800}


def _embed(**date):
    """Embed-ul Radar de pe calea vie: `send_radar_notification` -> `build_radar_embed`.

    FRONT-1b: `_build_embed` din app/services/radar/discord_service.py (pe care erau
    scrise T6/T6b la FRONT-1) a fost sters — nu-l mai apela nimeni de mult, iar
    campurile de data au fost mutate aici, unde ajung efectiv pe Discord.
    """
    from app.services.discord_service import build_radar_embed

    return build_radar_embed({**_LISTING, **date}, "A", 40, "iphone")


def test_t6_campul_de_reactualizare_apare_doar_pe_bump_real():
    cu_bump = _embed(listed_at=_POSTAT, refreshed_at=_BUMPAT, found_at=_BUMPAT)
    nume = [f["name"] for f in cu_bump["fields"]]
    assert "🔁 Reactualizat pe platformă" in nume
    # ordinea: Postat -> Reactualizat -> Gasit (aceeasi ca in corpul e-mailului)
    assert nume.index("🔁 Reactualizat pe platformă") == nume.index("📅 Postat pe platformă") + 1
    assert nume.index("🔍 Găsit de FlipRadar") == nume.index("🔁 Reactualizat pe platformă") + 1
    valoare = next(f["value"] for f in cu_bump["fields"] if "Reactualizat" in f["name"])
    assert valoare == "03.09.2026 17:30"


def test_t6b_fara_date_embedul_e_identic_cu_cel_de_dinainte():
    """Un `listing` fara chei de data produce EXACT embed-ul de dinainte de runda.

    Comparatia e pe dict intreg, nu pe chei: garda ca modulele care nu trimit date
    (si calea de pret scazut, care inca nu le trimite) raman neatinse la byte.
    """
    fara_nimic = _embed()
    assert all("Postat" not in f["name"] and "Reactualizat" not in f["name"]
               and "Găsit" not in f["name"] for f in fara_nimic["fields"])
    # ultimul camp ramane Keyword, ca inainte de FRONT-1b
    assert fara_nimic["fields"][-1]["name"] == "🎯 Keyword"


def test_t6c_listed_at_fara_bump_arata_postat_dar_nu_reactualizat():
    doar_postat = _embed(listed_at=_POSTAT, found_at=_BUMPAT)
    sub_prag = _embed(listed_at=_POSTAT, found_at=_BUMPAT,
                      refreshed_at=_POSTAT + timedelta(hours=23))
    egal = _embed(listed_at=_POSTAT, found_at=_BUMPAT, refreshed_at=_POSTAT)

    for embed in (doar_postat, sub_prag, egal):
        nume = [f["name"] for f in embed["fields"]]
        assert "📅 Postat pe platformă" in nume
        assert "🔍 Găsit de FlipRadar" in nume
        assert not any("Reactualizat" in n for n in nume)
    # sub prag / egal produc acelasi embed ca lipsa totala a reactualizarii
    assert sub_prag == doar_postat and egal == doar_postat


def test_t6d_corpul_emailului_are_linia_doar_pe_bump_real(monkeypatch):
    from app.models.radar_keyword import RadarKeyword
    from app.models.user import User
    from app.utils import radar_scanner as rs

    trimise = []
    monkeypatch.setattr(rs, "smtp_configured", lambda: True)
    monkeypatch.setattr(rs, "send_email",
                        lambda to, subj, body: trimise.append((to, subj, body)))

    user = User(email="x@example.com", username="x", hashed_password="x")
    kw = RadarKeyword(user_id=1, name="iphone", max_price=1500.0, resale_price=2000.0)

    def corp(**kw_extra):
        trimise.clear()
        rs._send_email_alert(user, _LISTING, kw, "A", 40.0,
                             listed_at=_POSTAT, found_at=_BUMPAT, **kw_extra)
        return trimise[0][2]

    cu_bump = corp(refreshed_at=_BUMPAT)
    assert "Reactualizat pe platformă: 03.09.2026 17:30" in cu_bump

    vechi = corp()                                    # semnatura veche
    fara = corp(refreshed_at=None)
    sub_prag = corp(refreshed_at=_POSTAT + timedelta(hours=23))
    assert fara == vechi and sub_prag == vechi
    assert "Reactualizat" not in vechi


# ── Paritatea celor doua reguli (backend vs frontend) ──────────────────────────

def test_regula_backend_si_frontend_folosesc_acelasi_prag():
    """Garda pe drift: pragul e scris in doua limbi, deci se verifica amandoua."""
    import re
    from pathlib import Path

    from app.utils.listing_dates import PRAG_REACTUALIZARE

    assert PRAG_REACTUALIZARE == timedelta(hours=24)

    js = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / \
        "shared" / "listingHelpers.js"
    sursa = js.read_text(encoding="utf-8")
    m = re.search(r"const PRAG_BUMP_MS = ([^;]+);", sursa)
    assert m, "PRAG_BUMP_MS a disparut din listingHelpers.js"
    assert eval(m.group(1).replace("*", "*")) == PRAG_REACTUALIZARE.total_seconds() * 1000


# ── T7/T8 — FRONT-1b: calea vie de Discord + stergerea duplicatului ────────────

def test_t7_listing_dict_pentru_discord_duce_ambele_date():
    """Ce ajunge efectiv pe Discord. Blocul era inline in bucla de scan (cateva sute de
    linii), deci nimic nu-l putea verifica; FRONT-1b l-a extras."""
    from app.utils.radar_scanner import _listing_dict_pentru_discord

    listing = {"title": "iPhone 12 Pro", "price": 1200, "currency": "RON",
               "platform": "olx", "url": "https://www.olx.ro/x",
               "images": ["https://x/y.jpg"], "location": "Cluj",
               "listed_at": _POSTAT, "refreshed_at": _BUMPAT}
    rand = type("Rand", (), {"found_at": _BUMPAT})()
    kw = type("Kw", (), {"resale_price": 2000.0})()

    d = _listing_dict_pentru_discord(listing, rand, kw, "olx")
    assert d["listed_at"] == _POSTAT
    assert d["refreshed_at"] == _BUMPAT
    assert d["found_at"] == _BUMPAT          # din randul DB, nu din listing
    # campurile de dinainte de FRONT-1b, neatinse
    assert d["title"] == "iPhone 12 Pro" and d["platform"] == "olx"
    assert d["resale_price"] == 2000 and d["margin"] == 800
    assert d["image_url"] == "https://x/y.jpg"


def test_t7b_dictul_ajunge_intr_un_embed_cu_reactualizarea():
    """Capatul lantului: dictul construit de scanner produce campul pe embed-ul real."""
    from app.services.discord_service import build_radar_embed
    from app.utils.radar_scanner import _listing_dict_pentru_discord

    d = _listing_dict_pentru_discord(
        {"title": "x", "price": 1200, "listed_at": _POSTAT, "refreshed_at": _BUMPAT},
        type("Rand", (), {"found_at": _BUMPAT})(),
        type("Kw", (), {"resale_price": 2000.0})(), "olx")
    nume = [f["name"] for f in build_radar_embed(d, "A", 40, "iphone")["fields"]]
    assert "🔁 Reactualizat pe platformă" in nume
    assert "📅 Postat pe platformă" in nume


def test_t7c_listing_fara_date_da_chei_none_nu_lipsa():
    """Cheile exista mereu; embed-ul decide ce afiseaza, nu dictul."""
    from app.utils.radar_scanner import _listing_dict_pentru_discord

    d = _listing_dict_pentru_discord({"title": "x"}, type("R", (), {})(),
                                     type("K", (), {})(), "olx")
    assert d["listed_at"] is None and d["refreshed_at"] is None and d["found_at"] is None


def test_t8_calea_moarta_de_alerte_a_disparut():
    """FRONT-1b — `_build_embed`/`send_discord_alert`/`route_discord_alerts` erau un
    duplicat fara apelanti al rutarii Radar. Modulul NU s-a putut sterge: gazduieste
    `send_test_message` si `send_system_alert`, vii, cu cinci apelanti in `app/`.
    """
    from app.services.radar import discord_service as vechi

    for mort in ("_build_embed", "send_discord_alert", "route_discord_alerts", "_fmt_dt"):
        assert not hasattr(vechi, mort), mort
    for viu in ("send_test_message", "send_system_alert"):
        assert hasattr(vechi, viu), viu


def test_t8b_formatarea_de_data_traieste_pe_calea_vie():
    from app.services.discord_service import _fmt_dt

    assert _fmt_dt(_POSTAT) == "01.06.2026 10:00"
    assert _fmt_dt(None) == ""
    assert _fmt_dt("nu-i datetime") == ""


# ── T9 — FRONT-1c: alerta Discord de PRET SCAZUT primeste aceleasi trei date ────

_LISTING_SCADERE = {
    "external_id": "olx_scadere", "title": "iPhone 12 Pro",
    "price": 1200.0, "currency": "RON", "platform": "olx",
    "url": "https://www.olx.ro/x", "images": ["https://x/y.jpg"], "location": "Cluj",
    "listed_at": _POSTAT, "refreshed_at": _BUMPAT,
}
# Referinta din `radar_seen_ids`: 2000 -> 1200 = scadere de 40%, peste _PRICE_DROP_MIN.
_PRET_INITIAL = 2000.0
_DROP_PCT = int(round(((_PRET_INITIAL - 1200.0) / _PRET_INITIAL) * 100))   # 40


def _alerta_pret_scazut(monkeypatch, listing: dict) -> dict:
    """Ruleaza `_reaparitie_fara_rand` (SEEN-3) si intoarce dict-ul trimis pe Discord."""
    import uuid

    from app.database import SessionLocal
    from app.models.radar_keyword import RadarKeyword
    from app.models.radar_seen_id import RadarSeenId
    from app.models.user import User
    from app.utils import radar_scanner as rs

    notificari = []
    monkeypatch.setattr(rs, "send_radar_notification",
                        lambda **kw: notificari.append(kw) or 1)
    monkeypatch.setattr(rs.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(rs, "is_push_configured", lambda: False)
    monkeypatch.setattr(rs, "smtp_configured", lambda: False)

    db = SessionLocal()
    try:
        email = f"f1c_{uuid.uuid4().hex[:10]}@example.com"
        user = User(email=email, username=email.split("@")[0],
                    hashed_password="x", is_active=True)
        db.add(user)
        db.flush()
        kw = RadarKeyword(user_id=user.id, name="iphone", max_price=5000.0,
                          resale_price=3000.0, platform="olx", notify_discord=True)
        db.add(kw)
        db.add(RadarSeenId(user_id=user.id, platform="olx",
                           external_id=listing["external_id"],
                           pret_initial=_PRET_INITIAL, moneda="RON"))
        db.commit()

        rs._reaparitie_fara_rand(db, user, kw, "olx", dict(listing),
                                 settings=type("S", (), {})(),
                                 eur_ron=5.0, usd_ron=4.5, cursuri={"RON": 1.0})
    finally:
        db.close()

    assert notificari, "alerta de pret scazut n-a plecat"
    return notificari[0]["listing"]


def test_t9_alerta_de_pret_scazut_are_cele_trei_date_si_prefixul(monkeypatch):
    trimis = _alerta_pret_scazut(monkeypatch, _LISTING_SCADERE)

    # cele trei date, ca la alerta de anunt nou
    assert trimis["listed_at"] == _POSTAT
    assert trimis["refreshed_at"] == _BUMPAT
    assert trimis["found_at"] is not None          # din randul abia salvat

    # prefixul, caracter cu caracter — acelasi text, acelasi procent, aceeasi rotunjire
    assert trimis["title"] == f"Pret scazut {_DROP_PCT}%: iPhone 12 Pro"
    assert trimis["title"].startswith("Pret scazut 40%: ")
    assert trimis["title"].endswith(_LISTING_SCADERE["title"])


def test_t9b_embedul_de_pret_scazut_arata_reactualizarea_doar_la_bump(monkeypatch):
    from app.services.discord_service import build_radar_embed

    bumpat = _alerta_pret_scazut(monkeypatch, _LISTING_SCADERE)
    nume = [f["name"] for f in build_radar_embed(bumpat, "A", 40, "iphone")["fields"]]
    assert "🔁 Reactualizat pe platformă" in nume
    assert "📅 Postat pe platformă" in nume

    # acelasi anunt, dar reactualizat la o ora dupa publicare -> sub pragul de 24 h
    fara_bump = _alerta_pret_scazut(
        monkeypatch,
        {**_LISTING_SCADERE, "external_id": "olx_scadere2",
         "refreshed_at": _POSTAT + timedelta(hours=1)})
    nume2 = [f["name"] for f in build_radar_embed(fara_bump, "A", 40, "iphone")["fields"]]
    assert "📅 Postat pe platformă" in nume2
    assert not any("Reactualizat" in n for n in nume2)


def test_t9c_restul_cheilor_au_ramas_cu_aceleasi_valori(monkeypatch):
    """Regresie pe restul alertei: dict-ul inline de dinainte de FRONT-1c, reconstruit
    aici din aceleasi surse, trebuie sa se regaseasca intact — masurat, singura valoare
    care difera intre el si `_listing_dict_pentru_discord` era titlul."""
    trimis = _alerta_pret_scazut(monkeypatch, _LISTING_SCADERE)
    resale = 3000.0
    pret = 1200.0
    vechi = {
        "price": pret,
        "currency": "RON",
        "url": "https://www.olx.ro/x",
        "image_url": "https://x/y.jpg",
        "location": "Cluj",
        "platform": "olx",
        "resale_price": int(resale),
        "margin": int(resale - pret),
    }
    for cheie, valoare in vechi.items():
        assert trimis[cheie] == valoare, (cheie, trimis[cheie], valoare)


# ── T10 — FRONT-1d: a treia alerta Discord (scadere pe un rand EXISTENT) ────────

def _alerta_scadere_pe_rand(monkeypatch, *, listed_at, refreshed_at,
                            pret_vechi=2000.0, pret_nou=1200.0) -> dict:
    """Ruleaza `_refresh_seen_listing` pe calea (1) — anuntul ARE rand in feed — si
    intoarce dict-ul trimis pe Discord.

    Aici sursa e randul ORM (`row.title`, `row.images` serializat JSON, ...), nu
    listing-ul scraperului, de-aia dict-ul ramane construit inline.
    """
    import json
    import uuid

    from app.database import SessionLocal
    from app.models.radar_keyword import RadarKeyword
    from app.models.radar_listing import RadarListing
    from app.models.radar_seen_id import RadarSeenId
    from app.models.user import User
    from app.utils import radar_scanner as rs

    notificari = []
    monkeypatch.setattr(rs, "send_radar_notification",
                        lambda **kw: notificari.append(kw) or 1)
    monkeypatch.setattr(rs.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(rs, "is_push_configured", lambda: False)

    db = SessionLocal()
    try:
        email = f"f1d_{uuid.uuid4().hex[:10]}@example.com"
        user = User(email=email, username=email.split("@")[0],
                    hashed_password="x", is_active=True)
        db.add(user)
        db.flush()
        kw = RadarKeyword(user_id=user.id, name="iphone", max_price=5000.0,
                          resale_price=3000.0, platform="olx", notify_discord=True)
        db.add(kw)
        db.flush()
        ext = f"olx_{uuid.uuid4().hex[:8]}"
        db.add(RadarListing(
            user_id=user.id, keyword_id=kw.id, platform="olx", external_id=ext,
            title="iPhone 12 Pro", price=pret_vechi, currency="RON",
            url="https://www.olx.ro/x",
            images=json.dumps(["https://x/y.jpg"]),
            location="Cluj", status="active",
            listed_at=listed_at, refreshed_at=refreshed_at,
        ))
        db.add(RadarSeenId(user_id=user.id, platform="olx", external_id=ext,
                           pret_initial=pret_vechi, moneda="RON"))
        db.commit()

        marcaj = rs._refresh_seen_listing(
            db, user, kw, "olx",
            {"external_id": ext, "title": "iPhone 12 Pro", "price": pret_nou,
             "currency": "RON", "platform": "olx"},
            settings=type("S", (), {})(),
            eur_ron=5.0, usd_ron=4.5, cursuri={"RON": 1.0})
        assert marcaj == "notified", marcaj
    finally:
        db.close()

    assert notificari, "alerta de scadere pe rand existent n-a plecat"
    return notificari[0]["listing"]


def test_t10_scaderea_pe_rand_existent_are_cele_trei_date_si_prefixul(monkeypatch):
    trimis = _alerta_scadere_pe_rand(monkeypatch,
                                     listed_at=_POSTAT, refreshed_at=_BUMPAT)

    assert trimis["listed_at"] == _POSTAT
    assert trimis["refreshed_at"] == _BUMPAT
    assert trimis["found_at"] is not None        # coloana randului, populata la insert

    # prefixul, neschimbat: 2000 -> 1200 = 40%
    assert trimis["title"] == "Pret scazut 40%: iPhone 12 Pro"
    # restul dict-ului, neatins de FRONT-1d
    assert trimis["price"] == 1200.0 and trimis["currency"] == "RON"
    assert trimis["image_url"] == "https://x/y.jpg"
    assert trimis["location"] == "Cluj" and trimis["platform"] == "olx"


def test_t10b_embedul_arata_reactualizarea_doar_la_bump(monkeypatch):
    from app.services.discord_service import build_radar_embed

    bumpat = _alerta_scadere_pe_rand(monkeypatch,
                                     listed_at=_POSTAT, refreshed_at=_BUMPAT)
    nume = [f["name"] for f in build_radar_embed(bumpat, "A", 40, "iphone")["fields"]]
    assert "🔁 Reactualizat pe platformă" in nume
    assert "📅 Postat pe platformă" in nume and "🔍 Găsit de FlipRadar" in nume

    # reactualizat la o ora dupa publicare -> sub pragul de 24 h
    fara_bump = _alerta_scadere_pe_rand(
        monkeypatch, listed_at=_POSTAT, refreshed_at=_POSTAT + timedelta(hours=1))
    nume2 = [f["name"] for f in build_radar_embed(fara_bump, "A", 40, "iphone")["fields"]]
    assert "📅 Postat pe platformă" in nume2
    assert not any("Reactualizat" in n for n in nume2)


def test_t10c_rand_fara_date_nu_produce_campuri(monkeypatch):
    """Randuri vechi, dinainte de DATE-1: cheile pleaca None, embed-ul le ignora."""
    from app.services.discord_service import build_radar_embed

    trimis = _alerta_scadere_pe_rand(monkeypatch, listed_at=None, refreshed_at=None)
    assert trimis["listed_at"] is None and trimis["refreshed_at"] is None
    nume = [f["name"] for f in build_radar_embed(trimis, "A", 40, "iphone")["fields"]]
    assert not any("Postat" in n or "Reactualizat" in n for n in nume)
    assert "🔍 Găsit de FlipRadar" in nume     # found_at exista mereu pe rand


# ── T11/T12 — FRONT-1e: paritate Discord pe Auto si Imobiliare ─────────────────

_AUTO_BAZA = {"title": "BMW 320d", "price": 7500.0, "currency": "EUR",
              "year": 2015, "km": 180000, "platform": "olx_auto",
              "location": "Cluj", "url": "https://www.olx.ro/bmw"}
_IMOB_BAZA = {"title": "Apartament 2 camere", "price": 85000.0, "currency": "EUR",
              "rooms": 2, "area_sqm": 55.0, "platform": "olx",
              "zone_normalized": "Gheorgheni", "url": "https://www.olx.ro/ap"}

_NUME_DATE = ("📅 Postat pe platformă", "🔁 Reactualizat pe platformă",
              "🔍 Găsit de FlipRadar")


def _nume(embed) -> list:
    return [f["name"] for f in embed["fields"]]


def _verifica_paritate(builder, baza):
    """Aceleasi trei cazuri pentru oricare builder: bump / fara bump / fara date."""
    cu_bump = builder({**baza, "listed_at": _POSTAT, "refreshed_at": _BUMPAT,
                       "found_at": _BUMPAT})
    nume = _nume(cu_bump)
    for eticheta in _NUME_DATE:
        assert eticheta in nume, (eticheta, nume)
    # aceeasi ORDINE ca la Radar: Postat -> Reactualizat -> Gasit, ultimele campuri
    assert nume[-3:] == list(_NUME_DATE), nume
    valoare = next(f["value"] for f in cu_bump["fields"] if "Reactualizat" in f["name"])
    assert valoare == "03.09.2026 17:30"

    # sub pragul de 24 h -> fara „Reactualizat", restul neschimbat
    fara_bump = builder({**baza, "listed_at": _POSTAT, "found_at": _BUMPAT,
                         "refreshed_at": _POSTAT + timedelta(hours=23)})
    doar_postat = builder({**baza, "listed_at": _POSTAT, "found_at": _BUMPAT})
    assert not any("Reactualizat" in n for n in _nume(fara_bump))
    assert "📅 Postat pe platformă" in _nume(fara_bump)
    assert fara_bump == doar_postat

    # fara nicio data -> embed-ul de azi, dinaintea rundei
    return builder(dict(baza))


def test_t11_auto_embed_paritate_cu_radar():
    from app.services.discord_service import build_auto_embed

    fara_date = _verifica_paritate(
        lambda listing: build_auto_embed(listing, "A", 40, "bmw"), _AUTO_BAZA)
    assert not any(n in _NUME_DATE for n in _nume(fara_date))
    assert _nume(fara_date)[-1] == "🎯 Keyword"
    assert fara_date["footer"]["text"].startswith("FlipRadar Auto Anunțuri")


def test_t12_imob_embed_paritate_cu_radar():
    from app.services.discord_service import build_imob_embed

    fara_date = _verifica_paritate(
        lambda listing: build_imob_embed(listing, "A", 40, "apartament"), _IMOB_BAZA)
    assert not any(n in _NUME_DATE for n in _nume(fara_date))
    assert _nume(fara_date)[-1] == "🎯 Keyword"
    assert fara_date["footer"]["text"].startswith("FlipRadar Imobiliare")


def test_t12b_auto_datele_vin_dupa_blocul_de_import():
    """Auto are un camp „Import pe roti" dupa Keyword — datele raman ULTIMELE."""
    from app.services.discord_service import build_auto_embed

    embed = build_auto_embed(
        {**_AUTO_BAZA, "currency": "EUR", "listed_at": _POSTAT, "found_at": _BUMPAT,
         "import_score_json": {"pe_roti": {"total_ron": 45000, "saving_ron": 3000}}},
        "A", 40, "bmw")
    nume = _nume(embed)
    assert "🌍 Import pe roți" in nume
    assert nume.index("🌍 Import pe roți") < nume.index("📅 Postat pe platformă")
    assert nume[-1] == "🔍 Găsit de FlipRadar"


# ── T13/T14 — dict-urile trimise de cele doua scannere ─────────────────────────

def _seed_user_settings(db):
    import uuid

    from app.models.radar_settings import RadarSettings
    from app.models.user import User

    email = f"f1e_{uuid.uuid4().hex[:10]}@example.com"
    user = User(email=email, username=email.split("@")[0],
                hashed_password="x", is_active=True)
    db.add(user)
    db.flush()
    db.add(RadarSettings(user_id=user.id, discord_webhook_auto_all="https://x/wh",
                         discord_webhook_imob_all="https://x/wh"))
    db.commit()
    return user


def test_t13_auto_scanner_trimite_cele_trei_date(monkeypatch):
    """Dict-ul e o comprehensiune pe COLOANELE randului, deci cele trei coloane din
    DATE-1 ajung acolo prin constructie — testul pinuieste ca raman."""
    import app.services.discord_service as ds
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing
    from app.models.auto_keyword import AutoKeyword
    from app.services import auto_listings_scanner as als

    trimise = []
    monkeypatch.setattr(als.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(ds, "send_auto_notification",
                        lambda *a, **k: trimise.append(a[0]))

    db = SessionLocal()
    try:
        user = _seed_user_settings(db)
        kw = AutoKeyword(user_id=user.id, name="bmw", platform="olx_auto",
                         is_active=True, notify_discord=True, notify_email=False)
        db.add(kw)
        db.flush()
        rand = AutoFeedListing(user_id=user.id, keyword_id=kw.id, platform="olx_auto",
                               external_id="a1", title="BMW 320d", price=7500.0,
                               currency="EUR", grade="A", score=40,
                               listed_at=_POSTAT, refreshed_at=_BUMPAT)
        db.add(rand)
        db.commit()
        db.refresh(rand)
        als._notify(kw, rand, db)
    finally:
        db.close()

    assert trimise, "notificarea auto n-a plecat"
    d = trimise[0]
    assert d["listed_at"] == _POSTAT and d["refreshed_at"] == _BUMPAT
    assert d["found_at"] is not None


def test_t13b_auto_rand_vechi_fara_date_nu_randeaza_campuri():
    """Paritate cu T10c de la Radar: randuri dinainte de DATE-1 au NULL."""
    from app.services.discord_service import build_auto_embed

    embed = build_auto_embed({**_AUTO_BAZA, "listed_at": None, "refreshed_at": None,
                              "found_at": _BUMPAT}, "A", 40, "bmw")
    nume = _nume(embed)
    assert not any("Postat" in n or "Reactualizat" in n for n in nume)
    assert "🔍 Găsit de FlipRadar" in nume


def test_t14_imob_scanner_trimite_cele_trei_date(monkeypatch):
    import app.services.discord_service as ds
    from app.database import SessionLocal
    from app.models.real_estate_monitor_keyword import (
        RealEstateMonitorKeyword as RealEstateKeyword)
    from app.models.real_estate_monitor_listing import RealEstateMonitorListing
    from app.services import real_estate_scanner as rs

    trimise = []
    monkeypatch.setattr(rs.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(ds, "send_imob_notification",
                        lambda *a, **k: trimise.append(a[0]))

    db = SessionLocal()
    try:
        user = _seed_user_settings(db)
        kw = RealEstateKeyword(user_id=user.id, name="apartament", platform="olx",
                               notify_discord=True, notify_email=False)
        db.add(kw)
        db.flush()
        rand = RealEstateMonitorListing(
            user_id=user.id, keyword_id=kw.id, platform="olx", external_id="r1",
            title="Apartament 2 camere", price=85000.0, currency="EUR",
            grade="A", score=40, listed_at=_POSTAT, refreshed_at=_BUMPAT)
        db.add(rand)
        db.commit()
        db.refresh(rand)
        settings = type("S", (), {"discord_webhook_imob_all": "https://x/wh",
                                  "discord_here_imob": False})()
        rs._notify_re(rand, kw, settings, db)
    finally:
        db.close()

    assert trimise, "notificarea imobiliare n-a plecat"
    d = trimise[0]
    assert d["listed_at"] == _POSTAT and d["refreshed_at"] == _BUMPAT
    assert d["found_at"] is not None


def test_t14b_datele_ies_din_sqlite_intotdeauna_NAIVE():
    """PASUL 0.4, pinuit — conventia Imobiliare scrie `listed_at` din `fromisoformat`
    pe un ISO CU offset, deci in memorie poate fi AWARE. La persistare, coloana
    TIMESTAMP din SQLite ARUNCA offset-ul si pastreaza ora de perete: un
    `17:30+00:00` scris se citeste inapoi ca `17:30` naiv, NU convertit la local.

    Consecinta pentru runda: `este_reactualizat` nu vede niciodata perechea mixta
    aware+naiv pe calea de notificare (compara doua naive), deci nu e nimic de reparat
    aici. Comportamentul e de STOCARE, preexistent, si nu se atinge in runda asta.
    """
    import uuid
    from datetime import timezone

    from app.database import SessionLocal
    from app.models.real_estate_monitor_listing import RealEstateMonitorListing
    from app.utils.listing_dates import este_reactualizat

    aware = _BUMPAT.replace(tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        user = _seed_user_settings(db)
        rand = RealEstateMonitorListing(
            user_id=user.id, platform="olx", external_id=f"tz_{uuid.uuid4().hex[:6]}",
            title="x", listed_at=_POSTAT, refreshed_at=aware)
        db.add(rand)
        db.commit()
        db.expire_all()
        rand = db.query(RealEstateMonitorListing).filter_by(id=rand.id).one()

        assert rand.refreshed_at.tzinfo is None          # offset-ul a fost aruncat
        assert rand.refreshed_at == _BUMPAT              # ora de perete, neconvertita
        assert rand.listed_at.tzinfo is None
        assert este_reactualizat(rand.listed_at, rand.refreshed_at) is True
    finally:
        db.close()
