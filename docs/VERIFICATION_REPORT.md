# FlipRadar — Raport verificare implementări

**Data:** 2026-06-28
**Verificări efectuate:** 22
**Metodă:** citire fișiere reale de pe disc + teste rulate cu `backend/venv` (Python 3.14)
împotriva PostgreSQL real + `next build` + boot integrat al aplicației.

## Rezultate

| # | Verificare | Status | Problemă găsită | Remediat |
|---|-----------|--------|-----------------|---------|
| 1 | CORS withCredentials | ✅ | — (`allow_origins` listă explicită, nu `*`; `allow_credentials=True`) | N/A |
| 2 | SSE EventSource withCredentials | ✅ | — (unica instanță are `{ withCredentials: true }`) | N/A |
| 3 | Refresh interceptor Axios | ✅ | Cererile concurente eșuau în timpul refresh-ului (latent) | ✅ (hardening — vezi Modificări suplimentare) |
| 4 | localStorage eliminat complet | ✅ | — (rămân doar `localStorage` pentru temă, nu token) | N/A |
| 5 | /api/auth/refresh securizat | ✅ | — (cookie + verificare `type`, doar access reînnoit, fără `get_current_user`) | N/A |
| 6 | Discord worker thread stabil | ✅ | — (`daemon=True`, instanță unică/proces, `db.close()` în `finally`, `cleanup_stale` o singură dată) | N/A |
| 7 | Migrări DB idempotente | ✅ | — (toate `IF NOT EXISTS` + guard `_table/_column_exists` + tracking) | N/A |
| 8 | Rate limiting doar pe scraping | ✅ | — (13 endpoint-uri scraping/scan; niciun feed/stats/dashboard) | N/A |
| 9 | Crypto backward compat | ✅ | — (`InvalidToken` prins explicit; plain text returnat neatins; gol → gol) | N/A |
| 10 | decrypt_cookie aplicat consistent | ✅ | — (toate cele 8 locuri de citire-pentru-folosire decriptează) | N/A |
| 11 | Health check returnează 200 | ✅ | — (niciun `raise`; doar `return result`) | N/A |
| 12 | Delay-uri fixe eliminate | ✅ | — (doar `_get_platform_delay`/`random.uniform`; fără sleep fix inter-pagini) | N/A |
| 13 | compute_score None-safe | ✅ | — (toate combinațiile None → tuple, fără excepție) | N/A |
| 14 | batch_size citit din DB | ✅ | — (`run_sold_detection` citește `radar_settings.sold_detection_batch_size`) | N/A |
| 15 | Duplicate L1 nu rupe L2/L3/L4 | ✅ | — (L1a `url` + L1b seller/price; L2 pHash, L3 text, L4 fallback intacte) | N/A |
| 16 | Facebook auth lock thread-safe | ✅ | — (fără fișier → False; fără credențiale → False; lock funcțional) | N/A |
| 17 | Deque SSE independent de DB | ✅ | — (`.append()` înainte de `_persist_to_db`; persist în try/except) | N/A |
| 18 | Session status backward compat | ✅ | — (cookie plain text decriptat ca atare; `access_token_web` detectat) | N/A |
| 19 | features_complete chei corecte | ✅ | — (BMW `year`/`km`, Apple `product_line`/`storage_gb` — confirmate cu colectorii) | N/A |
| 20 | next build fără erori | ✅ | — (`Compiled successfully`, 59/59 pagini, fără `exhaustive-deps`) | N/A |
| 21 | /api/health montat primul | ✅ | — (primul `include_router`; fără middleware global de auth) | N/A |
| 22 | Rate limiter instanță unică | ✅ | — (`Limiter(` definit doar în `app/rate_limit.py`, importat peste tot) | N/A |

**Rezultat: 22/22 verificări trecute.** Nu au fost găsite bug-uri de integrare care să rupă
funcționalitatea. A fost aplicat un singur hardening de robustețe (V3, detaliat mai jos).

---

## Probleme găsite și remedieri aplicate

### V3 — Interceptor refresh: cereri concurente în timpul refresh-ului
**Tip:** robustețe / integrare (nu rupea testele V3, dar era o slăbiciune reală).

Implementarea inițială (conform spec M3) respingea imediat orice cerere care primea 401
cât timp un refresh era deja în curs (`if (isRefreshing) return Promise.reject(error)`).
Pe pagini care fac request-uri în paralel (Dashboard rulează acum `getStats` +
`getSchedulerStatus` + altele simultan — vezi M15), dacă access_token-ul expiră fix la
încărcare, **toate cererile în afară de prima ar eșua** chiar dacă refresh-ul reușea →
panouri cu erori tranzitorii (deși fără logout forțat).

