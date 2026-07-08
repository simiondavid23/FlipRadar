# FlipRadar

[![CI](https://github.com/simiondavid23/FlipRadar/actions/workflows/ci.yml/badge.svg)](https://github.com/simiondavid23/FlipRadar/actions/workflows/ci.yml)

Aplicatie web pentru research-ul de produse profitabile in comertul online (revanzare). Permite monitorizarea preturilor pe mai multe magazine din Romania, analiza profitabilitatii produselor, gestionarea inventarului si a vanzarilor, plus alerte automate cand preturile scad.

Lucrare de licenta.

## Stack

- **Backend:** FastAPI, SQLAlchemy + PostgreSQL, Pydantic v2, APScheduler, Playwright + curl_cffi + BeautifulSoup (scraping), JWT + bcrypt
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

Testele backend folosesc o baza PostgreSQL **dedicata** (`flipradar_test`), niciodata cea reala.

```bash
cd backend
pip install -r requirements-dev.txt
# In backend/.env adauga linia (cu parola ta reala de postgres):
#   TEST_DATABASE_URL=postgresql://postgres:parola@localhost:5432/flipradar_test
pytest
```

`conftest.py` creeaza singur baza `flipradar_test` la prima rulare daca nu exista si
refuza sa porneasca daca `TEST_DATABASE_URL` lipseste sau e egala cu `DATABASE_URL`.

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
