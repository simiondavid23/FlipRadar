"""FBS-5 — citirea din `fb_pool`, in forma CANONICA a nucleului.

De ce exista modulul asta si nu trei citiri in consumatori: forma intoarsa catre
interfata trebuie sa fie IDENTICA intre calea vie si bazin, altfel comutarea rupe
tacit interfata. Solutia care garanteaza asta prin CONSTRUCTIE, nu prin atentie:

    bazin -> dict CANONIC (exact forma pe care o produce `parse.canonic`)
          -> ACELASI cod de filtrare/formatare pe care il foloseste deja calea vie

Adica modulul asta NU stie nimic despre forma finala. Intoarce canonice, iar fiecare
consumator le trece prin propriul lui formator, cel existent. Daca as fi construit
aici dicturile finale, ar fi trebuit sa reproduc trei forme diferite si sa le tin
sincronizate manual — exact tiparul de defect pe care seria l-a prins de sase ori.

`listed_at` se reintoarce la DATETIME AWARE: bazinul il tine ca string ISO cu offset
(vezi docstring-ul din `models/fb_pool.py`), iar `canonic` il da aware. Fara conversia
inversa, `_naiv_local` din Radar ar primi un string si ar crapa, iar Imobiliare ar
face `fromisoformat` pe un obiect. Conversia sta AICI, o singura data.
"""
from datetime import datetime
from typing import Optional

from app.models.fb_pool import FbPoolListing


def _listed_at(brut: Optional[str]):
    """String ISO din bazin -> datetime aware, ca `canonic`. None ramane None."""
    if not brut:
        return None
    try:
        return datetime.fromisoformat(brut)
    except (TypeError, ValueError):
        return None


def rand_la_canonic(r) -> dict:
    """Un rand de bazin, in EXACT forma pe care o produce `parse.canonic`."""
    return {
        "external_id": r.external_id,
        "title": r.title,
        "price": r.price,
        "currency": r.currency,
        "location": r.location,
        "image_url": r.image_url,
        "listed_at": _listed_at(r.listed_at),
        "category_id": r.category_id,
        "source_url": r.source_url,
    }


def citeste(db, modul: str, keyword_id: Optional[int]) -> list[dict]:
    """Anunturile din bazin pentru o pereche (modul, keyword_id), ca dicturi canonice.

    Fara `keyword_id` NU se poate interoga: bazinul e cheiat pe el. Se intoarce lista
    goala, iar apelantul e cel care avertizeaza — el stie in ce modul e.

    Ordinea e descrescatoare dupa `prima_vedere_at` (coloana INDEXATA), ca cele mai
    proaspete sa vina primele — aceeasi asteptare ca pe calea vie, unde Facebook
    intoarce feed-ul sortat.
    """
    if not keyword_id:
        return []
    randuri = (db.query(FbPoolListing)
               .filter(FbPoolListing.modul == modul,
                       FbPoolListing.keyword_id == keyword_id)
               .order_by(FbPoolListing.prima_vedere_at.desc())
               .all())
    return [rand_la_canonic(r) for r in randuri]


def sterge_vechi(db, zile: float) -> int:
    """Sterge randurile nevazute de mai mult de `zile`. Intoarce cate s-au sters.

    Se sterge pe `ultima_vedere_at`, NU pe `prima_vedere_at`: un anunt inca vazut la
    fiecare trecere e VIU, indiferent cand a aparut prima data. Stergerea pe
    `prima_vedere_at` ar arunca exact anunturile de lunga durata, care sunt si cele
    mai des cele interesante.

    `ultima_vedere_at` NU e indexat (vezi `models/fb_pool.py`), deci asta e o scanare
    de tabel. Pe un bazin de ordinul miilor de randuri, rulata o data pe zi, e
    neglijabila. Daca bazinul creste la sute de mii, indexul devine necesar — dar el e
    SCHEMA, deci alta runda.
    """
    from datetime import timedelta, timezone
    prag = datetime.now(timezone.utc) - timedelta(days=float(zile))
    # Bazinul scrie `prima_vedere_at`/`ultima_vedere_at` prin `_acum()` (UTC aware),
    # dar SQLite le intoarce naive. Comparatia se face pe naiv-UTC, ca sa nu amestecam
    # conventiile — exact motivul pentru care `_ca_utc` exista in planificator.
    prag_naiv = prag.replace(tzinfo=None)
    n = (db.query(FbPoolListing)
         .filter(FbPoolListing.ultima_vedere_at < prag_naiv)
         .delete(synchronize_session=False))
    db.commit()
    return int(n or 0)


def marime(db) -> dict:
    """Cate randuri, pe module, si varsta celui mai vechi. Trei cifre care spun
    imediat daca retentia functioneaza."""
    from sqlalchemy import func
    pe_modul = dict(db.query(FbPoolListing.modul, func.count(FbPoolListing.id))
                    .group_by(FbPoolListing.modul).all())
    total = sum(pe_modul.values())
    cea_mai_veche = db.query(func.min(FbPoolListing.ultima_vedere_at)).scalar()
    varsta_zile = None
    if cea_mai_veche is not None:
        ref = cea_mai_veche
        if ref.tzinfo is not None:
            ref = ref.replace(tzinfo=None)
        varsta_zile = round((datetime.utcnow() - ref).total_seconds() / 86400.0, 2)
    return {
        "total": int(total),
        "pe_modul": {str(k): int(v) for k, v in pe_modul.items()},
        "cea_mai_veche_ultima_vedere": (cea_mai_veche.isoformat()
                                        if cea_mai_veche is not None else None),
        "varsta_maxima_zile": varsta_zile,
    }
