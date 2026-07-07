# FlipRadar — Changelog QA

**Data implementare:** 2026-06-28
**Implementat de:** Claude Code
**Total modificări:** 19

> Toate testele backend au fost rulate cu interpretorul din `backend/venv` (Python 3.14)
> împotriva bazei PostgreSQL reale (`flipradar`). Frontend-ul a fost validat prin
> `next build` (compilare reușită a tuturor rutelor). Acolo unde un test depinde de
> servicii externe live (scraping real, trimitere reală pe Discord, login real Facebook,
> interacțiune în browser) este marcat explicit ca **QA manual recomandat**.

---

## Tabel sumar

| # | Modificare | Fișiere principale modificate | Status teste |
|---|-----------|-------------------------------|-------------|
| 1 | Validare env vars la startup | `app/startup_checks.py` (nou), `app/main.py` | ✅ 2/2 |
| 2 | Health check /api/health | `app/routers/health.py` (nou), `app/main.py` | ✅ live boot |
| 3 | JWT → httpOnly cookies + refresh | `routers/auth.py`, `utils/auth.py`, `lib/api.js`, `lib/auth.js`, `login/page.js`, `app/page.js`, `routers/logs.py`, `logs/page.js` | ✅ 18/18 |
| 4 | Criptare cookie-uri sesiune | `services/crypto_service.py` (nou), `routers/radar.py`, `utils/radar_scanner.py`, `services/radar/okazii_scraper.py`, `services/radar/lajumate_scraper.py` | ✅ 8/8 |
| 5 | Rate limiting scraping endpoints | `app/rate_limit.py` (nou), `app/main.py`, `requirements.txt`, 6 routere | ✅ 5/5 |
| 6 | Jitter delay-uri inter-pagini | `utils/radar_scanner.py`, `services/auto_listings_scanner.py` | ✅ pass |
| 7 | Discord queue → PostgreSQL | `models/discord_queue_db.py` (nou), `services/discord_service.py`, `utils/db_migrate.py`, `app/main.py` | ✅ 9/9 |
| 8 | Auto scorer market_avg dinamic | `services/auto_scorer.py`, `services/auto_listings_scanner.py` | ✅ 11/11 |
| 9 | Sold detection batch_size conf. | `models/radar_settings.py`, `services/ml/sold_detector.py`, `routers/admin.py`, `utils/db_migrate.py` | ✅ 6/6 |
| 10 | Duplicate detection L1 revizuit | `services/real_estate/duplicate_detector.py`, `models/real_estate_monitor_listing.py`, `services/real_estate_scanner.py`, `utils/db_migrate.py` | ✅ 9/9 |
| 11 | Facebook re-autentificare auto | `services/facebook_auth.py` (nou), `services/radar/facebook_scraper.py`, `.env.example` (nou) | ✅ 7/7 logic |
| 12 | Logs SSE → DB persistent (opt.) | `models/log_entry.py` (nou), `services/log_manager.py`, `utils/db_migrate.py`, `app/main.py` | ✅ 8/8 |
| 13 | Panel status sesiuni Settings | `routers/user_settings.py`, `lib/api.js`, `settings/page.js` | ✅ backend + build |
| 14 | Badge avertisment Mobile.de | `auto-listings/keywords/page.js`, `auto/listings/search/page.js` | ✅ build |
| 15 | Widget scheduler status dashboard | `routers/dashboard.py`, `lib/api.js`, `dashboard/page.js` | ✅ backend + build |
| 16 | Zona normalizată în card imob. | `real-estate-monitor/feed/page.js` | ✅ build |
| 17 | Paginare Marketplace load more | `routers/marketplace.py`, `lib/api.js`, `marketplace/search/page.js` | ✅ backend + build |
| 18 | Confirmare ștergere cu impact | `routers/radar.py`, `routers/auto_listings_keywords.py`, `routers/real_estate_keywords.py`, `components/DeleteKeywordModal.jsx` (nou), 3× `keywords/page.js`, `lib/api.js` | ✅ backend + build |
| 19 | Indicator calitate date ML | `models/market_listing.py`, `services/ml/feed_ml_bridge.py`, `routers/ml.py`, `utils/db_migrate.py`, `ml-predictor/page.js` | ✅ 25/25 backend + build |

**Rezultat global testare automată backend: 100% PASS** (M3 18/18, M4 8/8, M5 5/5, M6 pass,
M7 9/9, M8 11/11, M9 6/6, M10 9/9, M11 7/7, M12 8/8, M13–M19 backend 25/25). Frontend: `next build` reușit.

