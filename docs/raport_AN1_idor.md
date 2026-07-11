> NU SE COMITE / NU SE PUSHUIEȘTE — repo public; conține slăbiciuni nefixate.

# AN-1 — Sweep IDOR exhaustiv (Etapa 2 · P2)

**Repo:** FlipRadar · **HEAD:** `ccbf10a` · **Data:** 8 iulie 2026 · **Analiză:** statică (citire cod), read-only.
**Tipar auth corect:** `current_user: User = Depends(get_current_user)` (sau `require_feature(...)` / `require_admin` care îl împachetează; sau, la SSE, verificare JWT din query/cookie). **Ownership corect:** `Model.user_id == current_user.id` pe fiecare read/update/delete + `user_id=current_user.id` pe create.

Legendă: **auth** = DA / NU · **ownership** = OK / IDOR / SUSPECT / N-A (fără model cu `user_id`).

---

## Sumar (numărătoare)

- **Total endpoint-uri (grep):** 223 · **rânduri în tabel:** 223.
- **OK / N-A (fără problemă):** 213 (95.5%).
- **Probleme:** 10 (4.5%) → **4 CRITIC** + **6 SUSPECT**. **0 IDOR clasic** (acces direct la înregistrarea altui user prin `id`) — toate CRUD-urile pe modele cu `user_id` filtrează corect.

---

## CRITICE (listă cu impact)

