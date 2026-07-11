// Curs EUR->RON per anunt: rata din listing daca exista (import_score_json), altfel
// constanta 5.0. Unificat din auto-listings/feed + real-estate-monitor/feed — REF-1.
export function eurRonOf(listing) {
  return listing.import_score_json?.pe_roti?.eur_ron_rate
    || listing.import_score_json?.pe_platforma?.eur_ron_rate || 5.0;
}
