# TI-1b — Diagnostic flake auth în suita pytest (RAPORT)

Baseline: `291515e`, git tree curat la start. Diagnostic pur (niciun fișier app/test modificat).
Artefacte de rulare: `subset_run{1,2,3}.txt`, `isolated_{exclusion,apismoke}.txt`,
`full_run.txt`, `full_run_{2..6}.txt`, `concurrent_{A,B}.txt` (acest director; necommis).

---

## VERDICT (pe scurt)

**H3 CONFIRMAT — lipsa izolării bazei de test per-proces.** Toate procesele pytest folosesc
ACEEAȘI bază `flipradar_test`; fixture-ul autouse `clean_db` face `TRUNCATE {toate tabelele}
RESTART IDENTITY CASCADE` înainte de fiecare test. Când ≥2 procese de test rulează concurent
pe aceeași bază, `clean_db` al unui proces șterge rândurile în curs ale celuilalt →
`db.refresh(new_user)` nu mai găsește userul (`Could not refresh instance '<User>'`), iar
token-ul de sesiune indică un user truncat (`401 Token invalid sau expirat`).

- **H1 (conexiuni „otrăvite" din pool): INFIRMAT.** `reset_on_return='rollback'` e activ
  (conexiuni idle stau după `ROLLBACK`); nicio conexiune `idle in transaction` orfană; 11/11
  rulări secvențiale curate. Pool-ul nu e cauza.
- **H2 (thread-uri daemon): NU e cauza directă a acestor simptome.** Workerul Discord atinge
  DOAR `discord_queue`/`discord_notifications_sent`, niciodată `users` — nu poate șterge rândul
  care dispare. Niciun test nu declanșează endpoint-urile thread-spawning (vezi 6b). Rămâne un
  actor DB inutil în teste (risc latent), dar nu produce simptomul.

**Dovadă cheie:** 11 rulări secvențiale = 0 eșecuri; 2 rulări CONCURENTE pe aceeași bază =
26× `Could not refresh` + 33× `Token invalid` + zeci de teste picate.

---

## PUNCTUL 6 (static + empiric)

### 6a — Când pornește workerul din `discord_service.py`?
**La IMPORT, nu lazy.** `discord_service.py:153` `discord_service = DiscordNotificationService()`
(singleton la nivel de modul); `__init__` (liniile 30-33) creează și `.start()` thread-ul daemon
`discord-queue-worker`. Lanțul de import la nivel de modul:
`main.py:63  from app.utils.radar_scanner import run_radar_scan`
`  → radar_scanner.py:32  from app.services.discord_service import send_radar_notification`
`    → discord_service.py:153  DiscordNotificationService()  → thread.start()`
`conftest.py:94` face `import app.main` în fixture-ul `_schema` (session, autouse), deci
**workerul pornește la setup-ul sesiunii de test și rulează toată sesiunea**, făcând poll pe
baza de test la fiecare 2s (`_process_batch → SessionLocal() → SELECT discord_queue → close`).
`run_auto_scan`/`run_real_estate_scan` sunt importate în interiorul `lifespan` (main.py:132,182),
deci NU pornesc la import (lifespan e off în teste).

Confirmare empirică (inline, fără fișiere): după `import app.main`,
`threading.enumerate()` → `['MainThread', 'discord-queue-worker']`.

### 6b — Endpoint thread-spawning → teste care le ating
| Endpoint (rută HTTP) | Sursă | Teste care îl ating |
|---|---|---|
| `POST /api/radar/scan-now` | radar.py:1397 | **niciunul** |
| `POST /api/radar/facebook/connect` | radar.py:1293 | **niciunul** |
| `POST /api/radar/search-manual` (ThreadPoolExecutor) | radar.py:1020/1081 | **niciunul** |
| `POST /api/auto-listings/scan-now` | auto_listings_keywords.py:522 | **niciunul** |
| `POST /api/auto-lots/scan-now` | auto_lot_keywords.py:232 | **niciunul** |
| `POST /api/real-estate-monitor/scan-now` | real_estate_keywords.py:551 | **niciunul** |
| worker Discord (import-time) | discord_service.py:31/153 | rulează în TOATE (via `import app.main`) |

`grep` în `backend/tests/` pentru `scan-now|facebook/connect|search-manual|run_*_scan|_scan_user`
→ 0 potriviri. Singura potrivire înrudită: `test_radar_watchdog.py` care face **mock** pe
`_dispatch_alert` și nu apelează niciun endpoint. → **Niciun thread pornit de endpoint nu e
exercitat de suită.** Singurul thread de fundal viu e workerul Discord (import-time).

---

## PUNCTUL 4 — reproducere subset (test → r1/r2/r3/izolat)
| Fișier | run1 | run2 | run3 | izolat |
|---|---|---|---|---|
| `test_radar_exclusion_api.py` (3) | ✅ 7/7* | ✅ | ✅ | ✅ 3/3 |
| `test_api_smoke.py` (4) | ✅ (subset) | ✅ | ✅ | ✅ 4/4 |
\* subset = ambele fișiere împreună, 7 teste, ~15s; toate 3 rulările + izolate = CURATE.

## PUNCTUL 5 — suita completă
- `full_run.txt`: **202 passed** in 193.16s.
- `full_run_{2..6}.txt` (5 rulări back-to-back): **fiecare 202 passed**, 0 failed/error.
- Total secvențial: **11 rulări, 0 eșecuri.** Flake-ul NU se reproduce secvențial (nici back-to-back).

## Reproducere DECISIVĂ — 2 suite CONCURENTE pe aceeași bază
`pytest -p no:warnings` × 2 în paralel pe `flipradar_test`:
- `concurrent_A.txt`: **2 failed + 7 errors**; 14× `Could not refresh instance '<User>'`.
- `concurrent_B.txt`: **33 failed + 6 errors**; 12× `Could not refresh` + 33× `Token invalid sau expirat`.
- Teste picate „rătăcitoare" în multe fișiere (auto_bulk_action, export_by_ids, imobiliare_*,
  mobile_de_*, radar_exclusion_api, api_smoke) — exact semnătura raportată.

