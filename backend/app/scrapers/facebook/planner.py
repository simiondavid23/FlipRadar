"""FB-3 — planificatorul: ce perechi (keyword x ancora) se scaneaza si cand.

Decide, nu executa. Nu apeleaza nucleul, nu face cereri, nu doarme. Cablarea la un
job real e FB-6.

TREI mecanisme, in ordinea importantei:

1. BUGETUL per tick. La 51 de ancore per keyword, "scaneaza tot ce e scadent" ar
   insemna sute de cereri intr-un minut. Bugetul (implicit 12 la un tick de 5 minute,
   adica 144/ora) e plafonul dur; perechile scadente peste buget asteapta urmatorul
   tick, iar ordinea dupa intarziere le garanteaza ca nu raman in urma la infinit.

2. INTERVALUL ADAPTIV per pereche. O ancora productiva (multe anunturi noi) se
   scaneaza des, una moarta rar. Asa bugetul fix se duce unde exista marfa, fara sa
   fie nevoie de configurare manuala per oras.

3. FRANA. Nu e optionala: bugetul de 144 de cereri/ora e agresiv si nu stim pragul
   real al Facebook. La orice semnal de blocaj bugetul se INJUMATATESTE si revine
   incet (+1 la fiecare fereastra fara incident). Fara ea, prima zi de blocaje ar
   continua sa loveasca serverul in acelasi ritm.

Frana traieste IN MEMORIA instantei (procesul sta pornit 24/7 pe Pi). Un restart o
reseteaza la bugetul plin — acceptabil: dupa un restart oricum nu stim daca blocajul
mai e activ, iar primul semnal o coboara imediat la loc.

Maparea pentru FB-6 (nu se citeste in runda asta): campul de activare e `is_active`
la TOATE cele trei tabele de keyword-uri — `radar_keywords` (RadarKeyword),
`auto_keywords` (AutoKeyword), `real_estate_keywords` (RealEstateMonitorKeyword);
toate au si `active_hours_start` / `active_hours_end`. Valorile lui `modul` din
`fb_scan_state` sunt `radar`, `auto`, `real_estate`.
"""
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from app.services.log_manager import log_manager
from app.models.fb_scan_state import FbScanState

from .anchors import ANCORE, selecteaza

_TIER_IMPLICIT = {1: 30, 2: 180, 3: 480}


@dataclass
class ConfigPlanificator:
    buget_per_tick: int = 12               # FB_BUGET_PER_TICK
    interval_min_min: int = 10             # FB_INTERVAL_MIN
    interval_max_min: int = 1440           # FB_INTERVAL_MAX (24 h)
    interval_start_tier: dict = field(default_factory=lambda: dict(_TIER_IMPLICIT))
    frana_activa: bool = True              # FB_FRANA (0/1)
    frana_revenire_min: int = 30           # FB_FRANA_REVENIRE_MIN
    ancore_dezactivate: tuple = ()         # FB_ANCORE_DEZACTIVATE (lista cu virgula)


def config_din_env() -> ConfigPlanificator:
    """Config din FB_* cu default-urile de mai sus. NU se apeleaza in teste.

    Variabile citite: FB_BUGET_PER_TICK, FB_INTERVAL_MIN, FB_INTERVAL_MAX,
    FB_FRANA (0/false/no = frana oprita), FB_FRANA_REVENIRE_MIN,
    FB_ANCORE_DEZACTIVATE (slug-uri separate prin virgula).
    `interval_start_tier` NU e configurabil din env — e o decizie de dimensionare,
    nu un buton de operare.
    """
    def _int(nume, implicit):
        try:
            brut = os.getenv(nume)
            return int(brut) if brut not in (None, "") else implicit
        except (TypeError, ValueError):
            return implicit

    brut_frana = (os.getenv("FB_FRANA") or "").strip().lower()
    frana = brut_frana not in ("0", "false", "no", "off")

    brut_anc = os.getenv("FB_ANCORE_DEZACTIVATE") or ""
    dezactivate = tuple(s.strip().lower() for s in brut_anc.split(",") if s.strip())

    return ConfigPlanificator(
        buget_per_tick=_int("FB_BUGET_PER_TICK", 12),
        interval_min_min=_int("FB_INTERVAL_MIN", 10),
        interval_max_min=_int("FB_INTERVAL_MAX", 1440),
        frana_activa=frana,
        frana_revenire_min=_int("FB_FRANA_REVENIRE_MIN", 30),
        ancore_dezactivate=dezactivate,
    )


