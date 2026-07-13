"""ALERT-1 — webhook Discord dedicat pentru alerte de pret + Flash Deals.

Doua teste pure pe embed builders si un test de integrare care verifica ca un
Flash Deal ajunge in coada Discord (module="alerts") FARA sa strice notificarea
in-app existenta. Worker-ul Discord NU ruleaza sub pytest (FLIPRADAR_TESTING=1,
setat de conftest) — enqueue scrie doar in discord_queue, exact ce testam.
"""
from app.services.discord_service import (
    ALERT_COLORS,
    FLASH_DEAL_COLOR,
    build_alert_embed,
    build_flash_deal_embed,
)


def test_build_alert_embed_fields():
    # price_drop, fara product_url -> embed corect si fara cheia "url".
    embed = build_alert_embed(
        product_name="Casti Sony",
        current_price=199.99,
        target_price=250.0,
        currency="RON",
        alert_type="price_drop",
    )
    assert embed["title"].startswith("📉")
    assert "Casti Sony" in embed["title"]
    assert embed["color"] == 0x22c55e == ALERT_COLORS["price_drop"]

    by_name = {f["name"]: f["value"] for f in embed["fields"]}
    assert by_name["💰 Pret curent"] == "199.99 RON"
    assert by_name["🎯 Tinta"] == "250.00 RON"

    assert embed["footer"]["text"] == "FlipRadar Alerte"
    # Fara product_url -> nu adaugam cheia "url".
    assert "url" not in embed


def test_build_flash_deal_embed_fields():
    embed = build_flash_deal_embed(
        product_name="Bicicleta MTB",
        old_price=1000.0,
        new_price=850.0,
        currency="RON",
        drop_pct=0.15,
        source="emag",
        product_url="https://example.test/produs",
    )
    assert embed["title"].startswith("⚡")
    assert embed["color"] == FLASH_DEAL_COLOR

    by_name = {f["name"]: f["value"] for f in embed["fields"]}
    assert by_name["📉 Scadere"] == "-15.0%"
    assert by_name["🏪 Sursa"] == "EMAG"
    # product_url nenul -> cheia "url" e setata.
    assert embed["url"] == "https://example.test/produs"


def test_flash_deal_enqueues_discord(auth_client):
    """Un Flash Deal pune un item in coada Discord pe webhook-ul dedicat de alerte
    (module="alerts"). Notificarea in-app a fost eliminata in NOTIF-1."""
    from app.database import SessionLocal
    from app.models.user import User
    from app.models.product import Product
    from app.models.radar_settings import RadarSettings
    from app.models.discord_queue_db import DiscordQueueItem
    from app.utils.alert_checker import _check_and_send_flash_deals

    db = SessionLocal()
    try:
        # auth_client a inregistrat exact un user (clean_db a golit tabelele inainte).
        user = db.query(User).first()
        assert user is not None

        db.add(RadarSettings(
            user_id=user.id,
            discord_webhook_alerts="https://discord.test/wh",
        ))
        product = Product(
            user_id=user.id,
            name="FlashDeal test produs",
            current_price=50.0,
            currency="EUR",
        )
        db.add(product)
        db.commit()
        db.refresh(product)

        # 100 -> 50 = scadere de 50% (peste pragul implicit de 15%).
        _check_and_send_flash_deals(db, product, 100.0, 50.0, "emag")
        db.commit()

        # Exact un item Discord, pe modulul "alerts", cu listing_id de flash deal.
        items = db.query(DiscordQueueItem).filter(
            DiscordQueueItem.module == "alerts"
        ).all()
        assert len(items) == 1
        assert items[0].listing_id.startswith(f"flashdeal-{product.id}-")
    finally:
        db.close()
