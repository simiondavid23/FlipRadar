"""
Lightweight idempotent database migrations.
Runs on app startup to add new columns introduced after initial deploy,
since Base.metadata.create_all() only creates tables that don't exist yet.

Fiecare migrare e inregistrata intr-o tabela `schema_migrations` dupa ce ruleaza
cu succes, deci la fiecare pornire de dupa prima nu se mai afiseaza nimic decat
daca apare o intrare noua de migrare. Garzile de introspectie (column/table exists)
sunt pastrate ca strat suplimentar de siguranta pe baze de date existente, unde
coloanele pot exista deja (adaugate inainte sa existe tabela de tracking).
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


def _applied(conn, name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM schema_migrations WHERE migration_name = :name"),
        {"name": name},
    ).fetchone()
    return result is not None


def _migrate(conn, name: str, sql: str) -> None:
    """Ruleaza o migrare o singura data si o inregistreaza. Izoleaza erorile
    per-migrare (un statement defect nu blocheaza pornirea / restul migrarilor)."""
    if _applied(conn, name):
        return
    try:
        conn.execute(text(sql))
        conn.execute(
            text("INSERT INTO schema_migrations (migration_name) VALUES (:name)"),
            {"name": name},
        )
        conn.commit()
        print(f"[DB Migrate] Applied: {name}")
    except Exception as e:
        conn.rollback()
        print(f"[DB Migrate] Failed: {name} -> {e}")


def run_migrations():
    """Apply any pending column additions."""
    inspector = inspect(engine)

    with engine.connect() as conn:
        # Tabela de tracking — mereu sigur de rulat (idempotent).
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name VARCHAR(200) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()

        # Alerts: add `currency` column (default EUR)
        if _table_exists(inspector, "alerts") and not _column_exists(inspector, "alerts", "currency"):
            _migrate(conn, "add_alerts_currency",
                     "ALTER TABLE alerts ADD COLUMN currency VARCHAR DEFAULT 'EUR'")

        # Watchlist: notes column (pre-existing project includes it, but old DBs may not)
        if _table_exists(inspector, "watchlist_items") and not _column_exists(inspector, "watchlist_items", "notes"):
            _migrate(conn, "add_watchlist_items_notes",
                     "ALTER TABLE watchlist_items ADD COLUMN notes VARCHAR")

        # Products: ean column (for cross-site deduplication)
        if _table_exists(inspector, "products") and not _column_exists(inspector, "products", "ean"):
            _migrate(conn, "add_products_ean",
                     "ALTER TABLE products ADD COLUMN ean VARCHAR")

        # Products: resale_price column (estimated resale price for profit tracking)
        if _table_exists(inspector, "products") and not _column_exists(inspector, "products", "resale_price"):
            _migrate(conn, "add_products_resale_price",
                     "ALTER TABLE products ADD COLUMN resale_price FLOAT")

        # FlipRadar — brand dedicat + pret de lista original (pentru filtrare brand si on_sale)
        if _table_exists(inspector, "products") and not _column_exists(inspector, "products", "brand"):
            _migrate(conn, "add_products_brand",
                     "ALTER TABLE products ADD COLUMN IF NOT EXISTS brand VARCHAR(200)")
        if _table_exists(inspector, "products") and not _column_exists(inspector, "products", "original_price"):
            _migrate(conn, "add_products_original_price",
                     "ALTER TABLE products ADD COLUMN IF NOT EXISTS original_price NUMERIC(10,2)")
        # FlipRadar — subcategorie inferata per magazin (taxonomie SOURCE_CATEGORIES)
        if _table_exists(inspector, "products") and not _column_exists(inspector, "products", "subcategory"):
            _migrate(conn, "add_products_subcategory",
                     "ALTER TABLE products ADD COLUMN IF NOT EXISTS subcategory VARCHAR(200)")

        # FlipRadar — prag personalizat pentru alertele Flash Deal (implicit 0.15 = 15%)
        if _table_exists(inspector, "users") and not _column_exists(inspector, "users", "flash_deal_threshold"):
            _migrate(conn, "add_users_flash_deal_threshold",
                     "ALTER TABLE users ADD COLUMN IF NOT EXISTS flash_deal_threshold NUMERIC(5,2) DEFAULT 0.15")

        # FlipRadar — config per-functionalitate AI (JSON nullable)
        if _table_exists(inspector, "users") and not _column_exists(inspector, "users", "ai_features_config"):
            _migrate(conn, "add_users_ai_features_config",
                     "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_features_config JSON")

        # FlipRadar — Imobiliare: coloana `saved` pe real_estate_listing (tabela exista deja).
        if _table_exists(inspector, "real_estate_listing") and not _column_exists(inspector, "real_estate_listing", "saved"):
            _migrate(conn, "add_real_estate_listing_saved",
                     "ALTER TABLE real_estate_listing ADD COLUMN IF NOT EXISTS saved BOOLEAN DEFAULT FALSE")

        # FlipRadar — Grupuri Facebook: config-uri + postari (idempotent IF NOT EXISTS).
        _migrate(conn, "create_facebook_group_configs", """
            CREATE TABLE IF NOT EXISTS facebook_group_configs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                group_name VARCHAR(200) NOT NULL,
                group_url TEXT NOT NULL,
                keywords JSON DEFAULT '[]',
                negative_keywords JSON DEFAULT '[]',
                check_interval_hours INTEGER DEFAULT 2,
                is_active BOOLEAN DEFAULT TRUE,
                cookies_encrypted TEXT,
                cookies_saved_at TIMESTAMP,
                last_run_at TIMESTAMP,
                last_run_status VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        _migrate(conn, "create_facebook_group_posts", """
            CREATE TABLE IF NOT EXISTS facebook_group_posts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                config_id INTEGER NOT NULL,
                post_id VARCHAR(200),
                group_url TEXT,
                text TEXT,
                pret NUMERIC(10,2),
                moneda VARCHAR(10),
                tip_anunt VARCHAR(20),
                tip_proprietate VARCHAR(50),
                suprafata_mp INTEGER,
                etaj VARCHAR(30),
                zona VARCHAR(100),
                termen VARCHAR(20),
                facilitati VARCHAR(200),
                posted_at TIMESTAMP,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # FlipRadar — index ML pe market_listings (category, brand, sold_at).
        # create_all() nu adauga indexuri pe tabele deja existente, deci il cream aici.
        if _table_exists(inspector, "market_listings"):
            existing_idx = {i["name"] for i in inspector.get_indexes("market_listings")}
            if "ix_market_listings_category_brand_sold" not in existing_idx:
                _migrate(conn, "create_ix_market_listings_category_brand_sold",
                         "CREATE INDEX IF NOT EXISTS ix_market_listings_category_brand_sold "
                         "ON market_listings (category, brand, sold_at)")

        # Users: security question columns (for password reset flow)
        if _table_exists(inspector, "users") and not _column_exists(inspector, "users", "security_question"):
            _migrate(conn, "add_users_security_question",
                     "ALTER TABLE users ADD COLUMN security_question VARCHAR")
        if _table_exists(inspector, "users") and not _column_exists(inspector, "users", "security_answer_hash"):
            _migrate(conn, "add_users_security_answer_hash",
                     "ALTER TABLE users ADD COLUMN security_answer_hash VARCHAR")

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
                _migrate(conn, f"add_users_{flag}",
                         f"ALTER TABLE users ADD COLUMN {flag} BOOLEAN NOT NULL DEFAULT TRUE")

        # Products: user_id FK (per-user product isolation)
        if _table_exists(inspector, "products") and not _column_exists(inspector, "products", "user_id"):
            _migrate(conn, "add_products_user_id",
                     "ALTER TABLE products ADD COLUMN user_id INTEGER REFERENCES users(id)")

        if _table_exists(inspector, "products"):
            has_product_code = _column_exists(inspector, "products", "product_code")
            has_sku = _column_exists(inspector, "products", "sku")
            if has_product_code and not has_sku:
                _migrate(conn, "rename_products_product_code_to_sku",
                         "ALTER TABLE products RENAME COLUMN product_code TO sku")
            elif not has_product_code and not has_sku:
                _migrate(conn, "add_products_sku",
                         "ALTER TABLE products ADD COLUMN sku VARCHAR")

        if _table_exists(inspector, "products") and _column_exists(inspector, "products", "asin"):
            try:
                uniques = inspector.get_unique_constraints("products")
                for uq in uniques:
                    cols = uq.get("column_names") or []
                    if cols == ["asin"]:
                        _migrate(conn, f"drop_products_constraint_{uq['name']}",
                                 f'ALTER TABLE products DROP CONSTRAINT IF EXISTS "{uq["name"]}"')
            except Exception:
                pass
            try:
                indexes = inspector.get_indexes("products")
                for idx in indexes:
                    if idx.get("column_names") == ["asin"]:
                        _migrate(conn, f"drop_products_index_{idx['name']}",
                                 f'DROP INDEX IF EXISTS "{idx["name"]}"')
            except Exception:
                pass
            _migrate(conn, "drop_products_asin_column",
                     "ALTER TABLE products DROP COLUMN IF EXISTS asin")

        # Radar Marketplace: extensii ulterioare (min_price + categorie + canale notificare + listed_at)
        if _table_exists(inspector, "radar_keywords"):
            if not _column_exists(inspector, "radar_keywords", "min_price"):
                _migrate(conn, "add_radar_keywords_min_price",
                         "ALTER TABLE radar_keywords ADD COLUMN min_price FLOAT")
            if not _column_exists(inspector, "radar_keywords", "category"):
                _migrate(conn, "add_radar_keywords_category",
                         "ALTER TABLE radar_keywords ADD COLUMN category VARCHAR")
            if not _column_exists(inspector, "radar_keywords", "notify_email"):
                _migrate(conn, "add_radar_keywords_notify_email",
                         "ALTER TABLE radar_keywords ADD COLUMN notify_email BOOLEAN NOT NULL DEFAULT TRUE")
            if not _column_exists(inspector, "radar_keywords", "notify_discord"):
                _migrate(conn, "add_radar_keywords_notify_discord",
                         "ALTER TABLE radar_keywords ADD COLUMN notify_discord BOOLEAN NOT NULL DEFAULT TRUE")
            # FlipRadar — platforma unica (noul model de keyword)
            if not _column_exists(inspector, "radar_keywords", "platform"):
                _migrate(conn, "add_radar_keywords_platform",
                         "ALTER TABLE radar_keywords ADD COLUMN platform VARCHAR(50)")
            # FlipRadar — cuvinte excluse pe descriere (OLX & Vinted)
            if not _column_exists(inspector, "radar_keywords", "exclude_description_words"):
                _migrate(conn, "add_radar_keywords_exclude_description_words",
                         "ALTER TABLE radar_keywords ADD COLUMN exclude_description_words JSON")
            # FlipRadar — interval orar activ (Module 5)
            if not _column_exists(inspector, "radar_keywords", "active_hours_start"):
                _migrate(conn, "add_radar_keywords_active_hours_start",
                         "ALTER TABLE radar_keywords ADD COLUMN active_hours_start INTEGER")
            if not _column_exists(inspector, "radar_keywords", "active_hours_end"):
                _migrate(conn, "add_radar_keywords_active_hours_end",
                         "ALTER TABLE radar_keywords ADD COLUMN active_hours_end INTEGER")
            # FIX 3 — bug notificari email: randurile vechi cu notify_email NULL ar
            # trimite email implicit. Le fortam pe FALSE (opt-in explicit din UI).
            _migrate(conn, "set_radar_keywords_notify_email_default_false",
                     "UPDATE radar_keywords SET notify_email = FALSE WHERE notify_email IS NULL")
        if _table_exists(inspector, "radar_listings"):
            if not _column_exists(inspector, "radar_listings", "listed_at"):
                _migrate(conn, "add_radar_listings_listed_at",
                         "ALTER TABLE radar_listings ADD COLUMN listed_at TIMESTAMP")

        # Radar keywords: car_filters (JSON serializat) + extensii pentru scrapere auto
        if _table_exists(inspector, "radar_keywords"):
            if not _column_exists(inspector, "radar_keywords", "car_filters"):
                _migrate(conn, "add_radar_keywords_car_filters",
                         "ALTER TABLE radar_keywords ADD COLUMN car_filters TEXT")
            # FlipRadar — config wizard marketplace (platform/categorie/subcategorie/filtre) JSON
            if not _column_exists(inspector, "radar_keywords", "marketplace_config"):
                _migrate(conn, "add_radar_keywords_marketplace_config",
                         "ALTER TABLE radar_keywords ADD COLUMN IF NOT EXISTS marketplace_config TEXT")

        # Radar settings: noi toggle-uri pentru platforme
        if _table_exists(inspector, "radar_settings"):
            for col in ("platform_lajumate_enabled", "platform_publi24_enabled",
                        "platform_autovit_enabled", "platform_mobilede_enabled"):
                if not _column_exists(inspector, "radar_settings", col):
                    _migrate(conn, f"add_radar_settings_{col}",
                             f"ALTER TABLE radar_settings ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT TRUE")
            # FlipRadar — cookie-uri de sesiune LaJumate + Okazii (Module 1)
            _migrate(conn, "add_lajumate_cookie",
                     "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS lajumate_cookie TEXT")
            _migrate(conn, "add_okazii_cookie",
                     "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS okazii_cookie TEXT")

        # FlipRadar — populeaza coloana `brand` din primul cuvant al numelui pentru
        # produsele vechi care nu au brand setat inca. Rulata o singura data prin
        # tracking (numele e inregistrat dupa succes).
        if _table_exists(inspector, "products"):
            _migrate(conn, "backfill_products_brand", """
                UPDATE products
                SET brand = split_part(name, ' ', 1)
                WHERE brand IS NULL
                  AND name IS NOT NULL
                  AND length(trim(name)) > 2
            """)

        # Module 3 — reset date ML colectate ca sa repornim colectarea cu filtre
        # de calitate. Rulate o singura data (tracked in schema_migrations).
        # Numarul se afiseaza doar la rularea efectiva (nu la fiecare pornire).
        if _table_exists(inspector, "market_listings"):
            if (not _applied(conn, "cleanup_apple_market_listings_v2")
                    or not _applied(conn, "cleanup_bmw_market_listings_v2")):
                count_apple = conn.execute(text(
                    "SELECT COUNT(*) FROM market_listings WHERE category = 'electronics_apple'")).scalar()
                count_bmw = conn.execute(text(
                    "SELECT COUNT(*) FROM market_listings WHERE category = 'auto_bmw'")).scalar()
                print(f"[ML Cleanup] Deleting {count_apple} Apple + {count_bmw} BMW "
                      f"listings and restarting clean collection.")
            _migrate(conn, "cleanup_apple_market_listings_v2",
                     "DELETE FROM market_listings WHERE category = 'electronics_apple'")
            _migrate(conn, "cleanup_bmw_market_listings_v2",
                     "DELETE FROM market_listings WHERE category = 'auto_bmw'")

        # Auto Anunturi — keyword-uri + feed + index-uri + webhook Discord auto.
        _migrate(conn, "create_auto_keywords", """
            CREATE TABLE IF NOT EXISTS auto_keywords (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(200) NOT NULL,
                platform VARCHAR(50) NOT NULL,
                make VARCHAR(100),
                model VARCHAR(100),
                query TEXT,
                year_from INTEGER,
                year_to INTEGER,
                km_max INTEGER,
                price_max NUMERIC(10,2),
                price_currency VARCHAR(10) DEFAULT 'RON',
                fuel_type VARCHAR(50),
                transmission VARCHAR(50),
                body_type VARCHAR(50),
                location VARCHAR(200),
                is_active BOOLEAN DEFAULT TRUE,
                notify_email BOOLEAN DEFAULT FALSE,
                notify_discord BOOLEAN DEFAULT FALSE,
                active_hours_start INTEGER,
                active_hours_end INTEGER,
                polling_interval_minutes INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        _migrate(conn, "create_auto_feed_listings", """
            CREATE TABLE IF NOT EXISTS auto_feed_listings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                keyword_id INTEGER REFERENCES auto_keywords(id) ON DELETE SET NULL,
                platform VARCHAR(50) NOT NULL,
                external_id VARCHAR(200),
                title TEXT,
                price NUMERIC(10,2),
                currency VARCHAR(10) DEFAULT 'RON',
                year INTEGER,
                km INTEGER,
                fuel_type VARCHAR(50),
                transmission VARCHAR(50),
                body_type VARCHAR(50),
                location VARCHAR(200),
                image_url TEXT,
                images_json JSON DEFAULT '[]',
                url TEXT,
                description TEXT,
                score INTEGER DEFAULT 50,
                grade VARCHAR(5) DEFAULT 'C',
                import_score_json JSON,
                status VARCHAR(20) DEFAULT 'active',
                found_at TIMESTAMP DEFAULT NOW(),
                last_checked_at TIMESTAMP
            )
        """)

        _migrate(conn, "idx_auto_feed_user_platform",
            "CREATE INDEX IF NOT EXISTS idx_auto_feed_user_platform "
            "ON auto_feed_listings(user_id, platform, status)")

        _migrate(conn, "idx_auto_feed_external_unique",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_auto_feed_external "
            "ON auto_feed_listings(user_id, platform, external_id) "
            "WHERE external_id IS NOT NULL")

        _migrate(conn, "add_discord_webhook_auto",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS "
            "discord_webhook_auto TEXT")

        # ── Global Discord notification service (Module 1) ──
        _migrate(conn, "create_discord_notifications_sent", """
            CREATE TABLE IF NOT EXISTS discord_notifications_sent (
                id SERIAL PRIMARY KEY,
                listing_id VARCHAR(200) NOT NULL,
                module VARCHAR(50) NOT NULL,
                webhook_url TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT NOW()
            )
        """)
        _migrate(conn, "idx_discord_notif_dedup",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_notif_dedup "
            "ON discord_notifications_sent(listing_id, module, webhook_url)")

        _migrate(conn, "add_discord_auto_all",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS discord_webhook_auto_all TEXT")
        _migrate(conn, "add_discord_auto_b",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS discord_webhook_auto_b TEXT")
        _migrate(conn, "add_discord_imob_all",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS discord_webhook_imob_all TEXT")
        _migrate(conn, "add_discord_imob_a",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS discord_webhook_imob_a TEXT")
        _migrate(conn, "add_discord_imob_b",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS discord_webhook_imob_b TEXT")
        _migrate(conn, "add_discord_here_radar",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS discord_here_radar BOOLEAN DEFAULT FALSE")
        _migrate(conn, "add_discord_here_auto",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS discord_here_auto BOOLEAN DEFAULT FALSE")
        _migrate(conn, "add_discord_here_imob",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS discord_here_imob BOOLEAN DEFAULT FALSE")
        _migrate(conn, "add_custom_zone_aliases",
            "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS custom_zone_aliases JSON DEFAULT '{}'")

        # ── Imobiliare Monitor: keyword-uri + feed (Module 3) ──
        _migrate(conn, "create_real_estate_keywords", """
            CREATE TABLE IF NOT EXISTS real_estate_keywords (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(200) NOT NULL,
                platform VARCHAR(50) NOT NULL,
                property_type VARCHAR(50),
                rooms INTEGER,
                area_min INTEGER,
                area_max INTEGER,
                price_max NUMERIC(10,2),
                price_currency VARCHAR(10) DEFAULT 'EUR',
                zone VARCHAR(200),
                city VARCHAR(100) DEFAULT 'București',
                floor_min INTEGER,
                floor_max INTEGER,
                furnished BOOLEAN,
                query TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                notify_email BOOLEAN DEFAULT FALSE,
                notify_discord BOOLEAN DEFAULT FALSE,
                active_hours_start INTEGER,
                active_hours_end INTEGER,
                polling_interval_minutes INTEGER DEFAULT 30,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        _migrate(conn, "create_real_estate_listings", """
            CREATE TABLE IF NOT EXISTS real_estate_listings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                keyword_id INTEGER REFERENCES real_estate_keywords(id) ON DELETE SET NULL,
                platform VARCHAR(50) NOT NULL,
                external_id VARCHAR(200),
                source VARCHAR(20) DEFAULT 'platform',
                title TEXT,
                price NUMERIC(10,2),
                currency VARCHAR(10) DEFAULT 'EUR',
                price_per_sqm NUMERIC(8,2),
                property_type VARCHAR(50),
                rooms INTEGER,
                area_sqm INTEGER,
                floor VARCHAR(30),
                zone_raw VARCHAR(200),
                zone_normalized VARCHAR(200),
                city VARCHAR(100),
                furnished BOOLEAN,
                image_url TEXT,
                images_json JSON DEFAULT '[]',
                url TEXT,
                description TEXT,
                score INTEGER DEFAULT 50,
                grade VARCHAR(5) DEFAULT 'C',
                price_history JSON DEFAULT '[]',
                phash VARCHAR(64),
                color_hist JSON,
                duplicate_group_id VARCHAR(100),
                duplicate_level INTEGER,
                user_flagged_duplicate_id INTEGER,
                status VARCHAR(20) DEFAULT 'active',
                found_at TIMESTAMP DEFAULT NOW(),
                last_checked_at TIMESTAMP,
                last_price_change_at TIMESTAMP
            )
        """)
        _migrate(conn, "idx_re_listings_user_platform",
            "CREATE INDEX IF NOT EXISTS idx_re_listings_user_platform "
            "ON real_estate_listings(user_id, platform, status)")
        _migrate(conn, "idx_re_listings_external",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_re_listings_external "
            "ON real_estate_listings(user_id, platform, external_id) "
            "WHERE external_id IS NOT NULL")

        # ID-ul anuntului cu care a fost detectat duplicat (auto-populare buton UI).
        # Tabela reala e `real_estate_listings` (nu `real_estate_monitor_listings`).
        _migrate(conn, "add_re_duplicate_match_id",
            "ALTER TABLE real_estate_listings ADD COLUMN IF NOT EXISTS duplicate_match_id INTEGER")

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