---

## Detalii per modificare

### M1 — Validare variabile de mediu la startup
- Creat `app/startup_checks.py`; apelat ca **prima linie executabilă** în `main.py`, înainte de orice import din `app`.
- **Adaptare necesară:** `validate_env()` rulează înaintea `config.py` (care face `load_dotenv()`), deci `startup_checks` încarcă el însuși `.env`. În plus, reconfigurează `stdout/stderr` la UTF-8 — altfel diacriticele (ă/ț) și em-dash-ul din mesaje aruncau `UnicodeEncodeError` pe consola Windows cp1252 (ar fi blocat pornirea).
- **Teste:** pornire cu toate variabilele → OK + warning-uri pentru opționale; pornire cu o variabilă obligatorie lipsă → mesaj `[FATAL]` + `exit code 1`. **PASS**.

### M2 — Health check /api/health
- Creat `routers/health.py`; montat **primul** router în `main.py`. Endpoint-ul vechi trivial `/api/health` a fost eliminat (evită rută dublă).
- **Test (boot real):** `GET /api/health` fără token → 200, `status: ok`, `db: ok`, `scheduler: ok`, listă `jobs` non-vidă (radar_scan, auto_listings_scan, real_estate_scan, re_phash_job, re_daily_cleanup etc.). Ramura DB-down→`degraded`/HTTP 200 e tratată prin try/except (verificat prin inspecție). **PASS**.

### M3 — JWT → httpOnly cookies + refresh automat
- Backend: `login` setează cookie-uri `access_token` (15 min) + `refresh_token` (7 zile) httpOnly; endpoint-uri noi `/refresh` și `/logout`; `get_current_user` citește token din cookie (prioritar) apoi din header `Authorization: Bearer` (fallback). Adăugat `decode_token` în `utils/auth.py`.
- SSE logs (`/api/logs/stream`) acceptă acum token și din cookie (EventSource trimite cookie-ul cu `withCredentials: true`).
- Frontend: `withCredentials: true` pe instanța Axios, interceptor de refresh automat (o singură reîncercare), eliminat complet `localStorage("flipradar_token")` din `lib/api.js`, `lib/auth.js`, `login/page.js`, `app/page.js`, `logs/page.js`.
- **Teste (18/18):** login setează ambele cookie-uri httpOnly; acces cu cookie → 200; fără cookie → 401; Bearer fallback → 200; `/refresh` reînnoiește; un `access_token` NU poate fi folosit ca refresh (verificare `type`); logout șterge cookie-urile → 401 ulterior. **PASS**.

### M4 — Criptare cookie-uri sesiune (Fernet)
- Creat `services/crypto_service.py` (cheie derivată din `SECRET_KEY` via PBKDF2). Distinct de `utils/cookie_crypto.py` (acela criptează liste de cookies pentru grupuri Facebook cu `COOKIE_ENCRYPTION_KEY`).
- **Adaptare:** salvarea/citirea cookie-urilor de platformă se face în `routers/radar.py` (NU în `user_settings.py`), iar scraperele Okazii/LaJumate citesc cookie-ul direct din DB. `encrypt_cookie` aplicat la salvare; `decrypt_cookie` aplicat la **toate** locurile de citire (GET settings pentru UI, scan manual, endpoint-uri `*/test`, `radar_scanner`, okazii_scraper, lajumate_scraper).
- **Teste (8/8):** round-trip; backward-compat (text plain returnat neatins); cookie gol rămâne gol. **PASS**.

### M5 — Rate limiting pe endpoint-urile de scraping
- **Adaptare:** instanța `Limiter` definită într-un modul dedicat `app/rate_limit.py` (nu în `main.py`), pentru a evita importul circular — routerele sunt importate de `main.py` înainte ca `app`/`limiter` să existe.
- `@limiter.limit("5/minute")` pe 12 endpoint-uri: marketplace (olx-general, vinted, lajumate, publi24, okazii, kleinanzeigen, search-all), auto (lots/search, listings/search), real-estate/search, auto-listings/scan-now, real-estate-monitor/scan-now, radar/search-manual. Handler 429 cu mesaj în română.
- **Teste (5/5):** al 6-lea apel rapid → 429 cu mesaj românesc; endpoint GET feed (non-scraping) → fără limitare. **PASS**.

