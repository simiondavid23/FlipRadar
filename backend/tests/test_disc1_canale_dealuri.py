"""DISC-1 — rutarea deal-urilor axei D pe canale Discord.

Trei straturi, testate separat fiindca pot pica separat:
  * REGULA   — `deal_channel` (intrare > domeniu > `diverse`) si garda de import;
  * CABLAJUL — `_intrari` care duce `channel` din registru pana in scanner;
  * RUTAREA  — `send_deal_notification`, care alege webhook-urile.

Plus doua teste pe granita API (chei necunoscute, valoare goala) si un CONTROL
NEGATIV: cu `deal_channel` sabotat, testul de rutare trebuie sa cada. Fara el,
testul de rutare ar putea trece si daca rutarea ar trimite orbeste pe toate
webhook-urile configurate.
"""
import uuid

import pytest

from app.models.radar_settings import RadarSettings
from app.models.user import User
from app.database import SessionLocal
from app.services import discord_service as ds
from app.services.listing_scanner import _intrari
from app.services.shop_registry import (
    CANALE_DEAL,
    SHOP_REGISTRY,
    _valideaza_channel,
    deal_channel,
    listing_descriptor,
)

WEBHOOK = "https://discord.com/api/webhooks/{}/token"


class _DealFals:
    """Doar campurile pe care le citesc embed-ul si rutarea. Un rand real n-ar
    dovedi nimic in plus aici si ar lega testul de schema."""

    def __init__(self, domain, deal_id=7):
        self.id = deal_id
        self.shop_domain = domain
        self.external_id = "abc"
        self.title = "Adidasi de test"
        self.url = f"https://{domain}/p/1"
        self.image_url = None
        self.currency = "RON"
        self.price = 100.0
        self.compare_at_price = 250.0
        self.discount_pct = 60.0
        self.reason = "compare_at"
        self.min_price_seen = None
        self.sizes_available = []


class _SetariFalse:
    def __init__(self, harta):
        self.discord_webhooks_deals = harta


@pytest.fixture
def enqueue_fals(monkeypatch):
    """Intercepteaza coada: testele masoara CE se pune in ea, nu ce pleaca pe fir."""
    apeluri = []
    monkeypatch.setattr(ds.discord_service, "enqueue",
                        lambda **kw: apeluri.append(kw))
    return apeluri


def _canale_atinse(apeluri, harta):
    """Cheile de canal catre care s-a facut enqueue, deduse din URL-uri."""
    invers = {url: cheie for cheie, url in harta.items()}
    return sorted(invers[a["webhook_url"]] for a in apeluri)


# ── 1. REGULA ────────────────────────────────────────────────────────────────

def test_canalul_intrarii_bate_canalul_domeniului():
    """eMAG e domeniul pentru care exista mecanismul: declara `electronice`, dar
    departamentul de jucarii trebuie sa plece in `#feed-dealuri-jucarii`."""
    assert SHOP_REGISTRY["emag.ro"]["channel"] == "electronice"

    intrari = SHOP_REGISTRY["emag.ro"]["listing"]["entries"]
    jucarii = next(i for i in intrari if "jucarii-copii-bebe" in i["url"])
    laptopuri = next(i for i in intrari if "laptop-tablete" in i["url"])

    assert deal_channel("emag.ro", jucarii) == "jucarii"
    # Intrarea fara `channel` propriu NU suprascrie nimic: cade pe domeniu.
    assert "channel" not in laptopuri
    assert deal_channel("emag.ro", laptopuri) == "electronice"


def test_canalul_domeniului_cand_nu_exista_intrare():
    assert deal_channel("otter.ro") == "sneakers"
    assert deal_channel("otter.ro", None) == "sneakers"
    assert deal_channel("otter.ro", {"url": "x"}) == "sneakers"


def test_domeniul_absent_din_registru_cade_pe_diverse():
    """Rezerva NU e pentru un magazin pe care am uitat sa-l etichetam — pe acela
    cade `test_fiecare_domeniu_are_channel`. E pentru un rand VECHI al unui magazin
    scos din registru intre timp, unde o excepție ar rupe scanul."""
    assert deal_channel("nu-exista-nicaieri.example") == "diverse"
    assert deal_channel("nu-exista-nicaieri.example", {"url": "x"}) == "diverse"