Traceback reprezentativ (`concurrent_A`): `auth.py register → db.refresh(new_user) →
load_on_ident(...) is None → InvalidRequestError: Could not refresh instance '<User>'`.
`Token invalid` (`concurrent_B`): `auth_client.get("/api/auth/me") → 401`.

---

## Mecanism (dovedit)
Fără izolare per-proces, `clean_db` (conftest.py:103-116) rulează
`TRUNCATE {toate tabelele din Base.metadata} RESTART IDENTITY CASCADE` înainte de fiecare test,
pe baza PARTAJATĂ (conftest.py:49 `os.environ["DATABASE_URL"] = TEST_DATABASE_URL`, nume fix).
Cu 2 procese concurente:
1. Proc B: `register` → `db.add(user); db.commit()` (user id=1 în `users`).
2. Proc A: `clean_db` al testului următor → `TRUNCATE users ...` → șterge userul lui B.
3. Proc B: `db.refresh(user)` → SELECT pe PK → 0 rânduri → **`Could not refresh instance User`**.
   (sau, la endpoint autentificat: token-ul indică user id=1 truncat → **401 Token invalid**.)
Nedeterminist (timing între procese) → eșecuri rătăcitoare; izolat/secvențial trece.

Concurența poate apărea ușor: două terminale, IDE test-runner + CLI, o suită în background +
o rulare ad-hoc, sau conexiuni de worker rămase de la un proces care tocmai a ieșit (thread daemon
ucis fără checkin — „ocolește" reset_on_return-ul din H1). Nota din memorie „flakes under
back-to-back heavy runs; re-run cleanly" e consistentă cu asta.

---

## Recomandare de fix REVIZUITĂ (implementarea se decide separat)

**Primar (cauza rădăcină H3) — izolare per-proces a bazei de test:**
- **Opțiune A (robustă):** nume de bază unic per proces/worker (ex. sufix PID sau
  `PYTEST_XDIST_WORKER`), creat/șters per worker → rulările concurente devin sigure. Efort: mediu.
- **Opțiune B (ieftină, anti-footgun):** lock de sesiune la start (fail-fast dacă altă sesiune de
  test e activă pe aceeași bază) + documentare „nu rula suite concurent pe aceeași bază". Efort: mic.
- **Opțiune C (cea mai curată izolare):** izolare tranzacțională per-test — `dependency_overrides[get_db]`
  cu sesiune legată de o conexiune + `begin_nested()` rollback la teardown, în loc de `TRUNCATE`
  pe tabele partajate. Efort: mediu-mare (necesită pattern SAVEPOINT-restart fiindcă `register` face commit).

**Secundar (risc latent H2, defense-in-depth) — gating thread-uri de fundal în teste:**
Workerul Discord pornește la `import app.main` și rulează toată sesiunea inutil. Gating: verifică
un flag de mediu (ex. `TESTING`) în `discord_service.py` înainte de `thread.start()`, SAU mută
pornirea singletonului în `lifespan` (deja off în teste). Elimină un actor DB inutil din teste.

**NU e suficient:** `NullPool`/`engine.dispose()` (sugestia mea din TI-1) — **INSUFICIENT**,
fiindcă rădăcina e `TRUNCATE` cross-proces pe bază partajată, nu configurarea pool-ului.