### M6 — Jitter aleator pe delay-uri inter-pagini
- `_PLATFORM_DELAYS` (fix) → `_PLATFORM_DELAY_RANGES` (tuple) în `radar_scanner.py` **și** `auto_listings_scanner.py` (`_AUTO_PLATFORM_DELAYS`). Delay-ul se recalculează la fiecare pagină.
- *Notă:* `real_estate_scanner.py` nu avea delay-uri fixe inter-pagini (nu necesită modificare). Delay-ul inter-**platforme** din radar era deja jitter-uit.
- **Teste:** delay-urile variază între apeluri; toate în intervalul per-platformă și în limita globală [0.3, 4.0]s; default necunoscut [0.5, 1.5]s. **PASS**.

### M7 — Discord queue → PostgreSQL persistent
- Creat modelul `discord_queue` + migrare; rescris `services/discord_service.py` (worker thread, polling 2s, max 5/ciclu, retry 3, dedup pe `discord_notifications_sent`, `cleanup_stale`). Embed builder-ele și `send_*_notification` păstrate; cele 3 apeluri interne `enqueue` actualizate la noua semnătură.
- `main.py`: job `discord_queue_cleanup` (cron 03:30) + `cleanup_stale(db)` în lifespan + model înregistrat pentru `create_all`.
- **Teste (9/9, cu `req.post` mock-uit, fără rețea):** enqueue → `pending` → `sent`; `sent_at` setat; marcat în `discord_notifications_sent`; dedup blochează al doilea enqueue; webhook invalid → `failed` după 3 retry; `cleanup_stale` marchează pending-uri vechi ca `failed`. Persistența la restart e inerentă (coada e în PostgreSQL). **PASS**.

### M8 — Auto scorer cu market_avg_ron dinamic
- **Adaptare:** modelul real e `AutoFeedListing` (NU `AutoMonitorListing`) și **nu** are coloane `make`/`price_ron`. `_fetch_market_avg` filtrează marca după titlu (`title ilike %make%`), an ±2, status active, și convertește fiecare preț EUR→RON (media e comparabilă cu `price_ron` din scoring). Fallback per-listing când media keyword-level (`_market_avg` existent) e None.
- **Teste (11/11):** 5 anunțuri EUR → medie RON (nu None); <3 → None; fără make/an → None imediat; an ±2 corect; `compute_score` nu crapă cu None. **PASS**.

### M9 — Sold detection batch_size configurabil
- Coloană `sold_detection_batch_size` în `radar_settings` + migrare. `run_sold_detection` citește valoarea efectivă din DB. Endpoint admin `PATCH /api/admin/config` (+ `GET`) cu validare 10–500.
- **Adaptare:** `run_sold_detection` citește `RadarSettings.first()`, deci PATCH aplică valoarea pe **toate** rândurile `radar_settings` (config global consistent indiferent de rândul returnat).
- **Teste (6/6):** PATCH 0/600 → 422; PATCH 10 → 200; `run_sold_detection` procesează exact 10; 422 nu modifică valoarea. **PASS**.

### M10 — Duplicate detection Level 1 revizuit
- **Adaptare:** coloana reală e `url` (nu `source_url`), iar modelul NU avea `seller_id`. Am adăugat coloana `seller_id` (model + migrare + populare în scanner din `raw.get("seller_id")`). Level 1a = același `url`; Level 1b = același `seller_id` + `price`.
- *Notă:* scraperele imobiliare actuale nu extrag `seller_id`, deci Level 1b se va activa automat când un scraper îl furnizează (câmpul + logica sunt pregătite). Level 1a e funcțional acum.
- **Teste (9/9):** 1a (url comun) → level 1; 1b (seller+price) → level 1; 1b NU se declanșează la preț diferit; fără url & fără seller → continuă; fără semnale / unic → `(4, None, None)`. **PASS**.

### M11 — Facebook re-autentificare automată
- Creat `services/facebook_auth.py` (per spec, cu `STORAGE_STATE_PATH`, `needs_reauth`, `re_authenticate`, lock thread-safe). În `search_facebook` adăugat hook cu guard `_retry` (o singură reîncercare, fără buclă). Creat `.env.example` cu `FACEBOOK_EMAIL`/`FACEBOOK_PASSWORD`.
- **Teste (7/7 logică):** `needs_reauth` False cu rezultate / fără fișier / sesiune proaspătă, True la sesiune >24h; `re_authenticate` fără credențiale → False fără crash; lock previne concurența; `search_facebook` are param `_retry`.
- **QA manual recomandat:** login-ul real Playwright pe Facebook (necesită credențiale + rețea) nu a fost executat.

