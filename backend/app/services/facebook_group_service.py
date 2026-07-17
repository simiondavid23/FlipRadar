from datetime import datetime, timedelta
from typing import Optional
from app.database import SessionLocal
from app.models.facebook_group_config import FacebookGroupConfig
from app.models.facebook_group_post import FacebookGroupPost
from app.models.radar_settings import RadarSettings
from app.scrapers.facebook_group_scraper import scrape_facebook_group
from app.services.log_manager import log_manager, set_log_user
from app.services.radar.discord_service import send_system_alert
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
        # Citit INAINTE de suprascriere (dupa rollback => valoarea persistata, adica
        # statusul rularii precedente), ca sa stim daca e o intrare noua in stare.
        was_expired = (config.last_run_status == "cookies_expirate")
        config.last_run_at = now
        config.last_run_status = (
            "cookies_expirate" if "COOKIES_EXPIRATE" in error_msg
            else "eroare"
        )
        db.commit()

        # FBG-1 — alerta la INTRAREA in stare (pattern-ul de tranzitie al watchdog-urilor):
        # repetitiile nu re-alerteaza, reminder-ul zilnic (check_cookie_expiry) preia de acolo.
        if config.last_run_status == "cookies_expirate" and not was_expired:
            _alert_cookies_expired(db, config.user_id, [config.group_name])

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


def _alert_webhook_for(db, user_id: int) -> Optional[str]:
    """FBG-1 — webhook-ul de alerte de sistem al userului: discord_webhook_alerts
    (conventia C-15, canalul semantic de alerte), fallback discord_webhook_all
    (conventia RP-6) cand alerts e gol. None = fara Discord (ramane live logs)."""
    s = db.query(RadarSettings).filter(RadarSettings.user_id == user_id).first()
    if not s:
        return None
    return s.discord_webhook_alerts or s.discord_webhook_all


def _alert_cookies_expired(db, user_id: int, group_names: list) -> None:
    """FBG-1 — alerta de sesiune FB expirata: live logs intotdeauna, Discord
    best-effort. Folosita si la tranzitie (din _process_config), si de
    reminder-ul zilnic (check_cookie_expiry)."""
    names = ", ".join(sorted(n for n in group_names if n)) or "grupurile configurate"
    text = (f"⚠️ Grupuri Facebook — sesiunea Facebook a expirat pentru: {names}. "
            f"Reîncarcă cookie-urile în pagina Grupuri Facebook pentru a relua scanarea.")
    set_log_user(user_id)
    log_manager.emit("real_estate", "WARN", text)
    url = _alert_webhook_for(db, user_id)
    if url:
        try:
            send_system_alert(url, text)
        except Exception as exc:
            print(f"[FB Groups] Alerta Discord esuata (user {user_id}): {exc}")


def check_cookie_expiry():
    """FBG-1 — reminder zilnic (09:00): userii cu configuri active blocate pe
    "cookies_expirate" primesc o alerta pe Discord (send_system_alert) + live logs.
    Un mesaj pe zi per user, cu toate grupurile afectate. Inlocuieste notificarea
    in-app eliminata la NOTIF-1 (functia fusese pastrata ca no-op)."""
    set_log_user(None)  # MON-4 — reset defensiv pe thread de pool
    db = SessionLocal()
    try:
        rows = db.query(FacebookGroupConfig).filter(
            FacebookGroupConfig.is_active == True,  # noqa: E712
            FacebookGroupConfig.last_run_status == "cookies_expirate",
        ).all()
        by_user: dict = {}
        for cfg in rows:
            by_user.setdefault(cfg.user_id, []).append(cfg.group_name)
        for user_id, names in by_user.items():
            _alert_cookies_expired(db, user_id, names)
    finally:
        set_log_user(None)
        db.close()
