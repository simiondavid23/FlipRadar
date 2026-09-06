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


# ── T6 — alertele Radar ─────────────────────────────────────────────────────────

_LISTING = {"title": "iPhone 12 Pro", "price": 1200, "currency": "RON",
            "platform": "olx", "url": "https://www.olx.ro/x", "location": "Cluj"}


def _embed(**kw):
    from app.services.radar.discord_service import _build_embed

    return _build_embed(_LISTING, "iphone", "A", 2000.0, 40.0, **kw)


def test_t6_embedul_are_campul_doar_pe_bump_real():
    cu_bump = _embed(listed_at=_POSTAT, found_at=_BUMPAT, refreshed_at=_BUMPAT)
    nume = [f["name"] for f in cu_bump["fields"]]
    assert "🔁 Reactualizat pe platformă" in nume
    # imediat dupa „Postat", inainte de „Găsit"
    assert nume.index("🔁 Reactualizat pe platformă") == nume.index("📅 Postat pe platformă") + 1
    assert nume.index("🔍 Găsit de FlipRadar") == nume.index("🔁 Reactualizat pe platformă") + 1


def test_t6b_fara_bump_embedul_e_identic_cu_cel_al_semnaturii_vechi():
    """Parametrul nou e la coada, cu default — apelurile vechi produc EXACT ce produceau."""
    vechi = _embed(listed_at=_POSTAT, found_at=_BUMPAT)                       # semnatura veche
    fara_bump = _embed(listed_at=_POSTAT, found_at=_BUMPAT, refreshed_at=None)
    sub_prag = _embed(listed_at=_POSTAT, found_at=_BUMPAT,
                      refreshed_at=_POSTAT + timedelta(hours=23))
    assert fara_bump == vechi
    assert sub_prag == vechi
    assert all("Reactualizat" not in f["name"] for f in vechi["fields"])


def test_t6c_corpul_emailului_are_linia_doar_pe_bump_real(monkeypatch):
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


def test_t6d_lantul_discord_paseaza_refreshed_at(monkeypatch):
    """`route_discord_alerts` -> `send_discord_alert` -> `_build_embed`, tot lantul."""
    from app.services.radar import discord_service as ds

    trimise = []
    monkeypatch.setattr(ds.requests, "post",
                        lambda url, **kw: trimise.append(kw["json"]) or type(
                            "R", (), {"status_code": 204, "text": ""})())

    setari = type("S", (), {"discord_webhook_all": "https://x/wh",
                            "discord_webhook_buy_now": None,
                            "discord_webhook_maybe": None})()
    ds.route_discord_alerts(setari, _LISTING, "iphone", "A", 2000.0, 40.0,
                            _POSTAT, _BUMPAT, _BUMPAT)
    nume = [f["name"] for f in trimise[0]["embeds"][0]["fields"]]
    assert "🔁 Reactualizat pe platformă" in nume


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