def _ca_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Datetime-ul citit din DB, adus la UTC aware.

    SQLite intoarce NAIV ce s-a scris aware (masurat), iar comparatia naiv-vs-aware
    arunca TypeError. Toate comparatiile din planificator trec pe-aici.
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


_TIER_DUPA_SLUG = {a.slug: a.tier for a in ANCORE}


class Planificator:
    """Alege perechile de scanat. `acum` e injectabil ca testele sa fie deterministe."""

    def __init__(self, sesiune, config: ConfigPlanificator,
                 *, acum: Optional[Callable[[], datetime]] = None):
        self.sesiune = sesiune
        self.config = config
        self._acum = acum or (lambda: datetime.now(timezone.utc))
        # starea franei, in memorie
        self._buget_redus = config.buget_per_tick
        self._ultimul_incident_at: Optional[datetime] = None
        self._incidente = 0
        self._trepte_raportate = 0

    # ── perechi ──────────────────────────────────────────────────────────────
    def asigura_perechi(self, modul: str, keyword_id: int, scope: str,
                        tier_start_override: Optional[int] = None) -> int:
        """Creeaza randurile lipsa pentru (modul, keyword_id) x selecteaza(scope).

        Idempotent: randurile existente NU se ating (nici intervalul, nici scadenta —
        altfel fiecare pornire ar reseta invatarea). Randurile pentru ancore iesite
        din scope raman pe loc ca istoric; excluderea lor de la planificare se face
        la FB-6, cand planificatorul va sti scope-ul curent al fiecarui keyword.

        Intoarce numarul de randuri create.
        """
        acum = self._acum()
        alese = selecteaza(scope, dezactivate=self.config.ancore_dezactivate)

        existente = {
            r.ancora for r in self.sesiune.query(FbScanState.ancora).filter(
                FbScanState.modul == modul, FbScanState.keyword_id == keyword_id)
        }

        create = 0
        for a in alese:
            if a.slug in existente:
                continue
            interval = (tier_start_override if tier_start_override is not None
                        else self.config.interval_start_tier.get(
                            a.tier, self.config.interval_max_min))
            self.sesiune.add(FbScanState(
                modul=modul, keyword_id=keyword_id, ancora=a.slug,
                interval_min=int(interval), last_run_at=None, next_due_at=acum,
                ultima_rata_noi=None, cicluri_goale=0, stare="activ"))
            create += 1
        if create:
            self.sesiune.commit()
        return create

    def alege_scadente(self) -> list:
        """Perechile de scanat acum: cele mai intarziate intai, in limita bugetului.

        Nu filtreaza dupa `stare`: "retrogradat" inseamna doar interval mai lung, nu
        oprit — un loc mort tot merita verificat o data pe zi.
        """
        acum = self._acum()
        buget = self.buget_efectiv()

        randuri = (self.sesiune.query(FbScanState)
                   .filter(FbScanState.next_due_at <= acum)
                   .all())

        dezactivate = {s.strip().lower() for s in self.config.ancore_dezactivate if s}
        scadente, necunoscute = [], set()
        for r in randuri:
            if r.ancora in dezactivate:
                continue
            if r.ancora not in _TIER_DUPA_SLUG:
                # Ancora a disparut din registru: nu stim nici tier, nici coordonate.
                necunoscute.add(r.ancora)
                continue
            scadente.append(r)
        if necunoscute:
            log_manager.emit("radar", "WARN",
                f"Facebook planificator: ancore necunoscute in fb_scan_state, ignorate: "
                f"{', '.join(sorted(necunoscute))}")

        scadente.sort(key=lambda r: (-(acum - _ca_utc(r.next_due_at)).total_seconds(),
                                     _TIER_DUPA_SLUG[r.ancora]))
        alese = scadente[:buget]

        total = self.sesiune.query(FbScanState).count()
        log_manager.emit("radar", "INFO",
            f"Facebook planificator: {len(scadente)} scadente, {len(alese)} alese, "
            f"buget {buget}, {total} perechi in total")
        return alese

    # ── rezultat + interval adaptiv ──────────────────────────────────────────
    def inregistreaza_rezultat(self, pereche: FbScanState, anunturi_intoarse: int,
                               anunturi_noi: int, blocaj: bool = False) -> FbScanState:
        """Inchide un ciclu: adapteaza intervalul si reprogrameaza perechea."""
        acum = self._acum()
        rata = anunturi_noi / max(anunturi_intoarse, 1)
        interval = int(pereche.interval_min)

        if blocaj:
            # Un blocaj nu spune nimic despre cat de productiv e locul — ar fi gresit
            # sa rarim o ancora buna fiindca Facebook ne-a oprit. Intervalul ramane;
            # raspunsul la blocaj e bugetul, prin frana.
            self.semnal_blocaj()
        elif rata >= 0.75:
            interval = max(interval // 2, self.config.interval_min_min)
        elif rata <= 0.05:
            # ceil, nu int: la intervale mici trunchierea ar putea lasa valoarea pe loc
            interval = min(math.ceil(interval * 1.5), self.config.interval_max_min)

        pereche.interval_min = interval
        pereche.cicluri_goale = (pereche.cicluri_goale or 0) + 1 if anunturi_intoarse == 0 else 0
        pereche.ultima_rata_noi = rata
        pereche.last_run_at = acum
        pereche.next_due_at = acum + timedelta(minutes=interval)
        pereche.stare = self._stare(pereche)
        self.sesiune.commit()
        return pereche

    def _stare(self, pereche: FbScanState) -> str:
        """Eticheta de stare, DERIVATA — specificatia defineste coloana, nu tranzitiile.

        `retrogradat` = intervalul a atins plafonul (exact sensul din specificatie:
        "interval mai lung"); `degradat` = a avut cel putin un ciclu gol dar inca nu e
        la plafon; altfel `activ`. Politica reala se poate fixa la FB-6.
        """
        if int(pereche.interval_min) >= self.config.interval_max_min:
            return "retrogradat"
        if (pereche.cicluri_goale or 0) > 0:
            return "degradat"
        return "activ"

    # ── frana adaptiva ───────────────────────────────────────────────────────
    def semnal_blocaj(self) -> int:
        """Injumatateste bugetul efectiv (podea 1) si reporneste ceasul de revenire."""
        nou = max(self.buget_efectiv() // 2, 1)
        self._buget_redus = nou
        self._ultimul_incident_at = self._acum()
        self._incidente += 1
        self._trepte_raportate = 0
        log_manager.emit("radar", "WARN",
            f"Facebook frana: semnal de blocaj #{self._incidente} — "
            f"buget redus la {nou} din {self.config.buget_per_tick}")
        return nou

    def buget_efectiv(self) -> int:
        """Bugetul de cereri pentru tick-ul asta.

        Singurul efect secundar: un WARN cand se urca o treapta de revenire (altfel
        revenirea ar fi invizibila in jurnale).
        """
        if not self.config.frana_activa or self._ultimul_incident_at is None:
            return self.config.buget_per_tick

        fereastra = max(int(self.config.frana_revenire_min), 1)
        scurs_min = (self._acum() - self._ultimul_incident_at).total_seconds() / 60.0
        trepte = max(int(scurs_min // fereastra), 0)
        buget = min(self.config.buget_per_tick, self._buget_redus + trepte)

        if trepte > self._trepte_raportate:
            self._trepte_raportate = trepte
            log_manager.emit("radar", "WARN",
                f"Facebook frana: revenire, treapta {trepte} — buget {buget} "
                f"din {self.config.buget_per_tick}")
        return buget

    def stare_frana(self) -> dict:
        """Sursa pentru guard_status / Jurnale la FB-6."""
        return {
            "buget_configurat": self.config.buget_per_tick,
            "buget_efectiv": self.buget_efectiv(),
            "ultimul_incident_at": self._ultimul_incident_at,
            "incidente_total": self._incidente,
        }
