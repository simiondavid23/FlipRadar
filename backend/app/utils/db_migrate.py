"""
Lightweight idempotent database migrations.
Runs on app startup to add new columns introduced after initial deploy,
since Base.metadata.create_all() only creates tables that don't exist yet.
"""
from sqlalchemy import inspect, text
from app.database import engine


def _column_exists(inspector, table: str, column: str) -> bool:
    try:
        return any(c["name"] == column for c in inspector.get_columns(table))
    except Exception:
        return False


def _table_exists(inspector, table: str) -> bool:
    try:
        return inspector.has_table(table)
    except Exception:
        return False


def run_migrations():
    """Apply any pending column additions."""
    inspector = inspect(engine)

    migrations = []

    # Alerts: add `currency` column (default EUR)
    if _table_exists(inspector, "alerts") and not _column_exists(inspector, "alerts", "currency"):
        migrations.append(
            "ALTER TABLE alerts ADD COLUMN currency VARCHAR DEFAULT 'EUR'"
        )

    # Watchlist: notes column (pre-existing project includes it, but old DBs may not)
    if _table_exists(inspector, "watchlist_items") and not _column_exists(
        inspector, "watchlist_items", "notes"
    ):
        migrations.append("ALTER TABLE watchlist_items ADD COLUMN notes VARCHAR")

    # Products: ean column (for cross-site deduplication)
    if _table_exists(inspector, "products") and not _column_exists(
        inspector, "products", "ean"
    ):
        migrations.append("ALTER TABLE products ADD COLUMN ean VARCHAR")

    # Products: resale_price column (estimated resale price for profit tracking)
    if _table_exists(inspector, "products") and not _column_exists(
        inspector, "products", "resale_price"
    ):
        migrations.append("ALTER TABLE products ADD COLUMN resale_price FLOAT")

    # Users: security question columns (for password reset flow)
    if _table_exists(inspector, "users") and not _column_exists(
        inspector, "users", "security_question"
    ):
        migrations.append("ALTER TABLE users ADD COLUMN security_question VARCHAR")
    if _table_exists(inspector, "users") and not _column_exists(
        inspector, "users", "security_answer_hash"
    ):
        migrations.append("ALTER TABLE users ADD COLUMN security_answer_hash VARCHAR")

    # Users: per-feature flags for admin-controlled access restrictions.
    # Default TRUE so existing accounts keep their current capabilities; admins
    # can flip them off individually from the Users admin page.
    feature_flags = [
        "can_use_ai",
        "can_use_scraping",
        "can_use_alerts",
        "can_use_import_export",
    ]
    for flag in feature_flags:
        if _table_exists(inspector, "users") and not _column_exists(inspector, "users", flag):
            migrations.append(
                f"ALTER TABLE users ADD COLUMN {flag} BOOLEAN NOT NULL DEFAULT TRUE"
            )

    # Products: user_id FK (per-user product isolation)
    if _table_exists(inspector, "products") and not _column_exists(
        inspector, "products", "user_id"
    ):
        migrations.append("ALTER TABLE products ADD COLUMN user_id INTEGER REFERENCES users(id)")

    if _table_exists(inspector, "products"):
        has_product_code = _column_exists(inspector, "products", "product_code")
        has_sku = _column_exists(inspector, "products", "sku")
        if has_product_code and not has_sku:
            migrations.append("ALTER TABLE products RENAME COLUMN product_code TO sku")
        elif not has_product_code and not has_sku:
            migrations.append("ALTER TABLE products ADD COLUMN sku VARCHAR")

    if _table_exists(inspector, "products") and _column_exists(inspector, "products", "asin"):
        try:
            uniques = inspector.get_unique_constraints("products")
            for uq in uniques:
                cols = uq.get("column_names") or []
                if cols == ["asin"]:
                    migrations.append(
                        f'ALTER TABLE products DROP CONSTRAINT IF EXISTS "{uq["name"]}"'
                    )
        except Exception:
            pass
        try:
            indexes = inspector.get_indexes("products")
            for idx in indexes:
                if idx.get("column_names") == ["asin"]:
                    migrations.append(f'DROP INDEX IF EXISTS "{idx["name"]}"')
        except Exception:
            pass
        migrations.append("ALTER TABLE products DROP COLUMN IF EXISTS asin")

    # Radar Marketplace: extensii ulterioare (min_price + categorie + canale notificare + listed_at)
    if _table_exists(inspector, "radar_keywords"):
        if not _column_exists(inspector, "radar_keywords", "min_price"):
            migrations.append("ALTER TABLE radar_keywords ADD COLUMN min_price FLOAT")
        if not _column_exists(inspector, "radar_keywords", "category"):
            migrations.append("ALTER TABLE radar_keywords ADD COLUMN category VARCHAR")
        if not _column_exists(inspector, "radar_keywords", "notify_email"):
            migrations.append("ALTER TABLE radar_keywords ADD COLUMN notify_email BOOLEAN NOT NULL DEFAULT TRUE")
        if not _column_exists(inspector, "radar_keywords", "notify_discord"):
            migrations.append("ALTER TABLE radar_keywords ADD COLUMN notify_discord BOOLEAN NOT NULL DEFAULT TRUE")
    if _table_exists(inspector, "radar_listings"):
        if not _column_exists(inspector, "radar_listings", "listed_at"):
            migrations.append("ALTER TABLE radar_listings ADD COLUMN listed_at TIMESTAMP")

    # Radar keywords: car_filters (JSON serializat) + extensii pentru scrapere auto
    if _table_exists(inspector, "radar_keywords"):
        if not _column_exists(inspector, "radar_keywords", "car_filters"):
            migrations.append("ALTER TABLE radar_keywords ADD COLUMN car_filters TEXT")

    # Radar settings: noi toggle-uri pentru platforme
    if _table_exists(inspector, "radar_settings"):
        for col in ("platform_lajumate_enabled", "platform_publi24_enabled",
                    "platform_autovit_enabled", "platform_mobilede_enabled"):
            if not _column_exists(inspector, "radar_settings", col):
                migrations.append(f"ALTER TABLE radar_settings ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT TRUE")

    if migrations:
        with engine.begin() as conn:
            for stmt in migrations:
                try:
                    conn.execute(text(stmt))
                    print(f"[DB Migrate] Applied: {stmt}")
                except Exception as e:
                    print(f"[DB Migrate] Failed: {stmt} -> {e}")

    _backfill_product_sources()


def _backfill_product_sources():
    """Populate product_sources from existing products that don't yet have a row."""
    inspector = inspect(engine)
    if not _table_exists(inspector, "product_sources") or not _table_exists(inspector, "products"):
        return
    with engine.begin() as conn:
        rows_to_copy = conn.execute(text("""
            SELECT p.id, p.source, p.source_url, p.current_price, p.currency
            FROM products p
            LEFT JOIN product_sources ps ON ps.product_id = p.id
            WHERE p.source IS NOT NULL AND p.source_url IS NOT NULL AND ps.id IS NULL
        """)).fetchall()
        if not rows_to_copy:
            return
        for r in rows_to_copy:
            conn.execute(
                text("""
                    INSERT INTO product_sources (product_id, source, source_url, current_price, currency, created_at, updated_at)
                    VALUES (:pid, :src, :surl, :price, :cur, NOW(), NOW())
                """),
                {"pid": r[0], "src": r[1], "surl": r[2], "price": r[3], "cur": r[4] or "EUR"},
            )
        print(f"[DB Migrate] Backfilled {len(rows_to_copy)} product_sources rows from existing products")
