# Curățarea istoricului Git — ștergerea sesiunii Facebook expuse

> **Rulează acest runbook DOAR tu (David), manual.** Claude Code NU execută
> niciun pas de aici. Fiecare comandă rescrie istoricul întregului repo, deci
> trebuie făcută conștient și o singură dată, în ordinea de mai jos.

Fișierul `backend/data/facebook_session_13.json` a conținut o sesiune Facebook
autentificată (cookie-uri `c_user` + `xs`). A fost șters din working tree și
`backend/data/` a fost adăugat în `.gitignore`, dar **fișierul rămâne în
istoricul Git** (în commit-urile vechi) până când rulezi pașii de mai jos.

---

## PRECONDIȚIE OBLIGATORIE — invalidează sesiunea ÎNTÂI

**Înainte de orice comandă Git de mai jos, invalidează sesiunea Facebook.**
Ștergerea din istoric NU protejează nimic dacă sesiunea e încă validă: oricine
a văzut deja fișierul are cookie-urile, iar ele rămân folosibile.

1. Facebook → **Setări și confidențialitate** → **Setări** → **Securitate și
   autentificare** → **„Unde ești conectat" / „Where you're logged in"**.
2. Apasă **„Deconectează-te de peste tot" / „Log out of all sessions"**.
3. **Schimbă parola** contului (invalidează definitiv cookie-urile `xs` vechi).

Abia după ce ai făcut asta are sens să cureți istoricul.

---

## Pași — curățarea istoricului cu git-filter-repo

Ordinea recomandată: **comite întâi TOATE schimbările** din B1 (backend) și din
promptul de frontend, apoi rulează runbook-ul. `git filter-repo` curăță fișierul
din **întreaga** istorie, inclusiv din commit-urile noi — deci le poți comite
liniștit înainte.

1. **Instalează git-filter-repo**
   ```bash
   pip install git-filter-repo
   ```

2. **Fă o clonă proaspătă** a repo-ului (filter-repo cere un clone curat, nu
   working tree-ul curent):
   ```bash
   git clone <URL_REMOTE_ORIGIN> flipRadar-purge
   cd flipRadar-purge
   ```

3. **Șterge fișierul din tot istoricul:**
   ```bash
   git filter-repo --invert-paths --path backend/data/facebook_session_13.json
   ```

4. **Re-adaugă remote-ul `origin`** (filter-repo îl șterge intenționat, ca
   măsură de siguranță):
   ```bash
   git remote add origin <URL_REMOTE_ORIGIN>
   ```

5. **Forțează push-ul istoricului rescris** (toate ramurile + tag-urile):
   ```bash
   git push --force --all
   git push --force --tags
   ```

6. **Re-clonează local după push.** Hash-urile TUTUROR commit-urilor se schimbă,
   deci orice clonă veche devine incompatibilă — inclusiv cea folosită de Claude
   Code. Șterge clonele vechi și fă un `git clone` nou peste tot unde lucrezi.

---

## Avertisment — protecția reală

GitHub (și orice fork / clonă / cache de CI) poate păstra commit-urile vechi o
vreme, chiar și după `--force`. Prin urmare **curățarea istoricului nu este o
garanție**: singura protecție reală este invalidarea sesiunii din PRECONDIȚIE.
Tratează cookie-urile ca fiind deja compromise și bazează-te pe schimbarea
parolei, nu pe ștergerea din Git.
