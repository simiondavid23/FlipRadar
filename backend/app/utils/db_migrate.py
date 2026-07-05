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
            # Vinted: flag ca detaliul complet (poze/descriere/data) a fost adus
            # on-demand o singura data (evita re-fetch si hammering pe 403).
            if not _column_exists(inspector, "radar_listings", "vinted_detail_fetched"):
                _migrate(conn, "add_radar_listings_vinted_detail_fetched",
                         "ALTER TABLE radar_listings ADD COLUMN IF NOT EXISTS "
                         "vinted_detail_fetched BOOLEAN NOT NULL DEFAULT FALSE")
            # Facebook: la fel ca Vinted — flag ca detaliul (descriere/galerie) a fost
            # adus on-demand o singura data (evita re-fetch la fiecare deschidere a panoului).
            if not _column_exists(inspector, "radar_listings", "facebook_detail_fetched"):
                _migrate(conn, "add_radar_listings_facebook_detail_fetched",
                         "ALTER TABLE radar_listings ADD COLUMN IF NOT EXISTS "
                         "facebook_detail_fetched BOOLEAN NOT NULL DEFAULT FALSE")

        # Radar keywords: car_filters (JSON serializat) + extensii pentru scrapere auto
        if _table_exists(inspector, "radar_keywords"):
            if not _column_exists(inspector, "radar_keywords", "car_filters"):
                _migrate(conn, "add_radar_keywords_car_filters",
                         "ALTER TABLE radar_keywords ADD COLUMN car_filters TEXT")
            # FlipRadar — config wizard marketplace (platform/categorie/subcategorie/filtre) JSON
            if not _column_exists(inspector, "radar_keywords", "marketplace_config"):
                _migrate(conn, "add_radar_keywords_marketplace_config",
                         "ALTER TABLE radar_keywords ADD COLUMN IF NOT EXISTS marketplace_config TEXT")

            # FlipRadar — remapare catalog_id-uri Vinted pe keyword-urile old-form.
            # Dropdown-ul vechi (PLATFORM_CATEGORIES["vinted"]) stoca ID-uri gresite fata de
            # arborele real Vinted (ex. "Telefoane"=2995 = de fapt "Alte dispozitive si accesorii"),
            # deci filtrarea server-side (catalog_ids) nimerea categoria gresita. Aliniem valorile
            # deja salvate cu dropdown-ul corectat din categories.py, ca get_category_label sa
            # continue sa reflecte selectia userului iar scraper-ul sa filtreze corect.
            # NB: unele ID-uri noi coincid cu alte ID-uri vechi (ex. 196->257, 257->79), deci
            # folosim UN singur UPDATE cu CASE (evaluat o data pe valoarea originala a randului)
            # in loc de UPDATE-uri secventiale per-valoare care s-ar inlantui si ar dubla migrarea.
            _vinted_id_remap = {
                "4": "12", "3": "10", "6": "9", "270": "183", "79": "11", "8": "1037",
                "256": "13", "87": "4", "17": "29", "15": "28", "68": "4",
                "195": "76", "198": "2050", "201": "34", "196": "257", "257": "79",
                "255": "2050", "197": "1206", "200": "32", "199": "80",
                "2": "1193", "151": "1193", "152": "1193", "153": "1193", "154": "1193",
                "203": "1231", "155": "1193",
                "1206": "1187", "1232": "19", "1234": "160", "1235": "21", "1236": "22",
                "1237": "26", "1238": "88", "1239": "89",
                "76": "4332", "62": "4332", "61": "4332", "63": "4334", "64": "4335",
                "1919": "1934", "1920": "1924", "1921": "1920", "1922": "1919",
                "1203": "146", "1204": "964", "1240": "152", "1241": "956", "1242": "1902",
                "2995": "3661", "2996": "3567", "2997": "3566", "3025": "3002", "2998": "3580",
                "3263": "2309", "3264": "2312", "3265": "3036", "3266": "3037",
            }
            _when = " ".join(f"WHEN '{o}' THEN '{n}'" for o, n in _vinted_id_remap.items())
            _in = ", ".join(f"'{o}'" for o in _vinted_id_remap)
            _migrate(conn, "remap_vinted_category_ids_to_live_tree",
                     f"UPDATE radar_keywords SET category = CASE category {_when} ELSE category END "
                     f"WHERE category IN ({_in}) AND (platform = 'vinted' OR platform IS NULL)")

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
            # Vinted: mecanismul de cookie a fost eliminat (folosim libraria vinted-scraper,
            # care gestioneaza DataDome automat). Renuntam la coloana ca sa nu ramana date moarte.
            _migrate(conn, "drop_radar_settings_vinted_cookie",
                     "ALTER TABLE radar_settings DROP COLUMN IF EXISTS vinted_cookie")
            # MODIFICARE 9 — batch size configurabil pentru jobul ML de detectie vanzari.
            _migrate(conn, "add_sold_detection_batch_size",
                     "ALTER TABLE radar_settings ADD COLUMN IF NOT EXISTS "
                     "sold_detection_batch_size INTEGER DEFAULT 100")

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

        # Auto keywords: categorie per-platforma + filtre tehnice confirmate (JSON).
        # Populate de formularul dinamic de keyword; scanerul le trece la scrapere.
        if _table_exists(inspector, "auto_keywords"):
            if not _column_exists(inspector, "auto_keywords", "category"):
                _migrate(conn, "add_auto_keywords_category",
                         "ALTER TABLE auto_keywords ADD COLUMN category VARCHAR(100)")
            if not _column_exists(inspector, "auto_keywords", "tech_filters"):
                _migrate(conn, "add_auto_keywords_tech_filters",
                         "ALTER TABLE auto_keywords ADD COLUMN tech_filters JSON")

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

        # Auto feed: imbogatire on-demand a detaliului (vanzator/data/flag) — pattern Radar.
        if _table_exists(inspector, "auto_feed_listings"):
            if not _column_exists(inspector, "auto_feed_listings", "seller_name"):
                _migrate(conn, "add_auto_feed_seller_name",
                         "ALTER TABLE auto_feed_listings ADD COLUMN seller_name VARCHAR(200)")
            if not _column_exists(inspector, "auto_feed_listings", "listed_at"):
                _migrate(conn, "add_auto_feed_listed_at",
                         "ALTER TABLE auto_feed_listings ADD COLUMN listed_at TIMESTAMP")
            if not _column_exists(inspector, "auto_feed_listings", "detail_fetched"):
                _migrate(conn, "add_auto_feed_detail_fetched",
                         "ALTER TABLE auto_feed_listings ADD COLUMN detail_fetched BOOLEAN DEFAULT FALSE")

        # ── Loturi Auto: keyword-uri monitorizate + coloane noi pe auto_lot ──
        _migrate(conn, "create_auto_lot_keywords", """
            CREATE TABLE IF NOT EXISTS auto_lot_keywords (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(200) NOT NULL,
                platform VARCHAR(50) NOT NULL,
                make VARCHAR(100),
                model VARCHAR(100),
                year_from INTEGER,
                year_to INTEGER,
                damage_primary VARCHAR(100),
                bid_max NUMERIC(10,2),
                location_state VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                notify_email BOOLEAN DEFAULT FALSE,
                notify_discord BOOLEAN DEFAULT FALSE,
                active_hours_start INTEGER,
                active_hours_end INTEGER,
                polling_interval_minutes INTEGER DEFAULT 15,
                last_scan_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # auto_lot: coloane noi pentru feed monitorizat. Tabela e creata de create_all
        # din modelul AutoLot; pe DB-uri existente coloanele lipsesc, deci le adaugam aici.
        if _table_exists(inspector, "auto_lot"):
            if not _column_exists(inspector, "auto_lot", "keyword_id"):
                _migrate(conn, "add_auto_lot_keyword_id",
                         "ALTER TABLE auto_lot ADD COLUMN keyword_id INTEGER "
                         "REFERENCES auto_lot_keywords(id) ON DELETE SET NULL")
            if not _column_exists(inspector, "auto_lot", "status"):
                _migrate(conn, "add_auto_lot_status",
                         "ALTER TABLE auto_lot ADD COLUMN status VARCHAR(20) DEFAULT 'active'")
            if not _column_exists(inspector, "auto_lot", "last_seen_at"):
                _migrate(conn, "add_auto_lot_last_seen_at",
                         "ALTER TABLE auto_lot ADD COLUMN last_seen_at TIMESTAMP")
        _migrate(conn, "idx_auto_lot_user_platform_status",
            "CREATE INDEX IF NOT EXISTS idx_auto_lot_user_platform_status "
            "ON auto_lot(user_id, platform, status)")

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

        # MODIFICARE 7 — coada Discord persistenta (pending/sent/failed).
        if not _table_exists(inspector, "discord_queue"):
            _migrate(conn, "create_discord_queue", """
                CREATE TABLE discord_queue (
                    id SERIAL PRIMARY KEY,
                    webhook_url TEXT NOT NULL,
                    embed TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    module TEXT NOT NULL,
                    grade TEXT,
                    mention_here BOOLEAN DEFAULT FALSE,
                    image_url TEXT,
                    status TEXT DEFAULT 'pending',
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    sent_at TIMESTAMPTZ,
                    error_msg TEXT
                )
            """)
            _migrate(conn, "idx_discord_queue_status",
                "CREATE INDEX IF NOT EXISTS ix_discord_queue_status "
                "ON discord_queue(status, created_at)")

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
                tip_anunt VARCHAR(50) DEFAULT 'vanzare',
                rooms INTEGER,
                area_min INTEGER,
                area_max INTEGER,
                price_min NUMERIC(10,2),
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
        # Coloane adaugate ulterior (DB-uri existente): tip_anunt (vanzare/inchiriere) +
        # price_min. Lipseau complet — keyword-ul nu putea distinge vanzare de inchiriere.
        if _table_exists(inspector, "real_estate_keywords"):
            if not _column_exists(inspector, "real_estate_keywords", "tip_anunt"):
                _migrate(conn, "add_re_kw_tip_anunt",
                    "ALTER TABLE real_estate_keywords ADD COLUMN tip_anunt VARCHAR(50) DEFAULT 'vanzare'")
            if not _column_exists(inspector, "real_estate_keywords", "price_min"):
                _migrate(conn, "add_re_kw_price_min",
                    "ALTER TABLE real_estate_keywords ADD COLUMN price_min NUMERIC(10,2)")
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

        # MODIFICARE 10 — seller_id pentru deduplicare Level 1b (seller + price).
        _migrate(conn, "add_re_seller_id",
            "ALTER TABLE real_estate_listings ADD COLUMN IF NOT EXISTS seller_id VARCHAR(200)")

        # MODIFICARE 19 — flag calitate date ML pe market_listings.
        if _table_exists(inspector, "market_listings") and not _column_exists(inspector, "market_listings", "features_complete"):
            _migrate(conn, "add_market_listings_features_complete",
                     "ALTER TABLE market_listings ADD COLUMN IF NOT EXISTS "
                     "features_complete BOOLEAN DEFAULT FALSE")

        # Catalog — sugestii de surse cross-shop (potrivire pe nume, neconfirmate).
        if not _table_exists(inspector, "product_source_suggestions"):
            _migrate(conn, "create_product_source_suggestions", """
                CREATE TABLE product_source_suggestions (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    source TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    name TEXT,
                    price DOUBLE PRECISION,
                    currency TEXT NOT NULL DEFAULT 'EUR',
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uq_product_suggestion_source UNIQUE (product_id, source)
                )
            """)
            _migrate(conn, "idx_product_suggestions_product",
                "CREATE INDEX IF NOT EXISTS ix_product_source_suggestions_product_id "
                "ON product_source_suggestions(product_id)")

        # MODIFICARE 12 — tabel pentru persistarea optionala a log-urilor (TTL 24h).
        if not _table_exists(inspector, "log_entries"):
            _migrate(conn, "create_log_entries", """
                CREATE TABLE log_entries (
                    id SERIAL PRIMARY KEY,
                    module TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            _migrate(conn, "ix_log_entries_module_created",
                "CREATE INDEX IF NOT EXISTS ix_log_entries_module_created "
                "ON log_entries (module, created_at)")

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