def test_fiecare_domeniu_are_channel():
    """DISC-1b — eticheta e OBLIGATORIE, nu optionala.

    Testul-gardă al inversarii regulii. Cat timp absenta insemna `diverse`, un
    magazin nou uitat se purta perfect: feed-ul mergea, deal-urile plecau, doar pe
    canalul greșit — deci nimic nu semnala greseala. Cu testul asta, magazinul
    urmator adaugat fara eticheta cade aici, nu pe Discord peste doua luni.
    """
    fara = sorted(d for d, m in SHOP_REGISTRY.items() if "channel" not in m)

    assert not fara, (
        f"{len(fara)} domenii fara `channel`: {fara}. Alege canalul (unul din "
        f"{', '.join(CANALE_DEAL)}) — `diverse` se scrie EXPLICIT, nu se moștenește.")


def test_channel_invalid_e_respins_la_validare():
    """O typo nu are voie sa trimita un magazin intreg in `diverse` in tacere."""
    with pytest.raises(ValueError, match="electronic"):
        _valideaza_channel({"x.ro": {"channel": "electronic"}})

    with pytest.raises(ValueError, match="intrarea 1"):
        _valideaza_channel({"x.ro": {
            "channel": "electronice",
            "listing": {"entries": [{"url": "u"}, {"url": "u2", "channel": "sport"}]},
        }})

    # `toate` nu e canal AL UNUI MAGAZIN, ci destinatia agregata.
    with pytest.raises(ValueError):
        _valideaza_channel({"x.ro": {"channel": "toate"}})

    # Registrul real trece — garda ruleaza oricum la import, dar afirmatia
    # explicita spune ca asta se verifica, nu ca s-a intamplat sa mearga.
    _valideaza_channel(SHOP_REGISTRY)


def test_toate_canalele_din_registru_sunt_in_multimea_inchisa():
    for domeniu, meta in SHOP_REGISTRY.items():
        if "channel" in meta:
            assert meta["channel"] in CANALE_DEAL, domeniu


# ── 2. CABLAJUL registru -> scanner ──────────────────────────────────────────

def test_intrari_duce_channel_mai_departe():
    """`_intrari` reconstruieste dictul cheie cu cheie, deci o cheie necarata s-ar
    pierde TACUT intre registru si scanner."""
    canale = [deal_channel("emag.ro", i)
              for i in _intrari(listing_descriptor("emag.ro"))]

    assert canale.count("electronice") == 5
    assert canale.count("diverse") == 4
    assert canale.count("haine") == 1
    assert canale.count("beauty") == 1
    assert canale.count("jucarii") == 1
    assert len(canale) == 12


def test_intrari_pe_forma_url_nu_inventeaza_canal():
    """Pe un descriptor cu o singura listare canalul e al DOMENIULUI si sta in
    registru, nu in descriptor."""
    [intrare] = _intrari(listing_descriptor("otter.ro"))

    assert intrare["channel"] is None
    assert deal_channel("otter.ro", intrare) == "sneakers"


# ── 3. RUTAREA ───────────────────────────────────────────────────────────────

def test_dealul_pleaca_pe_toate_si_pe_canalul_lui(enqueue_fals):
    harta = {cheie: WEBHOOK.format(cheie)
             for cheie in ("toate", "electronice", "sneakers", "haine")}

    assert ds.send_deal_notification(_DealFals("otter.ro"), _SetariFalse(harta)) is True

    assert _canale_atinse(enqueue_fals, harta) == ["sneakers", "toate"], \
        "doar agregatul si canalul magazinului, nu si celelalte"
    assert {a["module"] for a in enqueue_fals} == {"deals"}
    assert {a["grade"] for a in enqueue_fals} == {None}
    assert {a["listing_id"] for a in enqueue_fals} == {"deal_7"}
    assert all(a["mention_here"] is False for a in enqueue_fals)


def test_canal_neconfigurat_lasa_dealul_doar_pe_toate(enqueue_fals):
    harta = {"toate": WEBHOOK.format("toate"), "haine": WEBHOOK.format("haine")}

    assert ds.send_deal_notification(_DealFals("otter.ro"), _SetariFalse(harta)) is True

    assert _canale_atinse(enqueue_fals, harta) == ["toate"]


def test_fara_niciun_webhook_nu_se_intampla_nimic(enqueue_fals):
    """Scanul nu are de ce sa cada fiindca Discord-ul nu e pus la punct."""
    for setari in (_SetariFalse({}), _SetariFalse(None), object()):
        assert ds.send_deal_notification(_DealFals("otter.ro"), setari) is False

    assert enqueue_fals == []


def test_canalul_pasat_explicit_bate_registrul(enqueue_fals):
    """Calea eMAG: scannerul stie din ce departament a iesit cardul."""
    harta = {cheie: WEBHOOK.format(cheie) for cheie in ("toate", "jucarii", "electronice")}

    ds.send_deal_notification(_DealFals("emag.ro"), _SetariFalse(harta), "jucarii")

    assert _canale_atinse(enqueue_fals, harta) == ["jucarii", "toate"]


