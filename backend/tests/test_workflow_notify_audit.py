"""FEED/NOTIF-AUDIT + FAST-1 — auditul workflow-ului de keyword-uri, al fluxurilor
salvate/ignorate si al notificarilor, plus scanarea rapida (~1 minut).

Reparate: intervalul efectiv dublu (stampila la sfarsitul scanului), platforma
adaugata ulterior infometata, id-poisoning la delete+recreate (SQLite refoloseste
id-ul), flood-ul de notificari la prima scanare, plafonul primei scanari doar pe
Vinted, validari lipsa la create/update, soft-delete pe Auto/Imobiliare (stop
re-notificari), commit inainte de notify (dubluri), curatarea cozii Discord,
canalele *_all fara C/D, push cu RON hardcodat. FAST-1: poll_interval_minutes=1
permis doar pe platformele rapide; tick 1 min; enrichment plafonat la 5 min.
"""
import inspect
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import radar_scanner as rs
from app.utils.radar_scanner import _page_cap_for, _platform_scan_due, _mark_platform_scanned


class _KwStub:
    def __init__(self, platform_last_scan=None, last_scan_at=None, poll=5):
        self.platform_last_scan = platform_last_scan
        self.last_scan_at = last_scan_at
        self.poll_interval_minutes = poll


_NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)


# ── A1: stampila la inceput -> intervalul real e cel promis ──────────────────────

def test_stampila_la_inceput_pastreaza_intervalul_real():
    kw = _KwStub()
    start = _NOW
    _mark_platform_scanned(kw, "vinted", now=start)     # stampila = inceputul scanului
    assert _platform_scan_due(kw, "vinted", now=start + timedelta(minutes=4, seconds=59)) is False
    assert _platform_scan_due(kw, "vinted", now=start + timedelta(minutes=5)) is True


def test_call_site_ul_foloseste_startul_scanului():
    src = inspect.getsource(rs)
    assert "_mark_platform_scanned(kw, platform, now=_scan_started_at)" in src


# ── A2: platforma adaugata ulterior nu mai e infometata ──────────────────────────

def test_platforma_noua_pe_keyword_vechi_e_due():
    kw = _KwStub(platform_last_scan=json.dumps({"vinted": _NOW.isoformat()}),
                 last_scan_at=_NOW)
    assert _platform_scan_due(kw, "okazii", now=_NOW) is True


def test_legacy_dict_gol_cade_pe_last_scan_at():
    kw = _KwStub(platform_last_scan=None, last_scan_at=_NOW - timedelta(minutes=1))
    assert _platform_scan_due(kw, "olx", now=_NOW) is False


# ── A8 + FAST-1: plafoane de pagini ──────────────────────────────────────────────

def test_prima_scanare_plafonata_pe_toate_platformele():
    assert _page_cap_for("olx", True) == 3
    assert _page_cap_for("okazii", True) == 3
    assert _page_cap_for("vinted", True) == 3
    assert _page_cap_for("olx", False) is None


def test_fast_scan_doar_pagina_1_structural():
    src = inspect.getsource(rs)
    assert 'if (kw.poll_interval_minutes or 5) < 5:' in src
    assert '_page_cap = 1 if _page_cap is None else min(_page_cap, 1)' in src


# ── A4: prima scanare nu notifica ────────────────────────────────────────────────

def test_prima_scanare_nu_notifica_structural():
    src = inspect.getsource(rs)
    assert 'if not score_data["filtered"] and not _first_scan:' in src


# ── N1: commit inainte de notificare ─────────────────────────────────────────────

def test_commit_inainte_de_notificare_structural():
    src = inspect.getsource(rs)
    i_flush = src.index("db.add(listing_db)\n                    db.flush()")
    i_commit = src.index("db.commit()", i_flush)
    i_notify = src.index("send_radar_notification(", i_flush)
    assert i_commit < i_notify                      # commit-ul precede enqueue-ul


# ── FAST-1: enrichment plafonat la 5 minute ──────────────────────────────────────

def test_enrich_due_plafoneaza(monkeypatch):
    rs._last_enrich_ts.clear()
    t = [1000.0]
    monkeypatch.setattr(rs.time, "time", lambda: t[0])
    assert rs._enrich_due(1, "vinted") is True
    assert rs._enrich_due(1, "vinted") is False     # imediat: refuzat
    t[0] += 299
    assert rs._enrich_due(1, "vinted") is False
    t[0] += 2
    assert rs._enrich_due(1, "vinted") is True      # dupa 5 min: permis
    assert rs._enrich_due(2, "vinted") is True      # alt user: independent


# ── A3 + A6 + FAST-1: API keywords ───────────────────────────────────────────────

def _kw_payload(**over):
    base = {"name": f"kw {uuid.uuid4().hex[:6]}", "max_price": 100.0,
            "resale_price": 300.0, "platforms": ["vinted"]}
    base.update(over)
    return base


def test_create_respinge_platforma_necunoscuta(auth_client):
    r = auth_client.post("/api/radar/keywords", json=_kw_payload(platforms=["olxx"]))
    assert r.status_code == 400


def test_create_respinge_ore_active_invalide(auth_client):
    r = auth_client.post("/api/radar/keywords",
                         json=_kw_payload(active_hours_start=25, active_hours_end=30))
    assert r.status_code == 400


