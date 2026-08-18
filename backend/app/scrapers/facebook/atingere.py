"""FBS-4 — atingerea programata a sesiunii Facebook.

CE NU E: re-login. Interdictia R5 ramane INTEGRAL in vigoare — nimic nu se
autentifica automat. Atingerea incarca o sesiune DEJA VALIDA, o foloseste uman-like
cateva zeci de secunde si re-salveaza `storage_state`-ul reimprospatat. Daca sesiunea
e moarta, atingerea RAPORTEAZA si se opreste; nu incearca sa se logheze, nu deschide
formularul de login, nu completeaza nimic.

E SI PROPRIA EI JUSTIFICARE. Nu stim daca `xs` se roteste la utilizare, deci nu stim
daca mecanismul asta rezolva o problema reala sau una imaginata. De-aia fiecare
atingere inregistreaza CE S-A SCHIMBAT fata de starea dinainte — nume de cookie-uri si
date de expirare, niciodata valori. Dupa cateva rulari, jurnalul decide:
  · `xs` schimbat la FIECARE atingere -> intervalul de 12 h e probabil prea mare;
  · `xs` neschimbat dupa cateva zile -> mecanismul nu rezolva nimic, se opreste.

DE CE AICI, si nu langa Playwright-ul existent din `services/radar/facebook_auth.py`:
acela e protectia R5 si nu se atinge. Atingerea e parte din ciclul de viata al
pachetului `facebook` — serveste `FB_SESIUNE_PATH`, aceeasi cale pe care o citeste
`client._cale_sesiune()`, si se coordoneaza cu zavorul executorului. Tinuta aici,
coordonarea ramane interna pachetului in loc sa devina o dependinta intre pachete.

AMPRENTA: se lanseaza pe ACEEASI cale ca `start_facebook_login_session` — Chrome real
cu fallback pe Chromium. Browserul care reimprospateaza sesiunea trebuie sa fie cel
care a creat-o; altfel reimprospatarea e chiar semnalul pe care voiam sa-l evitam.
"""
import json
import os
import random
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services.log_manager import log_manager

from .client import _cale_sesiune
from .parse import looks_like_login_wall

# Cookie-urile fara de care o stare noua nu e o sesiune, ci un storage anonim.
_OBLIGATORII = ("c_user", "xs")
_DOMENIU = "facebook.com"
_COPII_PASTRATE = 3
_DURATA_IMPLICITA_S = 40.0

# Ultima atingere, pentru `stare_executor`. In memorie, ca fereastra de la FBS-3:
# jurnalul e sursa de adevar, asta e comoditatea.
_ultima = None


def ultima_atingere() -> Optional[dict]:
    return dict(_ultima) if _ultima else None


# ══════════════════════════════════════════════════════════════════════════════
# Citire, validare, comparatie — pur, fara browser si fara disc scris
# ══════════════════════════════════════════════════════════════════════════════
def citeste_storage(cale) -> Optional[dict]:
    try:
        brut = json.loads(Path(cale).read_text(encoding="utf-8"))
        return brut if isinstance(brut, dict) and isinstance(brut.get("cookies"), list) \
            else None
    except Exception:
        return None


def _dupa_nume(storage: dict) -> dict:
    """Cookie-urile de pe facebook.com, indexate pe nume."""
    return {c.get("name"): c for c in (storage or {}).get("cookies", [])
            if _DOMENIU in (c.get("domain") or "") and c.get("name")}


def valideaza(nou: Optional[dict], vechi: Optional[dict]) -> tuple:
    """(ok, motiv). Se ruleaza INAINTE de a atinge fisierul.

    O atingere ratata care suprascrie o sesiune buna ar fi mai rea decat lipsa
    atingerii — si e mai periculoasa decat bug-ul documentat in `facebook_auth.py`,
    fiindca ruleaza AUTOMAT, nu la cererea cuiva.
    """
    if not isinstance(nou, dict) or not isinstance(nou.get("cookies"), list):
        return False, "starea noua nu are forma de storage_state"
    n = _dupa_nume(nou)
    lipsa = [c for c in _OBLIGATORII if c not in n or not n[c].get("value")]
    if lipsa:
        return False, f"starea noua n-are {lipsa} pe {_DOMENIU} — pare storage anonim"
    if vechi:
        v = _dupa_nume(vechi)
        vechi_user, nou_user = (v.get("c_user") or {}).get("value"), n["c_user"].get("value")
        if vechi_user and nou_user != vechi_user:
            return False, "`c_user` s-a schimbat — e ALT CONT, nu o reimprospatare"
    return True, ""