**Remediere (`frontend/src/lib/api.js`):** cererile concurente care primesc 401 în timpul
unui refresh în curs sunt puse într-o coadă (`refreshWaiters`) și reluate automat după ce
refresh-ul reușește (sau respinse dacă eșuează). Cele 4 criterii V3 rămân îndeplinite:
- `/auth/` exclus (fără buclă infinită) ✅
- `original._retry = true` setat ÎNAINTE de apelul de refresh ✅
- `isRefreshing` resetat în ambele ramuri (succes + eroare) ✅
- redirect la `/login` la eșec (reload-ul curăță starea React) ✅

Confirmat prin `next build` (compilare reușită) și fără regresii (M3 backend 18/18).

---

## Modificări suplimentare (schimbări de comportament funcțional)

1. **V3 — coadă de așteptare pentru refresh concurent** (descris mai sus). Schimbă
   comportamentul: în loc ca cererile paralele să eșueze în timpul unui refresh, ele sunt
   reluate transparent. Decizie: îmbunătățire de robustețe pentru fluxul de autentificare,
   relevantă direct pentru Dashboard-ul care face acum mai multe request-uri în paralel.

Nicio altă modificare de comportament funcțional nu a fost necesară — restul verificărilor
au confirmat implementări corecte.

---

## Observații (risc scăzut, fără remediere — în afara scopului)

- **Discord queue, deployment multi-worker:** worker-ul folosește `SELECT ... LIMIT 5` fără
  `FOR UPDATE SKIP LOCKED`. În deployment cu un singur proces (modelul real — există un
  `BackgroundScheduler` care nu suportă oricum multi-worker fără duplicare de scanuri) nu e
  o problemă: un singur thread worker procesează coada. Dacă vreodată se trece la
  `uvicorn --workers N`, ar trebui adăugat row-locking pentru a evita trimiteri duble.
  Dedup-ul pe `discord_notifications_sent` oferă protecție parțială. **Nemodificat** (ar fi
  o schimbare funcțională în afara scopului verificării).
- **M17 „Încarcă mai multe" + rate limit:** fiecare „load more" reface scrape-ul și
  feliază (scraperele nu suportă paginare nativă). Câteva click-uri rapide pe aceeași
  platformă pot atinge limita 5/min → 429 cu mesaj explicativ. Comportament așteptat.

---

## Verificări necesare QA manual (nu pot fi automatizate)

- [ ] Login în browser → cookie-uri `access_token` + `refresh_token` marcate **HttpOnly** în DevTools → Application → Cookies (și absente din `document.cookie`).
- [ ] Expirare access_token (ex: `max_age` temporar 5s) → interceptorul Axios reîmprospătează automat fără logout forțat; mai multe panouri Dashboard se reîncarcă corect simultan.
- [ ] SSE Logs (pagina Jurnale) continuă să primească evenimente după migrarea la cookie (EventSource cu credențiale).
- [ ] Trimitere listing grad A → mesaj Discord apare în canal (webhook real).
- [ ] Badge ⚠ Mobile.de vizibil în pagina Keywords Auto + tooltip la hover.
- [ ] Widget scheduler pe Dashboard afișează timpii „next run" corect (se actualizează la 60s).
- [ ] Pagina Settings → panoul „Status sesiuni" afișează badge-urile corect (OK/Lipsă/Expirat + preview token Vinted).
- [ ] Pagina ML Predictor → bara de calitate date afișată cu procentul corect (verde/galben/roșu).
- [ ] Pagina Imobiliare Feed → zona normalizată vizibilă în card (ex: „Floreasca ← Bd. X").
- [ ] Căutare manuală Marketplace → buton „Încarcă mai multe" apare pe tab-ul unei platforme și adaugă rezultate.
- [ ] Ștergere keyword (radar/auto/imobiliare) → modalul arată numărul corect de listing-uri afectate.

---

## Concluzie

Cele 19 modificări au trecut toate cele 22 de verificări post-QA. Implementările sunt corecte
și consistente la nivel de integrare:
- **Autentificare pe cookie httpOnly** corect configurată end-to-end (CORS cu origini explicite
  + credențiale, EventSource cu credențiale, interceptor de refresh fără bucle/logout forțat,
  `localStorage` curățat de token-uri). Hardening aplicat pentru cereri concurente.
- **Backend** robust: rate limiting izolat pe scraping, criptare cookie cu backward-compat,
  migrări idempotente, health check non-blocant (200), worker Discord stabil, scoring și
  detecție duplicate None-safe.
- **Frontend** compilează curat (`next build`, 59 rute).

Singura modificare cu impact funcțional este îmbunătățirea cozii de refresh concurent (V3),
documentată mai sus. Restul verificărilor au confirmat că implementarea inițială era corectă.
Elementele rămase necesită doar QA manual în browser (interacțiuni vizuale + servicii externe live).