def test_canal_pasat_invalid_cade_pe_registru(enqueue_fals):
    """Un apelant care paseaza gunoi nu poate ocoli multimea inchisa."""
    harta = {cheie: WEBHOOK.format(cheie) for cheie in ("toate", "sneakers", "diverse")}

    ds.send_deal_notification(_DealFals("otter.ro"), _SetariFalse(harta), "sport")

    assert _canale_atinse(enqueue_fals, harta) == ["sneakers", "toate"]


def test_acelasi_webhook_pe_doua_chei_nu_se_verifica_aici(enqueue_fals):
    """Cand `toate` si canalul arata spre acelasi URL, `send_deal_notification`
    pune DOUA iteme in coada — deduplicarea pe (listing_id, module, webhook_url)
    e treaba cozii, si e deja acolo. Testul pinuieste unde sta responsabilitatea,
    ca nimeni sa nu adauge o a doua verificare care s-ar putea desincroniza."""
    url = WEBHOOK.format("acelasi")
    ds.send_deal_notification(_DealFals("otter.ro"),
                              _SetariFalse({"toate": url, "sneakers": url}))

    assert [a["webhook_url"] for a in enqueue_fals] == [url, url]
    assert {a["listing_id"] for a in enqueue_fals} == {"deal_7"}


# ── 4. CONTROL NEGATIV ───────────────────────────────────────────────────────

def test_control_negativ_deal_channel_sabotat_strica_rutarea(enqueue_fals, monkeypatch):
    """Cu regula rupta (totul cade pe `diverse`), deal-ul de sneakers NU mai ajunge
    pe canalul lui. Daca asertiunea asta ar pica, ar insemna ca testul de rutare de
    mai sus trece din alt motiv decat cel pe care il afirma."""
    monkeypatch.setattr(ds, "deal_channel", lambda domain, entry=None: "diverse")

    harta = {cheie: WEBHOOK.format(cheie) for cheie in ("toate", "sneakers", "diverse")}
    ds.send_deal_notification(_DealFals("otter.ro"), _SetariFalse(harta))

    atinse = _canale_atinse(enqueue_fals, harta)
    assert "sneakers" not in atinse, "sabotajul trebuie sa se vada"
    assert atinse == ["diverse", "toate"]


# ── 5. EMBED ─────────────────────────────────────────────────────────────────

def _camp(embed, nume):
    return next((c["value"] for c in embed["fields"] if c["name"].endswith(nume)), None)


def test_embedul_poarta_canalul_si_labelul_magazinului():
    embed = ds.build_deal_embed(_DealFals("otter.ro"), "sneakers")

    assert _camp(embed, "Canal") == "sneakers"
    assert _camp(embed, "Magazin") == SHOP_REGISTRY["otter.ro"]["label"]
    assert _camp(embed, "Discount") == "-60.0%"
    assert _camp(embed, "Pret de referinta") == "250.0 RON"
    assert embed["url"] == "https://otter.ro/p/1"


def test_embedul_avertizeaza_doar_pe_referinta_nemarcata():
    nemarcat = next(d for d in SHOP_REGISTRY
                    if (listing_descriptor(d) or {}).get("reference_kind") == "nemarcat")
    marcat = next(d for d in SHOP_REGISTRY
                  if (listing_descriptor(d) or {}).get("reference_kind") == "min30")

    assert _camp(ds.build_deal_embed(_DealFals(nemarcat)), "Referinta nemarcata")
    assert _camp(ds.build_deal_embed(_DealFals(marcat)), "Referinta nemarcata") is None
    # Calea Shopify n-are descriptor de listare, deci nici avertisment.
    assert _camp(ds.build_deal_embed(_DealFals("patta.nl")), "Referinta nemarcata") is None


# ── 6. GRANITA API ───────────────────────────────────────────────────────────

def test_settings_respinge_cheile_necunoscute(auth_client):
    raspuns = auth_client.put("/api/radar/settings", json={
        "discord_webhooks_deals": {"sport": WEBHOOK.format("1")},
    })

    assert raspuns.status_code == 422, raspuns.text
    assert "sport" in raspuns.text


def test_settings_respinge_url_care_nu_e_webhook_discord(auth_client):
    raspuns = auth_client.put("/api/radar/settings", json={
        "discord_webhooks_deals": {"toate": "https://evil.example/hook"},
    })

    assert raspuns.status_code == 422, raspuns.text


def test_settings_salveaza_si_intoarce_harta(auth_client):
    pus = auth_client.put("/api/radar/settings", json={
        "discord_webhooks_deals": {"toate": WEBHOOK.format("t"),
                                   "sneakers": WEBHOOK.format("s")},
    })
    assert pus.status_code == 200, pus.text

    date = auth_client.get("/api/radar/settings").json()
    assert date["discord_webhooks_deals"] == {"toate": WEBHOOK.format("t"),
                                              "sneakers": WEBHOOK.format("s")}