def compara(vechi: Optional[dict], nou: Optional[dict]) -> dict:
    """Ce s-a schimbat, FARA nicio valoare de cookie.

    Asta e masuratoarea care justifica (sau infirma) intreaga runda, deci trebuie sa
    fie citibila din jurnal — dar un `xs` scris in jurnal e un jeton de sesiune scurs
    intr-un fisier de loguri. Se raporteaza doar NUMELE si datele de expirare.
    """
    v, n = _dupa_nume(vechi or {}), _dupa_nume(nou or {})
    schimbate = sorted(k for k in (v.keys() & n.keys())
                       if v[k].get("value") != n[k].get("value"))
    expirari = {}
    for k in sorted(v.keys() & n.keys()):
        if v[k].get("expires") != n[k].get("expires"):
            expirari[k] = {"inainte": v[k].get("expires"), "dupa": n[k].get("expires")}
    return {
        "schimbate": schimbate,
        "aparute": sorted(n.keys() - v.keys()),
        "disparute": sorted(v.keys() - n.keys()),
        "expirari_noi": expirari,
        "xs_schimbat": "xs" in schimbate,
        "datr_schimbat": "datr" in schimbate,
        "ceva_schimbat": bool(schimbate or (n.keys() ^ v.keys()) or expirari),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Scrierea, cu plasa
# ══════════════════════════════════════════════════════════════════════════════
def _copie_de_siguranta(cale: Path) -> Optional[Path]:
    if not cale.exists():
        return None
    marcaj = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tinta = cale.with_name(f"{cale.name}.bak-{marcaj}")
    try:
        tinta.write_bytes(cale.read_bytes())
    except Exception as exc:
        log_manager.emit("radar", "WARN",
            f"Facebook atingere: copia de siguranta a esuat ({type(exc).__name__})")
        return None
    vechi = sorted(cale.parent.glob(f"{cale.name}.bak-*"))
    for x in vechi[:-_COPII_PASTRATE]:
        try:
            x.unlink()
        except OSError:
            pass
    return tinta


def scrie_cu_plasa(cale, nou: dict, vechi: Optional[dict]) -> tuple:
    """(scris, motiv). Valideaza, face copie, scrie ATOMIC. La orice esec: nu scrie."""
    ok, motiv = valideaza(nou, vechi)
    if not ok:
        log_manager.emit("radar", "WARN",
            f"Facebook atingere: NU se scrie — {motiv}; sesiunea ramane neatinsa")
        return False, motiv

    cale = Path(cale)
    _copie_de_siguranta(cale)
    # Scriere ATOMICA: temporar in acelasi director + os.replace. O scriere directa
    # intrerupta lasa un storage_state trunchiat, adica o sesiune pierduta fara mesaj.
    fd, tmp = tempfile.mkstemp(dir=str(cale.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(nou, f, ensure_ascii=False)
        os.replace(tmp, cale)
    except Exception as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        log_manager.emit("radar", "WARN",
            f"Facebook atingere: scrierea a esuat ({type(exc).__name__}) — "
            f"originalul e neatins")
        return False, f"scriere esuata: {type(exc).__name__}"
    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# Singura functie care atinge Playwright — injectabila, deci testabila prin inlocuire
# ══════════════════════════════════════════════════════════════════════════════
def navigator_playwright(cale_sesiune: str, *, durata_s: float = _DURATA_IMPLICITA_S,
                         sleep=time.sleep) -> tuple:
    """(storage_nou|None, motiv_esec|None). Naviga uman-like, NU apasa nimic.

    Nu deschide anunturi, nu salveaza, nu trimite mesaje. Doar incarca Marketplace,
    asteapta, deruleaza putin, cu pauze neregulate — sub un minut in total.

    AVANTAJ fata de calea curl a nucleului: aici avem `page.url` DUPA redirecturi.
    FBS-0 a notat ca `client.get`/`post` nu expun URL-ul final, deci un redirect spre
    `/login/` sau `/checkpoint/` se putea detecta doar din continut. Aici se vede direct.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "playwright nu e instalat"

    from .client import _are_checkpoint

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=cale_sesiune)
        try:
            page = context.new_page()
            page.goto("https://www.facebook.com/marketplace/",
                      wait_until="domcontentloaded")
            sleep(random.uniform(2.5, 5.0))

            url, corp = page.url, ""
            try:
                corp = page.content()
            except Exception:
                corp = ""
            if "/login" in url or "/checkpoint" in url \
                    or looks_like_login_wall(corp) or _are_checkpoint(corp):
                return None, f"aterizare pe login/checkpoint ({url[:80]})"

            capat = time.time() + max(float(durata_s), 1.0)
            while time.time() < capat:
                try:
                    page.mouse.wheel(0, random.randint(300, 900))
                except Exception:
                    pass
                sleep(random.uniform(3.0, 7.5))

            return context.storage_state(), None
        finally:
            for x in (context, browser):
                try:
                    x.close()
                except Exception:
                    pass


# ══════════════════════════════════════════════════════════════════════════════
def atinge(*, navigator=None, durata_s: float = _DURATA_IMPLICITA_S) -> dict:
    """O atingere completa. Intoarce un rezumat; nu arunca niciodata."""
    global _ultima
    rezumat = {"la": datetime.now(timezone.utc).isoformat(), "reusit": False,
               "motiv": None, "schimbari": None}

    cale = _cale_sesiune()
    if not cale:
        rezumat["motiv"] = "FB_SESIUNE_PATH nesetata sau fisierul nu exista"
        log_manager.emit("radar", "INFO",
            f"Facebook atingere: sarita — {rezumat['motiv']}")
        _ultima = rezumat
        return rezumat

    # DOUA SESIUNI CONCURENTE ALE ACELUIASI CONT sunt un declansator de checkpoint de
    # sine statator. Se foloseste zavorul EXISTENT al executorului, nu unul nou; daca
    # nu se obtine, se sare peste rulare si se incearca la urmatoarea programare.
    from .executor import zavor_executor
    with zavor_executor(blocking=False) as obtinut:
        if not obtinut:
            rezumat["motiv"] = "un tick de executor ruleaza — se sare"
            log_manager.emit("radar", "INFO",
                f"Facebook atingere: sarita — {rezumat['motiv']}")
            _ultima = rezumat
            return rezumat

        vechi = citeste_storage(cale)
        nav = navigator or navigator_playwright
        try:
            nou, esec = nav(cale, durata_s=durata_s)
        except Exception as exc:
            nou, esec = None, f"{type(exc).__name__}: {str(exc)[:120]}"

        if nou is None:
            rezumat["motiv"] = esec or "navigatorul n-a intors o stare"
            log_manager.emit("radar", "WARN",
                f"Facebook atingere: ESUATA — {rezumat['motiv']}. "
                f"Sesiunea NU s-a rescris.")
            _ultima = rezumat
            return rezumat

        schimbari = compara(vechi, nou)
        scris, motiv = scrie_cu_plasa(cale, nou, vechi)
        rezumat.update({"reusit": scris, "motiv": motiv or None,
                        "schimbari": schimbari})
        if scris:
            log_manager.emit("radar", "INFO",
                "FBATINGERE " + " ".join([
                    f"la={rezumat['la']}", "reusit=1",
                    f"xs_schimbat={int(schimbari['xs_schimbat'])}",
                    f"datr_schimbat={int(schimbari['datr_schimbat'])}",
                    f"ceva_schimbat={int(schimbari['ceva_schimbat'])}",
                    f"schimbate={schimbari['schimbate']}",
                    f"aparute={schimbari['aparute']}",
                    f"disparute={schimbari['disparute']}",
                    f"expirari_noi={sorted(schimbari['expirari_noi'])}",
                ]))
        _ultima = rezumat
        return rezumat