### M12 — Logs SSE persistare opțională în DB (TTL 24h)
- Creat modelul `log_entries` + migrare. `log_manager.emit` persistă în DB doar dacă `LOG_DB_PERSISTENCE=true`; deque-ul SSE rămâne sursa principală și independentă. Job `log_entries_cleanup` (cron 03:00).
- **Teste (8/8):** OFF → DB gol (deque primește mesajul); ON → rând în DB (deque primește și el); `emit` nu crapă niciodată; cleanup șterge intrările >24h, păstrează cele proaspete. **PASS**.

### M13 — Panel status sesiuni platforme în Settings
- Endpoint `GET /api/users/settings/session-status` (prefix real `/api/users`). Frontend: panou cu badge-uri (verde OK / roșu Lipsă / galben Expirat) + preview token Vinted + vârstă sesiune Facebook. Inputurile de cookie există deja în secțiunea Radar.
- **Teste backend (în 25/25):** fără settings → vinted `missing`; cookie cu `access_token_web` → `ok` + `token_preview`; cookie fără → `expired`; pagina nu crapă fără `radar_settings`. Frontend: build OK.

### M14 — Badge avertisment Mobile.de
- Component `MobileDeWarning` (tooltip explicativ) lângă eticheta „Mobile.de" în lista de keyword-uri, în modalul de creare (când platforma selectată e Mobile.de) și în lista de platforme din pagina de căutare auto. Celelalte platforme nu primesc badge.
- *Notă:* opțiunile `<select>` nu pot conține JSX, deci în modal badge-ul apare sub select când Mobile.de e selectat. Build OK.

### M15 — Widget scheduler status pe Dashboard
- Endpoint `GET /api/dashboard/scheduler-status` cu **ID-urile reale** de joburi (ex: `auto_listings_scan`, nu `auto_scan`) + nume prietenoase. Frontend: card cu listă joburi, „next run" formatat („peste 3 min", „peste 1h 12min"), indicator verde/roșu, auto-refresh 60s.
- **Teste backend (în 25/25):** endpoint 200, formă corectă. Live boot: joburile (inclusiv `discord_queue_cleanup`, `log_entries_cleanup`) apar corect. Frontend: build OK.

### M16 — Zona normalizată în cardul imobiliar
- **Adaptare:** câmpul brut de localizare în model e `zone_raw` (nu `listing.location`). Cardul afișează `zone_normalized` + `← zone_raw` doar când diferă. Lipsă `zone_normalized` → secțiunea nu apare. Build OK.

### M17 — Paginare Marketplace „Încarcă mai multe"
- **Adaptare:** scraperele marketplace aduc tot setul (~3 pagini) într-un apel, fără param `page`. Am implementat paginare prin **feliere în endpoint** (helper `_paginate`): toate endpoint-urile (6 platforme + search-all) acceptă `page`/`per_page` și întorc `{results, page, has_more}`. Pagina de căutare e per-platformă (tab-uri), deci butonul „Încarcă mai multe" apare pe tab-ul unei platforme cu `has_more` și adaugă rezultate (nu le înlocuiește).
- **Teste:** `_paginate` (pag.1 → 20 + has_more True; pag.3 → 10 + has_more False) și acceptarea param-ilor — în 25/25 backend. Frontend: build OK.
- **QA manual recomandat:** fluxul live (query real → load more) depinde de scraping real.

### M18 — Confirmare ștergere keyword cu impact
- Endpoint `GET /keywords/{id}/impact` în toate cele 3 module (radar, auto, imobiliare). Component refolosibil `components/DeleteKeywordModal.jsx` înlocuiește `confirm()` în cele 3 pagini de keywords.
- **Adaptare:** `RadarSeenId` NU e legat de keyword (e global pe user+platformă), deci `seen_count` = 0 pentru toate modulele; `listing_count` e numărul real de listinguri asociate (impactul real al ștergerii).
- **Teste backend (în 25/25):** radar impact cu 3 listinguri → `listing_count == 3`; endpoint-urile auto + imobiliare răspund 200. Frontend: build OK.