def test_settings_valoarea_goala_sterge_cheia(auth_client):
    auth_client.put("/api/radar/settings", json={
        "discord_webhooks_deals": {"toate": WEBHOOK.format("t"),
                                   "sneakers": WEBHOOK.format("s")},
    })

    # Exact ce trimite formularul cand userul goleste inputul de sneakers.
    auth_client.put("/api/radar/settings", json={
        "discord_webhooks_deals": {"toate": WEBHOOK.format("t"), "sneakers": ""},
    })

    harta = auth_client.get("/api/radar/settings").json()["discord_webhooks_deals"]
    assert harta == {"toate": WEBHOOK.format("t")}, "cheia goala se sterge, nu ramane \"\""


def test_settings_harta_lipsa_e_dict_gol_nu_none(auth_client):
    """Formularul indexeaza direct in valoare; None ar fi o capcana, ca la SET-1."""
    assert auth_client.get("/api/radar/settings").json()["discord_webhooks_deals"] == {}


_BACKFILL = (
    "UPDATE radar_settings "
    "SET discord_webhooks_deals = json_object('toate', discord_webhook_deals) "
    "WHERE discord_webhook_deals IS NOT NULL AND discord_webhook_deals != '' "
    "AND (discord_webhooks_deals IS NULL "
    "     OR discord_webhooks_deals IN ('', '{}', 'null')) "
    "AND id = :id"
)


def _rand_vechi(harta_bruta, **campuri):
    """Un rand de setari scris ca inainte de DISC-1. Intoarce id-ul.

    `harta_bruta` se scrie prin SQL BRUT, nu prin ORM, si asta e esenta testului:
    tipul `JSON` al lui SQLAlchemy transforma un `None` din Python in JSON null
    ('null'), deci un rand construit prin ORM n-ar putea niciodata sa reproduca
    SQL NULL — exact starea pe care o lasa `ALTER TABLE ADD COLUMN` si singura pe
    care migrarea o intalneste in productie.
    """
    from sqlalchemy import text
    from app.database import engine

    db = SessionLocal()
    try:
        uniq = uuid.uuid4().hex[:10]
        u = User(email=f"disc1_{uniq}@example.com", username=f"disc1_{uniq}",
                 hashed_password="x", is_active=True)
        db.add(u)
        db.flush()
        s = RadarSettings(user_id=u.id, **campuri)
        db.add(s)
        db.commit()
        rand_id = s.id
    finally:
        db.close()

    with engine.begin() as conn:
        conn.execute(text("UPDATE radar_settings SET discord_webhooks_deals = :v "
                          "WHERE id = :id"), {"v": harta_bruta, "id": rand_id})
    return rand_id


def _harta_randului(rand_id):
    db = SessionLocal()
    try:
        return db.query(RadarSettings).filter(RadarSettings.id == rand_id).first() \
                 .discord_webhooks_deals
    finally:
        db.close()


@pytest.mark.parametrize("harta_bruta", [None, "", "{}", "null"])
def test_migrarea_muta_webhookul_vechi_in_toate(harta_bruta):
    """Cine avea deja un webhook unic de deal-uri nu are voie sa ramana fara
    notificari dupa comutare.

    Cele patru forme de „neconfigurat" sunt toate reale — vezi comentariul
    migrarii. Prima varianta a garzii acoperea doar NULL si '', iar `{}` (randul
    scris prin ORM, unde modelul declara `default=dict`) i-a scapat.
    """
    from sqlalchemy import text
    from app.database import engine

    rand_id = _rand_vechi(harta_bruta, discord_webhook_deals=WEBHOOK.format("vechi"))

    with engine.begin() as conn:
        conn.execute(text(_BACKFILL), {"id": rand_id})

    assert _harta_randului(rand_id) == {"toate": WEBHOOK.format("vechi")}


def test_migrarea_nu_calca_peste_o_harta_deja_scrisa():
    """Idempotenta: reluarea dupa o cadere (sau o a doua pornire) nu are voie sa
    suprascrie ce a configurat userul intre timp."""
    import json

    from sqlalchemy import text
    from app.database import engine

    deja = {"toate": WEBHOOK.format("nou"), "sneakers": WEBHOOK.format("s")}
    rand_id = _rand_vechi(json.dumps(deja),
                          discord_webhook_deals=WEBHOOK.format("vechi"))

    with engine.begin() as conn:
        conn.execute(text(_BACKFILL), {"id": rand_id})

    assert _harta_randului(rand_id) == deja