1. **PUT `/api/radar/settings/proxy`** (`radar.py:1312`) — orice user autentificat (fără rol de admin) **rescrie fișierul global `.env`** (PROXY_HOST/PORT/USER/PASS) și `os.environ`. Impact: poate ruta tot traficul de scraping al serverului printr-un proxy controlat de atacator (intercept/MITM) sau poate rupe scrapingul pentru TOȚI userii. Lipsă guard de rol — **auto-recunoscut în docstring** („Doar admin-ii ar trebui... pentru moment permite oricărui user logat").
2. **GET `/api/logs/stream`** (`logs.py:37`, sursă `log_manager.get_all` l.59) — orice user autentificat primește **jurnalele GLOBALE** (buffer per-modul, `LogEntry`/log_manager NU au `user_id`): vede activitatea de scan a ALTOR useri — keyword-urile lor, URL-uri de anunțuri, adrese de email din mesajele de alertă. **Divulgare cross-user.** Verdict E.1: **CRITIC-multi-user** (ar fi OK-prin-design doar dacă aplicația e single-user; dar are register + panou admin multi-user).
3. **GET `/api/auto-listings/categories`** (`auto_listings_keywords.py:69`) — **fără `Depends`** (endpoint public neinclus în lista E.2). Impact de date: **nul** (întoarce doar taxonomia statică `AUTO_PLATFORM_CATEGORIES`), dar per regula „orice alt endpoint fără auth = CRITIC" → inconsecvență de politică de clasat aici.
4. **GET `/api/real-estate-monitor/categories`** (`real_estate_keywords.py:55`) — identic cu (3): **fără auth**, întoarce doar `RE_TECHNICAL_FIELDS`/`RE_PROPERTY_TYPES` statice. Impact de date **nul**, CRITIC-prin-regulă.

## SUSPECTE (scope/agregat, nu IDOR direct)

- **GET `/api/radar/settings/proxy`** (`radar.py:1298`) — expune configul proxy GLOBAL (host/port/username) oricărui user autentificat (parola e mascată).
- **GET `/api/logs/stats`** (`logs.py:83`) — agregat din același buffer global de loguri (`log_manager.get_stats`).
- **POST `/api/logs/test-emit`** (`logs.py:91`) — orice user scrie evenimente în bufferele globale de loguri (endpoint de debug expus).
- **POST `/api/ml/retrain`** (`ml.py:63`) — orice user declanșează reantrenarea GLOBALĂ a modelelor ML (operație costisitoare, ar trebui admin-only).
- **POST `/api/ml/sold-detection`** (`ml.py:76`) — orice user declanșează un batch GLOBAL de detecție vânzări.
- **GET `/api/ai/report`** (`ai_analysis.py:94`) — numără `total_products` (l.101) și `total_price_records` (l.121) **GLOBAL** (fără `user_id`), pe când restul raportului e user-scoped → scurge totaluri la nivel de platformă.

## Note (semnalări, nu bug de ownership)

- **E.2 — enumerare useri:** `GET /api/auth/security-question` (`auth.py:132`) întoarce 404 dacă emailul nu are cont / întrebare, 200 dacă are → dezvăluie existența conturilor. `POST /api/auth/reset-password` (`auth.py:144`) validează prin hash-ul răspunsului de securitate (bcrypt) + setează parola nouă; nu leagă un token de sesiune, deci un atacator care ghicește răspunsul poate reseta parola. De rate-limitat/înăsprit (deja `@limiter 5/min`).
- `GET /api/import-export/export-watchlist` (`import_export.py:243`) citește produsul prin `product_id` din watchlist-ul PROPRIU al userului fără re-filtrare pe `Product.user_id` — mărginit de watchlist-ul user-scoped (l.233), deci fără leak practic; de curățat pentru consistență.
- `POST /api/radar/settings/test-discord` (`radar.py:1057`) trimite un mesaj către un `webhook_url` arbitrar din body (SSRF-ish, inerent funcției de „testează webhook-ul") — în afara scopului IDOR.
- `GET /api/health` (`health.py:9`) și `GET /api/dashboard/scheduler-status` (`dashboard.py:20`) expun lista de joburi a scheduler-ului global (operațional, fără date de user).

---

## Tabel complet (223 endpoint-uri, grupat pe fișier)

### `admin.py` (21) — toate `Depends(require_admin)` (guard de ROL, `admin.py:30-34`); cross-user prin design
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/admin/config | DA (admin) | N-A (rol) | admin.py:45 |
| PATCH /api/admin/config | DA (admin) | N-A (rol) | admin.py:61 |
| GET /api/admin/stats | DA (admin) | N-A (rol) | admin.py:85 |
| GET /api/admin/tickets | DA (admin) | N-A (rol) | admin.py:125 |
| GET /api/admin/tickets/{ticket_id} | DA (admin) | N-A (rol) | admin.py:154 |
| POST /api/admin/tickets/{ticket_id}/reply | DA (admin) | N-A (rol) | admin.py:197 |
| POST /api/admin/run-alert-check | DA (admin) | N-A (rol) | admin.py:218 |
| PUT /api/admin/tickets/{ticket_id}/close | DA (admin) | N-A (rol) | admin.py:228 |
| GET /api/admin/products | DA (admin) | N-A (rol) | admin.py:277 |
| GET /api/admin/products/report | DA (admin) | N-A (rol) | admin.py:299 |
| GET /api/admin/products/report/pdf | DA (admin) | N-A (rol) | admin.py:378 |
| GET /api/admin/watchlist | DA (admin) | N-A (rol) | admin.py:557 |
| GET /api/admin/alerts | DA (admin) | N-A (rol) | admin.py:586 |
| GET /api/admin/inventory | DA (admin) | N-A (rol) | admin.py:623 |
| GET /api/admin/sales | DA (admin) | N-A (rol) | admin.py:647 |
| GET /api/admin/favorites | DA (admin) | N-A (rol) | admin.py:672 |
| GET /api/admin/chat-messages | DA (admin) | N-A (rol) | admin.py:706 |
| GET /api/admin/users | DA (admin) | N-A (rol) | admin.py:755 |
| GET /api/admin/users/{user_id} | DA (admin) | N-A (rol) | admin.py:790 |
| PUT /api/admin/users/{user_id}/active | DA (admin) | N-A (rol) | admin.py:890 (+_guard_self 897) |
| PUT /api/admin/users/{user_id}/features | DA (admin) | N-A (rol) | admin.py:921 (+_guard_self 929) |

### `auth.py` (7)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| POST /api/auth/register | NU (public E.2) | N-A | auth.py:29 (@limiter 5/min) |
| POST /api/auth/login | NU (public E.2) | N-A | auth.py:77 |
| POST /api/auth/refresh | NU (public E.2) | N-A | auth.py:102 (citește cookie refresh) |
| POST /api/auth/logout | NU (public E.2) | N-A | auth.py:125 (șterge cookie-uri) |
| GET /api/auth/security-question | NU (public E.2) | N-A · **enumerare useri** | auth.py:134 (vezi Note) |
| POST /api/auth/reset-password | NU (public E.2) | N-A · vezi Note | auth.py:146 |
| GET /api/auth/me | DA | OK (self) | auth.py:166 |

### `ai_analysis.py` (3) — `require_feature("can_use_ai")` (l.17)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| POST /api/ai/analyze-product | DA (feature) | N-A (market context agregat) | ai_analysis.py:58 |
| POST /api/ai/generate-listing | DA (feature) | N-A | ai_analysis.py:78 |
| GET /api/ai/report | DA (feature) | **SUSPECT** | ai_analysis.py:101,121 (count global Product/PriceHistory) |

### `ai_chat.py` (3)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| POST /api/ai/chat | DA (feature) | OK | ai_chat.py:68-90 (filter user.id), 144/152 (create user_id) |
| GET /api/ai/chat/history | DA | OK | ai_chat.py:172 |
| DELETE /api/ai/chat/history | DA | OK | ai_chat.py:195 |

### `alerts.py` (4)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/alerts/ | DA | OK | alerts.py:28 |
| POST /api/alerts/ | DA (feature) | OK | alerts.py:45 (verif Product owner), 55 (create user_id) |
| PUT /api/alerts/{alert_id}/toggle | DA | OK | alerts.py:79 |
| DELETE /api/alerts/{alert_id} | DA | OK | alerts.py:105 |

### `auto.py` (10)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| POST /api/auto/calculate-import | DA | N-A (calc pur) | auto.py:49 |
| GET /api/auto/lots/search | DA | N-A (căutare live) | auto.py:108 (@limiter) |
| POST /api/auto/lots/save | DA | OK | auto.py:215 (dedup user_id), 228 (create) |
| GET /api/auto/lots/saved | DA | OK | auto.py:266 |
| DELETE /api/auto/lots/saved/{lot_id} | DA | OK | auto.py:281 |
| POST /api/auto/listings/extract-description | DA | N-A (AI) | auto.py:305 |
| GET /api/auto/listings/search | DA | N-A (căutare live) | auto.py:324 (@limiter) |
| POST /api/auto/listings/save | DA | OK | auto.py:416/426 (dedup), 439 (create) |
| GET /api/auto/listings/saved | DA | OK | auto.py:473 |
| DELETE /api/auto/listings/saved/{listing_id} | DA | OK | auto.py:488 |

### `auto_listings_keywords.py` (15)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/auto-listings/categories | **NU** | N-A (taxonomie statică) | **auto_listings_keywords.py:69-70 — fără Depends (CRITIC #3)** |
| GET /api/auto-listings/keywords | DA | OK | :86 |
| POST /api/auto-listings/keywords | DA | OK | :97 (create user_id) |
| PUT /api/auto-listings/keywords/{kw_id} | DA | OK | :109-111 |
| DELETE /api/auto-listings/keywords/{kw_id} | DA | OK | :129-131 |
| GET /api/auto-listings/feed | DA | OK | :153 |
| GET /api/auto-listings/feed/export | DA | OK | :194 |
| PATCH /api/auto-listings/feed/{listing_id}/status | DA | OK | :234-236 |
| GET /api/auto-listings/feed/{listing_id}/detail | DA | OK | :263-265 |
| POST /api/auto-listings/feed/{listing_id}/generate-review | DA | OK | :308-310 |
| POST /api/auto-listings/feed/{listing_id}/render-template | DA | OK | :365-367 (template) + :371-373 (listing) |
| DELETE /api/auto-listings/feed/{listing_id} | DA | OK | :406-408 |
| GET /api/auto-listings/keywords/{keyword_id}/impact | DA | OK | :423-425 |
| POST /api/auto-listings/scan-now | DA | OK (scopat) | :447 run_auto_scan(user_id=user_id) |
| GET /api/auto-listings/stats | DA | OK | :466/474/479 |

### `auto_lot_keywords.py` (8)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/auto-lots/keywords | DA | OK | auto_lot_keywords.py:80 |
| POST /api/auto-lots/keywords | DA | OK | :92 |
| PUT /api/auto-lots/keywords/{kw_id} | DA | OK | :105-107 |
| DELETE /api/auto-lots/keywords/{kw_id} | DA | OK | :123-125 |
| GET /api/auto-lots/feed | DA | OK | :146 |
| PATCH /api/auto-lots/feed/{lot_id}/status | DA | OK | :165-167 |
| GET /api/auto-lots/stats | DA | OK | :186 |
| POST /api/auto-lots/scan-now | DA | OK (scopat) | :226 run_auto_lot_scan_for_user(user_id) |

### `currency.py` (2)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/currency/rates | DA | N-A (curs BNR global) | currency.py:14 |
| GET /api/currency/convert | DA | N-A | currency.py:31 |

### `dashboard.py` (4)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/dashboard/scheduler-status | DA | N-A (scheduler global, vezi Note) | dashboard.py:21 |
| GET /api/dashboard/stats | DA | OK | dashboard.py:59/65/71/84/95/112/129/143 |
| GET /api/dashboard/sales-timeseries | DA | OK | dashboard.py:188 |
| GET /api/dashboard/top-products | DA | OK | dashboard.py:234 |

### `facebook_groups.py` (9) — helper `_get_owned_config` (l.122-129)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/facebook-groups | DA | OK | :141 |
| POST /api/facebook-groups | DA | OK | :157 |
| PUT /api/facebook-groups/{config_id} | DA | OK | :178 (_get_owned_config) |
| DELETE /api/facebook-groups/{config_id} | DA | OK | :200 + :201-203 (posts user_id) |
| POST /api/facebook-groups/{config_id}/cookies | DA | OK | :222 |
| DELETE /api/facebook-groups/{config_id}/cookies | DA | OK | :243 |
| GET /api/facebook-groups/posts/all | DA | OK | :263 |
| GET /api/facebook-groups/{config_id}/posts | DA | OK | :295 + :297-299 |
| POST /api/facebook-groups/{config_id}/test-run | DA | OK (scopat) | :342 + :345 (config_id, user.id) |

### `favorites.py` (4)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/favorites/ | DA | OK | favorites.py:23 |
| GET /api/favorites/blacklist | DA | OK | favorites.py:39 |
| POST /api/favorites/ | DA | OK | favorites.py:55 (verif Product owner), 74 (create) |
| DELETE /api/favorites/{item_id} | DA | OK | favorites.py:94 |

### `health.py` (1)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/health | NU (public E.2 — monitoring) | N-A | health.py:10 |

### `import_export.py` (5) — `require_feature("can_use_import_export")` (l.17)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| POST /api/import-export/import-csv | DA (feature) | OK | :71 (dedup user_id), 79 (create) |
| POST /api/import-export/import-excel | DA (feature) | OK | :157 (dedup), 172 (create) |
| GET /api/import-export/export-products | DA (feature) | OK | :201 |
| GET /api/import-export/export-watchlist | DA (feature) | OK (vezi Note l.243) | :233 |
| GET /api/import-export/template | DA (feature) | N-A (șablon static) | :268 |

### `inventory.py` (7)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/inventory/ | DA | OK | inventory.py:26 |
| GET /api/inventory/stats | DA | OK | inventory.py:45 |
| POST /api/inventory/ | DA | OK | inventory.py:72 (create user_id) |
| PUT /api/inventory/{item_id} | DA | OK | inventory.py:89 |
| DELETE /api/inventory/{item_id} | DA | OK | inventory.py:111 |
| GET /api/inventory/template | DA | N-A (șablon) | inventory.py:126 |
| POST /api/inventory/import-excel | DA | OK | inventory.py:234 (create user_id) |

### `logs.py` (3) — **E.1: buffer global, fără user_id**
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/logs/stream | DA (token) | **CRITIC-multi-user** | logs.py:37/59 (log_manager global — vezi CRITIC #2) |
| GET /api/logs/stats | DA | **SUSPECT** | logs.py:83/88 (get_stats global) |
| POST /api/logs/test-emit | DA | **SUSPECT** | logs.py:91 (scrie în buffere globale) |

### `marketplace.py` (14)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/marketplace/olx-general | DA | N-A (căutare live) | marketplace.py:65 (@limiter) |
| GET /api/marketplace/vinted | DA | N-A | :81 |
| GET /api/marketplace/lajumate | DA | N-A | :97 |
| GET /api/marketplace/publi24 | DA | N-A | :113 |
| GET /api/marketplace/okazii | DA | N-A | :129 |
| GET /api/marketplace/kleinanzeigen | DA | N-A | :146 |
| GET /api/marketplace/search-all | DA | N-A | :163 |
| POST /api/marketplace/saved | DA | OK | :237 (dedup), 249 (create) |
| GET /api/marketplace/saved | DA | OK | :271 |
| DELETE /api/marketplace/saved/{saved_id} | DA | OK | :286 |
| GET /api/marketplace/keyword-alerts | DA | OK | :338 |
| POST /api/marketplace/keyword-alerts | DA | OK | :356 |
| PUT /api/marketplace/keyword-alerts/{alert_id} | DA | OK | :379 |
| DELETE /api/marketplace/keyword-alerts/{alert_id} | DA | OK | :407 |

### `ml.py` (4)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/ml/stats | DA | N-A (market_listings fără user_id, date partajate) | ml.py:17 |
| POST /api/ml/predict | DA | N-A (inferență pe features) | ml.py:52 |
| POST /api/ml/retrain | DA | **SUSPECT** (op globală) | ml.py:65 |
| POST /api/ml/sold-detection | DA | **SUSPECT** (op globală) | ml.py:78 |

### `notifications.py` (5)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/notifications/ | DA | OK | notifications.py:22 |
| GET /api/notifications/unread-count | DA | OK | notifications.py:38 |
| PUT /api/notifications/{notification_id}/read | DA | OK | notifications.py:53 |
| PUT /api/notifications/read-all | DA | OK | notifications.py:69 |
| DELETE /api/notifications/clear | DA | OK | notifications.py:81 |

### `products.py` (13) — helper `_user_products_query` (l.110-111)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/products/ | DA | OK | products.py:130 |
| GET /api/products/filter-options | DA | OK | products.py:203 |
| GET /api/products/brands | DA | OK | products.py:242 |
| GET /api/products/categories-by-source | DA | N-A (taxonomie statică) | products.py:287 |
| GET /api/products/source-categories | DA | N-A (constante) | products.py:298 |
| GET /api/products/stats | DA | OK | products.py:315 |
| GET /api/products/{product_id} | DA | OK | products.py:375 |
| POST /api/products/ | DA | OK | products.py:520 (dedup), 543 (create) |
| PUT /api/products/{product_id} | DA | OK | products.py:589 |
| POST /api/products/{product_id}/refresh-price | DA | OK | products.py:634 |
| DELETE /api/products/{product_id} | DA | OK | products.py:699 |
| POST /api/products/{product_id}/suggestions/{suggestion_id}/confirm | DA | OK | products.py:721 + :732 (sug prin product_id owned) |
| DELETE /api/products/{product_id}/suggestions/{suggestion_id} | DA | OK | products.py:757 + :767 |

### `radar.py` (38)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/radar/categories | DA | N-A (listă statică) | radar.py:371 |
| GET /api/radar/keywords | DA | OK | radar.py:387 |
| POST /api/radar/keywords | DA | OK | radar.py:411 |
| PUT /api/radar/keywords/{keyword_id} | DA | OK | radar.py:453 |
| DELETE /api/radar/keywords/{keyword_id} | DA | OK | radar.py:523 + :533-535 |
| PATCH /api/radar/keywords/{keyword_id}/toggle | DA | OK | radar.py:550 |
| GET /api/radar/keywords/{keyword_id}/impact | DA | OK | radar.py:868-870 |
| GET /api/radar/keywords/{keyword_id}/price-trend | DA | OK | radar.py:1593 + :1607-1609 |
| GET /api/radar/listings | DA | OK | radar.py:584 |
| GET /api/radar/listings/export | DA | OK | radar.py:646 |
| GET /api/radar/listings/{listing_id} | DA | OK | radar.py:689 |
| GET /api/radar/listings/{listing_id}/vinted-detail | DA | OK | radar.py:709 |
| GET /api/radar/listings/{listing_id}/facebook-detail | DA | OK | radar.py:751 |
| GET /api/radar/listings/{listing_id}/ai-review | DA | OK | radar.py:789 |
| PATCH /api/radar/listings/{listing_id}/status | DA | OK | radar.py:828 |
| DELETE /api/radar/listings/{listing_id} | DA | OK | radar.py:845 |
| POST /api/radar/listings/bulk-action | DA | OK | radar.py:1551/1566 (filter user_id + id.in_) |
| POST /api/radar/search-manual | DA | N-A (căutare live) | radar.py:881 (@limiter) |
| GET /api/radar/settings | DA | OK | radar.py:993 (_get_or_create_settings) |
| PUT /api/radar/settings | DA | OK | radar.py:1003 |
| POST /api/radar/settings/test-discord | DA | N-A (webhook user, vezi Note) | radar.py:1060 |
| GET /api/radar/settings/proxy | DA | **SUSPECT** (config global) | radar.py:1299 |
| PUT /api/radar/settings/proxy | DA | **CRITIC** (scrie .env global) | radar.py:1312 (vezi CRITIC #1) |
| GET /api/radar/lajumate/test | DA | OK | radar.py:1075 |
| GET /api/radar/okazii/test | DA | OK | radar.py:1105 |
| GET /api/radar/facebook/status | DA | OK | radar.py:1140 |
| POST /api/radar/facebook/connect | DA | OK | radar.py:1151 |
| GET /api/radar/stats | DA | OK | radar.py:1182 |
| POST /api/radar/scan-now | DA | OK (scopat _scan_user) | radar.py:1258-1260 |
| GET /api/radar/templates | DA | OK | radar.py:1414 |
| POST /api/radar/templates | DA | OK | radar.py:1430 |
| PUT /api/radar/templates/{template_id} | DA | OK | radar.py:1449-1451 |
| DELETE /api/radar/templates/{template_id} | DA | OK | radar.py:1474-1476 |
| POST /api/radar/templates/{template_id}/render | DA | OK | radar.py:1496-1498 + :1502-1504 |
| GET /api/radar/push/vapid-public-key | DA | N-A (cheie publică) | radar.py:1670 |
| POST /api/radar/push/subscribe | DA | OK | radar.py:1681/1691 |
| DELETE /api/radar/push/unsubscribe | DA | OK | radar.py:1709 |
| GET /api/radar/push/status | DA | OK | radar.py:1722 |

### `real_estate.py` (4)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/real-estate/search | DA | N-A (căutare live) | real_estate.py:43 (@limiter) |
| POST /api/real-estate/listings/save | DA | OK | real_estate.py:153 (dedup), 165 (create) |
| GET /api/real-estate/listings/saved | DA | OK | real_estate.py:198 |
| DELETE /api/real-estate/listings/saved/{listing_id} | DA | OK | real_estate.py:213 |

### `real_estate_keywords.py` (12)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/real-estate-monitor/categories | **NU** | N-A (statică) | **real_estate_keywords.py:55-56 — fără Depends (CRITIC #4)** |
| GET /api/real-estate-monitor/keywords | DA | OK | :76 |
| POST /api/real-estate-monitor/keywords | DA | OK | :87 |
| PUT /api/real-estate-monitor/keywords/{kw_id} | DA | OK | :99-101 |
| DELETE /api/real-estate-monitor/keywords/{kw_id} | DA | OK | :117-119 |
| GET /api/real-estate-monitor/feed | DA | OK | :149-150 |
| GET /api/real-estate-monitor/feed/export | DA | OK | :175 |
| PATCH /api/real-estate-monitor/feed/{listing_id}/status | DA | OK | :217-219 |
| DELETE /api/real-estate-monitor/feed/{listing_id} | DA | OK | :234-236 |
| GET /api/real-estate-monitor/stats | DA | OK | :250 |
| GET /api/real-estate-monitor/keywords/{keyword_id}/impact | DA | OK | :305-307 |
| POST /api/real-estate-monitor/scan-now | DA | OK (scopat) | :329 run_real_estate_scan(user_id=user_id) |

### `reports.py` (1)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/reports/summary | DA | OK | reports.py:48 (Sale user_id), :58 (Inventory user_id) |

### `sales.py` (6)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/sales/ | DA | OK | sales.py:32 |
| GET /api/sales/stats | DA | OK | sales.py:52 |
| POST /api/sales/ | DA | OK | sales.py:98 (inventory owner), 117 (create) |
| PUT /api/sales/{sale_id} | DA | OK | sales.py:141 |
| GET /api/sales/export-pdf | DA | OK | sales.py:162 |
| DELETE /api/sales/{sale_id} | DA | OK | sales.py:269 |

### `scraping.py` (6) — `require_feature("can_use_scraping")` (l.25)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/scraping/altex | DA (feature) | N-A (căutare live) | scraping.py:47 |
| GET /api/scraping/sole | DA (feature) | N-A | scraping.py:59 |
| GET /api/scraping/farmaciatei | DA (feature) | N-A | scraping.py:71 |
| GET /api/scraping/emag | DA (feature) | N-A | scraping.py:83 |
| GET /api/scraping/pcgarage | DA (feature) | N-A | scraping.py:95 |
| GET /api/scraping/search-all | DA (feature) | N-A | scraping.py:107 |

### `support.py` (4)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/support/tickets | DA | OK | support.py:63 |
| POST /api/support/tickets | DA | OK | support.py:90 (create user_id) |
| GET /api/support/tickets/{ticket_id} | DA | OK | support.py:123 |
| POST /api/support/tickets/{ticket_id}/reply | DA | OK | support.py:158 |

### `tracked_products.py` (3)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/tracked-products/ | DA | OK | tracked_products.py:24 (fav user_id), :30 (watchlist user_id) |
| PATCH /api/tracked-products/{product_id}/monitoring | DA | OK | tracked_products.py:100-101 (WatchlistItem user_id) |
| DELETE /api/tracked-products/{product_id} | DA | OK | tracked_products.py:129/133 (fav+watchlist user_id) |

### `user_settings.py` (3)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/users/settings | DA | OK (self) | user_settings.py:21 |
| PATCH /api/users/settings | DA | OK (self) | user_settings.py:32-40 |
| GET /api/users/settings/session-status | DA | OK | user_settings.py:59 (RadarSettings user_id) |

### `watchlist.py` (4)
| endpoint | auth | ownership | dovadă |
|---|---|---|---|
| GET /api/watchlist/ | DA | OK | watchlist.py:25 |
| POST /api/watchlist/ | DA | OK | watchlist.py:49 (verif Product owner), 90 (create) |
| PUT /api/watchlist/{item_id} | DA | OK | watchlist.py:113 |
| DELETE /api/watchlist/{item_id} | DA | OK | watchlist.py:142 |

---

## C. Modele în scop

**Directe cu `user_id`** (28, toate filtrate în routerele proprii — vezi tabel): `alert, auto_feed_listing, auto_keyword, auto_listing, auto_lot, auto_lot_keyword, chat_message, facebook_group_config, facebook_group_post, favorite, inventory, marketplace_keyword_alert, marketplace_saved, notification, product, push_subscription, radar_keyword, radar_listing, radar_message_template, radar_preset, radar_seen_id, radar_settings, real_estate_listing, real_estate_monitor_keyword, real_estate_monitor_listing, sale, support_ticket, watchlist`.
- `radar_preset`, `radar_seen_id` — au `user_id` dar NU sunt expuse prin niciun endpoint (interne scanner) → fără suprafață IDOR.

**Indirecte (FK către un model cu `user_id`)** — accesul trece prin ownership-ul părintelui:
- `price_history` (`product_id`→products): OK prin `join(Product).filter(Product.user_id==...)` (dashboard :83-84) sau prin produs deja deținut (products :353). **Excepție:** `ai_analysis.py:121` numără GLOBAL (SUSPECT).
- `product_source`, `product_source_suggestion` (`product_id`→products): accesate doar prin produsul deținut (products :721/:732, :757/:767) → OK.
- `ticket_message` (`ticket_id`→support_tickets): prin ticket deținut (support :143) sau admin (rol) → OK.
- `market_listing` — **fără `user_id`**, date de antrenare ML PARTAJATE prin design → N-A.
- `log_entry` / `log_manager` — **fără `user_id`**, buffere GLOBALE → baza CRITIC #2 / E.1.

---

## Reconciliere

**rânduri în tabel = 223, găsite de grep = 223.**
</content>
