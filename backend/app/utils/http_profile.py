"""Profilul de impersonare TLS/HTTP2 al scraperelor (curl_cffi) — o singura sursa.

Pana acum fiecare scraper isi definea propriul `_IMPERSONATE = "chrome110"`. Chrome 110
e din februarie 2023: amprenta lui TLS/HTTP2 nu mai apare in trafic real, deci profilul
devenise el insusi un SEMNAL de detectie, iar actualizarea cerea editat 9 fisiere.

De ce aliasul "chrome" si nu o versiune fixa:
  * `curl_cffi` e PINUIT in requirements.txt (0.15.0), deci aliasul se rezolva
    determinist si identic pe orice masina (Windows de dezvoltare, Pi de productie)
    — la 0.15.0 inseamna chrome146. Nu exista "deriva" intre masini.
  * O versiune fixa in cod imbatraneste TACUT: nimeni nu observa ca a ramas in urma
    decat cand incep blocajele. Aliasul urmeaza automat cel mai nou profil disponibil
    in versiunea instalata, iar upgrade-ul de profil devine un bump de dependinta,
    verificabil in requirements.
  * Riscul aliasului (se schimba sub tine la un upgrade de curl_cffi) e exact ce
    controleaza pin-ul din requirements.

Exceptii per platforma: `PLATFORM_IMPERSONATE`. Se pune aici o platforma DOAR cand
profilul modern o REGRESEAZA masurat live (mergea inainte, nu mai merge dupa), cu
data si simptomul in comentariu — nu preventiv.
"""

# Aliasul curl_cffi: cel mai nou profil Chrome din versiunea instalata (0.15.0 -> chrome146).
DEFAULT_IMPERSONATE = "chrome"

# Exceptii masurate, per platforma. Gol = toate platformele folosesc profilul implicit.
# Format: "platforma": "profil"   # AAAA-LL-ZZ: simptomul care a impus exceptia
PLATFORM_IMPERSONATE: dict[str, str] = {}


def impersonate_for(platform: str) -> str:
    """Profilul platformei: exceptia ei daca exista, altfel cel implicit."""
    return PLATFORM_IMPERSONATE.get((platform or "").strip().lower(), DEFAULT_IMPERSONATE)
