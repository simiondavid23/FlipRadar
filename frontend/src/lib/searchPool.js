/**
 * SEARCH-2 — executia paralela a unei cautari pe mai multe magazine.
 *
 * Fara React, deliberat: pagina are deja destula stare, iar regula de paralelism e
 * pur algoritmica si merita citita separat de randare.
 *
 * De ce `concurrency = 6`: rutele generice n-au rate limit (SEARCH-1b), iar poarta
 * din backend respecta `min_fetch_interval_s` PER DOMENIU — deci paralelismul e intre
 * magazine DIFERITE si nu apasa pe niciunul. Sase e destul ca 21 de domenii sa termine
 * in ~3 valuri, fara sa deschida 21 de conexiuni deodata.
 */

/**
 * Ruleaza `worker` peste `items`, cel mult `concurrency` deodata.
 *
 * `onResult(item, outcome)` se cheama IMEDIAT dupa fiecare element — de aici vine
 * randarea progresiva ceruta de SEARCH-2 (noriel a raspuns in 12 s la SEARCH-0; o
 * pagina care asteapta ultimul magazin ar parea blocata). `outcome` e mereu
 * `{ok: true, data}` sau `{ok: false, error}`; `runPool` nu arunca niciodata.
 *
 * `isStale()` spune ca o cautare NOUA a inceput intre timp. Cand devine adevarat,
 * rezultatul curent se arunca SI lucratorul se opreste — cererile deja plecate nu se
 * pot anula (nu exista `AbortController` pe axios in proiect si nu se introduce
 * acum), dar cele inca neplecate n-au niciun motiv sa mai plece.
 *
 * Intoarce o promisiune care se rezolva cand toti lucratorii s-au terminat.
 */
export function runPool(items, worker, { concurrency = 6, onResult, isStale } = {}) {
  const coada = [...items];
  const invechit = () => (typeof isStale === "function" ? isStale() : false);

  async function lucrator() {
    while (coada.length) {
      if (invechit()) return;
      const item = coada.shift();

      let rezultat;
      try {
        rezultat = { ok: true, data: await worker(item) };
      } catch (error) {
        rezultat = { ok: false, error };
      }

      if (invechit()) return;
      if (typeof onResult === "function") {
        // `onResult` e cod de randare; o exceptie de acolo n-are voie sa omoare
        // lucratorul si sa lase restul magazinelor in „se cauta…" pe veci.
        try {
          onResult(item, rezultat);
        } catch (e) {
          console.error("runPool: onResult a aruncat", e);
        }
      }
    }
  }

  const cati = Math.max(1, Math.min(concurrency, coada.length));
  return Promise.all(Array.from({ length: cati }, () => lucrator()));
}