### M19 — Indicator calitate date ML
- Coloană `features_complete` pe `market_listings` + migrare. `feed_ml_bridge._is_features_complete` (Apple: `product_line`+`storage_gb`; BMW: `year`+`km`) setat la inserare. `GET /api/ml/stats` extins cu `total`/`complete`/`completeness_pct` per categorie. Frontend: bară de calitate (verde ≥90% / galben 70–89% / roșu <70%).
- *Verificat:* cheile reale din feature dict — Apple `product_line`/`storage_gb` (apple_collector), BMW `year`/`km` (bmw_collector).
- **Teste (25/25 backend):** migrare aplicată; `_is_features_complete` (BMW year+km → True, fără year → False, Apple line+storage → True, categorie necunoscută → False); `/api/ml/stats` întoarce câmpurile de completitudine. Frontend: build OK.

---

## Variabile de mediu noi necesare

```env
# Obligatorii (deja existente — verificate acum explicit la startup)
DATABASE_URL=
SECRET_KEY=
GROQ_API_KEY=

# Facebook re-autentificare (noi)
FACEBOOK_EMAIL=
FACEBOOK_PASSWORD=

# Logs DB persistence (nou, opțional)
LOG_DB_PERSISTENCE=false
```

A fost creat și `backend/.env.example` ca șablon complet (cu placeholder-e, fără secrete).

---

## Pași manuali de deployment

1. `pip install -r requirements.txt` (s-a adăugat `slowapi==0.1.9`).
2. Repornește backend → migrările DB rulează automat și idempotent (`discord_queue`,
   `log_entries`, `market_listings.features_complete`, `radar_settings.sold_detection_batch_size`,
   `real_estate_listings.seller_id`).
3. Verifică `GET /api/health` după repornire (trebuie `status: ok`, joburi non-vide).
4. Testează autentificarea cu un login proaspăt (cookie-uri httpOnly în DevTools → Application → Cookies).
5. Cookie-urile Vinted/Okazii/LaJumate salvate anterior (text plain) sunt citite corect prin
   backward-compatibility; la prima re-salvare din UI vor fi criptate Fernet.
6. *(Opțional)* pentru re-auth Facebook automat, setează `FACEBOOK_EMAIL`/`FACEBOOK_PASSWORD`.

---

## Note de adaptare la structura reală (rezumat)

Structura reală a diferit de cea descrisă în prompt; deciziile de adaptare:
- **M1:** `startup_checks` încarcă singur `.env` (rulează înaintea `config.py`) + reconfigurează UTF-8 (altfel crash pe consolă Windows).
- **M4:** cookie-urile se salvează/citesc în `radar.py` + scrapere (nu `user_settings.py`).
- **M5:** `Limiter` într-un modul dedicat (evită import circular).
- **M7/M15:** ID-uri reale de joburi (`auto_listings_scan` etc.).
- **M8:** model real `AutoFeedListing`, filtru pe titlu + conversie EUR→RON (fără coloane `make`/`price_ron`).
- **M9:** config global aplicat pe toate rândurile `radar_settings`.
- **M10:** câmp `url` (nu `source_url`); adăugat `seller_id` (model+migrare+scanner).
- **M16:** `zone_raw` ca echivalent al `location`.
- **M17:** paginare prin feliere în endpoint (scraperele nu suportă `page` nativ).
- **M18:** `seen_count = 0` (RadarSeenId nu e per-keyword).

---

## Regresii detectate

Nu au fost detectate regresii la testarea automată (toate cele ~106 verificări backend trec) și
nici la `next build` (compilare reușită a tuturor rutelor) sau la pornirea integrată a aplicației
(`Application startup complete`, fără excepții, fără migrări eșuate).

### Verificări care necesită QA manual (depind de servicii externe live, neexecutate automat)
- **M11:** login real Playwright pe Facebook (necesită credențiale + rețea + posibil checkpoint).
- **M7:** trimitere reală pe un webhook Discord valid (testat cu mock; logica de coadă/retry/dedup verificată).
- **M17:** flux complet „Încarcă mai multe" cu scraping real (logica de paginare verificată unitar).
- **Comportament vizual frontend** (badge-uri, modaluri, formatarea timpilor scheduler, barele de
  calitate ML): validat prin compilare; o trecere rapidă în browser pe paginile Settings, Dashboard,
  ML Predictor, Imobiliare Feed și cele 3 pagini de Keywords este recomandată ca QA final.

---

*Prompt generat pentru FlipRadar QA — toate deciziile de implementare au fost confirmate anterior.*
