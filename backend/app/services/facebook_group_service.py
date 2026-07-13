from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.facebook_group_config import FacebookGroupConfig
from app.models.facebook_group_post import FacebookGroupPost
from app.scrapers.facebook_group_scraper import scrape_facebook_group
from app.services.real_estate.extractor import (
    extract_real_estate_data,
    passes_keyword_filter,
)
from app.utils.cookie_crypto import decrypt_cookies


async def _process_config(db, config) -> int:
    """Scrapeaza si proceseaza un singur config. Seteaza last_run_at/status,
    commit. Returneaza numarul de postari noi gasite."""
    now = datetime.utcnow()
    try:
        cookies = decrypt_cookies(config.cookies_encrypted)

        raw_posts = await scrape_facebook_group(
            group_url=config.group_url,
            cookies=cookies,
            last_run_at=config.last_run_at,
            max_posts=50,
        )

        new_count = 0

        for post in raw_posts:
            # Filtru keywords (regex, fara AI)
            if not passes_keyword_filter(
                post["text"],
                config.keywords or [],
                config.negative_keywords or [],
            ):
                continue

            # Deduplicare
            exists = db.query(FacebookGroupPost).filter(
                FacebookGroupPost.post_id == post["post_id"],
                FacebookGroupPost.user_id == config.user_id,
            ).first()
            if exists:
                continue

            # Extragere date structurate (regex, fara AI)
            extracted = extract_real_estate_data(post["text"])

            new_post = FacebookGroupPost(
                user_id=config.user_id,
                config_id=config.id,
                post_id=post["post_id"],
                group_url=config.group_url,
                text=post["text"][:1000],
                pret=extracted.get("pret"),
                moneda=extracted.get("moneda"),
                tip_anunt=extracted.get("tip_anunt"),
                tip_proprietate=extracted.get("tip_proprietate"),
                suprafata_mp=extracted.get("suprafata_mp"),
                etaj=extracted.get("etaj"),
                zona=extracted.get("zona"),
                termen=extracted.get("termen"),
                facilitati=extracted.get("facilitati"),
                posted_at=post.get("posted_at"),
            )
            db.add(new_post)
            db.flush()

            new_count += 1

        config.last_run_at = now
        config.last_run_status = "ok"
        db.commit()

        if new_count > 0:
            print(f"[FB Groups] {config.group_name}: {new_count} postari noi")

        return new_count

    except Exception as e:
        error_msg = str(e)
        try:
            db.rollback()
        except Exception:
            pass
        config.last_run_at = now
        config.last_run_status = (
            "cookies_expirate" if "COOKIES_EXPIRATE" in error_msg
            else "eroare"
        )
        db.commit()

        return 0


async def run_facebook_group_checks():
    """
    Job principal rulat de APScheduler.
    Verifica toate grupurile active ale tuturor utilizatorilor.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()

        configs = db.query(FacebookGroupConfig).filter(
            FacebookGroupConfig.is_active == True,  # noqa: E712
            FacebookGroupConfig.cookies_encrypted.isnot(None),
        ).all()

        for config in configs:
            # Verifica daca e timpul sa rulam pentru acest config
            if config.last_run_at:
                next_run = config.last_run_at + timedelta(
                    hours=config.check_interval_hours
                )
                if now < next_run:
                    continue

            await _process_config(db, config)

    finally:
        db.close()


async def run_single_config_check(config_id: int, user_id: int) -> int:
    """Ruleaza imediat o verificare pentru un singur config (manual / test-run),
    ignorand intervalul. Returneaza numarul de postari noi."""
    db = SessionLocal()
    try:
        config = db.query(FacebookGroupConfig).filter(
            FacebookGroupConfig.id == config_id,
            FacebookGroupConfig.user_id == user_id,
        ).first()
        if not config or not config.cookies_encrypted:
            return 0
        return await _process_config(db, config)
    finally:
        db.close()


def check_cookie_expiry():
    """Job zilnic — dezactivat in NOTIF-1.

    Avertizarea de expirare a cookie-urilor Facebook era o notificare in-app,
    eliminata complet in NOTIF-1. Functia e pastrata ca no-op fiindca scheduler-ul
    (app/main.py) o refera; la esec de scraping statusul 'cookies_expirate' se
    seteaza in continuare in _process_config.
    """
    return
