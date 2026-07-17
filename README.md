# FlipRadar

[![CI](https://github.com/simiondavid23/FlipRadar/actions/workflows/ci.yml/badge.svg)](https://github.com/simiondavid23/FlipRadar/actions/workflows/ci.yml)

Aplicatie web pentru research-ul de produse profitabile in comertul online (revanzare). Permite monitorizarea preturilor pe mai multe magazine din Romania, analiza profitabilitatii produselor, gestionarea inventarului si a vanzarilor, plus alerte automate cand preturile scad.

Lucrare de licenta.

## Stack

- **Backend:** FastAPI, SQLAlchemy + SQLite, Pydantic v2, APScheduler, Playwright + curl_cffi + BeautifulSoup (scraping), JWT + bcrypt
- **Frontend:** Next.js 16 (App Router), React 19, Recharts, Lucide icons, inline styles
- **AI:** Groq (chat support, analiza produs, generator listing, raport AI)
- **Email:** SMTP optional (alerte / notificari)

## Setup

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
# .env: SECRET_KEY (min 32 char), DATABASE_URL, GROQ_API_KEY (optional),
#       SMTP_HOST/PORT/USER/PASSWORD/FROM (optional)
uvicorn app.main:app --reload
```

API: `http://127.0.0.1:8000` · docs: `/docs`

Baza de date e un fisier SQLite (`backend/flipradar.db`) creat automat la prima pornire — nu se instaleaza niciun server de baza de date. Backup: copiaza fisierul cu backend-ul oprit.

### Frontend

```bash
cd frontend
npm install
# .env.local: NEXT_PUBLIC_API_URL=http://localhost:8000
# ATENTIE: foloseste localhost, NU 127.0.0.1 — browserele trateaza `localhost` si
# `127.0.0.1` ca site-uri diferite pentru cookie-urile SameSite; cu 127.0.0.1 aici,
# autentificarea (cookie httpOnly) nu functioneaza.
npm run dev
```

App: `http://localhost:3000`

## Rulare teste local

Testele backend ruleaza pe un fisier SQLite temporar, unic per rulare — nu ating baza reala si nu au nevoie de niciun server de baza de date.

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

`conftest.py` creeaza singur fisierul SQLite temporar la pornire si il sterge la final; izolarea intre rulari concurente e structurala (fiecare proces are propriul fisier).

## Functionalitati

- Cont utilizator cu resetare parola pe baza de intrebare de securitate
- Catalog produse + scraping din Altex, eMAG, Sole, FarmaciaTei, PCGarage
- Watchlist + alerte de pret cu verificare periodica (15 min)
- Inventar & vanzari (conversie automata RON → EUR la cursul BNR), cu calcul rapid de profit pe articolele din inventar
- AI (Groq): analiza profitabilitate, generator listing, raport, chat support cu ticketing
- Favorite + blacklist
- Notificari in-app (optional + email prin SMTP)
- Import CSV / Excel · Export Excel (produse, watchlist, inventar) si PDF (vanzari)
- Admin panel (utilizatori, feature flags, tichete suport)
