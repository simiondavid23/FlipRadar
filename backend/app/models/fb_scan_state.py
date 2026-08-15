"""FB-3 — starea de scanare per PERECHE (keyword x ancora).

Schimbarea de model a modulului Facebook: unitatea de lucru nu mai e "scanul unui
keyword", ci perechea (keyword, ancora). Pe calea logat-out geografia se alege doar
prin ancora — raza e ignorata de Facebook, paginarea nu merge, un apel aduce ~24 de
anunturi dintr-un singur loc — deci acoperirea nationala inseamna multe cereri mici,
fiecare cu ritmul ei. Un keyword cu 51 de ancore are 51 de randuri aici, fiecare cu
propriul interval adaptat de cat de productiv s-a dovedit locul acela.

Tabelul se creeaza prin `Base.metadata.create_all()` (importul modelului in main.py),
ca `shop_scan_state` — NU prin `_portable_migrations()`, care primeste doar coloane
adaugate pe tabele EXISTENTE.

`next_due_at` e driverul buclei si singurul camp indexat: fiecare tick intreaba
"ce a ajuns la scadenta?", deci interogarea aia trebuie sa fie ieftina si la zeci de
mii de randuri.

ATENTIE la fusuri: datele se scriu UTC AWARE, dar SQLite le intoarce NAIVE la citire
(masurat). Orice comparatie in Python intre o valoare citita si `acum()` trebuie sa
treaca prin `planner._ca_utc()`, altfel pica cu "can't compare offset-naive and
offset-aware datetimes". Filtrarea in SQL e sigura — acolo problema nu apare.
"""
from sqlalchemy import (
    Column, DateTime, Float, Integer, String, UniqueConstraint,
)

from app.database import Base


class FbScanState(Base):
    __tablename__ = "fb_scan_state"

    id = Column(Integer, primary_key=True, index=True)
    modul = Column(String(20), nullable=False)        # real_estate | radar | auto
    keyword_id = Column(Integer, nullable=False)
    ancora = Column(String(40), nullable=False)       # slug din registrul de ancore
    interval_min = Column(Integer, nullable=False)    # intervalul curent, adaptat
    last_run_at = Column(DateTime, nullable=True)
    next_due_at = Column(DateTime, nullable=False, index=True)
    ultima_rata_noi = Column(Float, nullable=True)
    cicluri_goale = Column(Integer, nullable=False, default=0)
    stare = Column(String(12), nullable=False, default="activ")  # activ|degradat|retrogradat

    __table_args__ = (
        UniqueConstraint("modul", "keyword_id", "ancora", name="uq_fb_scan_state_pereche"),
    )

    def __repr__(self):  # pragma: no cover — doar pentru depanare
        return (f"<FbScanState {self.modul}/{self.keyword_id}/{self.ancora} "
                f"la {self.interval_min} min, scadent {self.next_due_at}>")
