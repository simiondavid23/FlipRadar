"""FB-6a — bazinul de anunturi Facebook, per (modul, keyword_id).

DE CE EXISTA: pe calea logat-out o cerere aduce ~24 de anunturi dintr-o singura
ancora, iar acoperirea nationala inseamna zeci de cereri mici, esalonate in timp de
planificator. Scannerele nu pot astepta asta intr-un apel sincron. Deci executorul
(job separat) umple bazinul in ritmul lui, iar scannerele fac INGEST din el — exact
tiparul `facebook_group_posts`, unde un job scrie si scannerul citeste.

CE SE STOCHEAZA: canonicul NEFILTRAT. Fara pret, fara exclude_words, fara categorie —
filtrele keyword-ului se aplica la CITIRE (FB-6b). Altfel o simpla schimbare de
filtru (userul urca pretul maxim) ar cere re-scanarea intregii tari, desi anunturile
sunt deja in casa.

DE CE `create_all` SI NU `_portable_migrations()`: e un tabel NOU. `_portable_migrations`
primeste doar coloane adaugate pe tabele EXISTENTE. Tabelul intra prin importul
modelului in main.py, ca `fb_scan_state`.

DE CE `listed_at` E STRING: canonicul da datetime UTC AWARE, dar SQLite intoarce NAIV
ce scrii aware (masurat la FB-3) — deci un DateTime aici ar pierde TACUT fusul intre
scriere si citire. Stringul ISO poarta offsetul, iar fiecare consumator isi face
conversia lui la FB-6b (Radar/Auto vor naiv local, Imobiliare vrea chiar ISO).
"""
from sqlalchemy import (
    Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint,
)

from app.database import Base


class FbPoolListing(Base):
    __tablename__ = "fb_pool"

    id = Column(Integer, primary_key=True, index=True)
    modul = Column(String(20), nullable=False)        # radar | auto | real_estate
    keyword_id = Column(Integer, nullable=False)
    external_id = Column(String(40), nullable=False)  # id BRUT din canonic, fara prefix
    ancora = Column(String(40), nullable=False)       # slug-ul ancorei care l-a vazut prima

    title = Column(Text, nullable=True)
    price = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    location = Column(String(200), nullable=True)
    source_url = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)
    category_id = Column(String(40), nullable=True)
    listed_at = Column(String(40), nullable=True)     # ISO cu offset (vezi docstring)

    prima_vedere_at = Column(DateTime, nullable=False, index=True)
    ultima_vedere_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("modul", "keyword_id", "external_id", name="uq_fb_pool_anunt"),
        Index("ix_fb_pool_modul_keyword", "modul", "keyword_id"),
    )

    def __repr__(self):  # pragma: no cover — doar pentru depanare
        return (f"<FbPoolListing {self.modul}/{self.keyword_id}/{self.external_id} "
                f"de la {self.ancora}>")