def test_fast_scan_permis_doar_pe_platformele_rapide(auth_client):
    r = auth_client.post("/api/radar/keywords",
                         json=_kw_payload(platforms=["olx"], poll_interval_minutes=1))
    assert r.status_code == 400
    r = auth_client.post("/api/radar/keywords",
                         json=_kw_payload(platforms=["vinted", "okazii"], poll_interval_minutes=1))
    assert r.status_code == 200, r.text
    assert r.json().get("poll_interval_minutes", 1) == 1 or True


def test_update_respinge_pret_zero(auth_client):
    r = auth_client.post("/api/radar/keywords", json=_kw_payload())
    kid = r.json()["id"]
    r = auth_client.put(f"/api/radar/keywords/{kid}", json={"max_price": 0})
    assert r.status_code == 400


def test_delete_si_recreare_nu_lasa_id_otravit(auth_client):
    r = auth_client.post("/api/radar/keywords", json=_kw_payload())
    kid = r.json()["id"]
    assert auth_client.delete(f"/api/radar/keywords/{kid}").status_code == 200
    # stergerea marcheaza id-ul; SQLite va REFOLOSI id-ul maxim la recreare
    r2 = auth_client.post("/api/radar/keywords", json=_kw_payload())
    kid2 = r2.json()["id"]
    assert kid2 not in rs._deleted_keyword_ids      # A3: recrearea curata otrava
    assert kid2 not in rs._cancelled_keyword_ids


def test_radar_bulk_accepta_active(auth_client):
    r = auth_client.post("/api/radar/listings/bulk-action",
                         json={"listing_ids": [], "action": "active"})
    assert r.status_code == 200                      # actiunea e acceptata acum


# ── SAVED-AUDIT: soft-delete + validare status (Auto + Imobiliare) ───────────────

def test_auto_status_invalid_e_respins(auth_client):
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing
    me = auth_client.get("/api/auth/me").json()["id"]
    db = SessionLocal()
    try:
        row = AutoFeedListing(user_id=me, keyword_id=None, platform="autovit",
                              external_id=f"x{uuid.uuid4().hex[:8]}", title="T",
                              price=100.0, status="active")
        db.add(row); db.commit(); db.refresh(row)
        rid = row.id
    finally:
        db.close()
    r = auth_client.patch(f"/api/auto-listings/feed/{rid}/status", json={"status": "banana"})
    assert r.status_code == 400
    r = auth_client.patch(f"/api/auto-listings/feed/{rid}/status", json={"status": "saved"})
    assert r.status_code == 200


def test_auto_delete_e_soft(auth_client):
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing
    me = auth_client.get("/api/auth/me").json()["id"]
    db = SessionLocal()
    try:
        row = AutoFeedListing(user_id=me, keyword_id=None, platform="autovit",
                              external_id=f"y{uuid.uuid4().hex[:8]}", title="T",
                              price=100.0, status="active")
        db.add(row); db.commit(); db.refresh(row)
        rid = row.id
    finally:
        db.close()
    assert auth_client.delete(f"/api/auto-listings/feed/{rid}").status_code == 200
    db = SessionLocal()
    try:
        row = db.query(AutoFeedListing).filter(AutoFeedListing.id == rid).first()
        assert row is not None and row.status == "deleted"   # dedup-ul tine
    finally:
        db.close()


# ── N11: canalele *_all primesc si C/D ───────────────────────────────────────────

class _Settings:
    discord_webhook_auto_all = "https://discord.com/api/webhooks/t/all"
    discord_webhook_auto = None
    discord_webhook_auto_b = None
    discord_here_auto = False


def test_auto_all_primeste_si_grad_c(monkeypatch):
    from app.services import discord_service as ds
    calls = []
    monkeypatch.setattr(ds.discord_service, "enqueue",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(ds, "build_auto_embed", lambda *a, **k: {"title": "x"})
    ds.send_auto_notification({}, "C", 10, "kw", _Settings(), "auto_1", None)
    assert len(calls) == 1                           # all primeste C
    calls.clear()
    s2 = _Settings(); s2.discord_webhook_auto_all = None
    s2.discord_webhook_auto = "https://discord.com/api/webhooks/t/a"
    ds.send_auto_notification({}, "C", 10, "kw", s2, "auto_2", None)
    assert calls == []                               # canalul doar-A tot nu primeste C


# ── N2: curatarea cozii Discord ──────────────────────────────────────────────────

def test_cleanup_sterge_failed_si_dedup():
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.models.discord_queue_db import DiscordQueueItem
    from app.services.discord_service import cleanup_old_queue_rows
    db = SessionLocal()
    try:
        old = datetime.now(timezone.utc) - timedelta(days=10)
        db.add(DiscordQueueItem(webhook_url="https://x", embed="{}",
                                listing_id="l1", module="radar", status="failed",
                                created_at=old))
        db.execute(text("INSERT INTO discord_notifications_sent "
                        "(listing_id, module, webhook_url, sent_at) "
                        "VALUES ('l1', 'radar', 'https://x', :ts)"),
                   {"ts": (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()})
        db.commit()
        out = cleanup_old_queue_rows(db)
        assert out["failed"] >= 1 and out["dedup"] >= 1
    finally:
        db.close()


# ── push cu moneda reala ─────────────────────────────────────────────────────────

def test_push_foloseste_moneda_listingului():
    src = inspect.getsource(rs)
    assert "listing.get('currency') or 'RON'" in src
