import axios from "axios";
  
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL
  || (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  // MODIFICARE 3 — trimite automat cookie-urile httpOnly de sesiune la fiecare request.
  withCredentials: true,
});

// MODIFICARE 3 — refresh automat al access_token-ului. La primul 401 pe un endpoint
// protejat, încearcă o singură dată /api/auth/refresh și reia request-ul original.
// Cererile concurente care primesc 401 în timpul unui refresh în curs sunt puse în
// așteptare și reluate după ce refresh-ul reușește (sau respinse dacă eșuează), ca
// să nu eșueze panourile care fac request-uri în paralel (ex: Dashboard).
// Dacă refresh-ul eșuează, redirecționează utilizatorul la /login.
let isRefreshing = false;
let refreshWaiters = [];
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !original.url?.includes("/auth/")
    ) {
      original._retry = true;
      // Un refresh e deja în curs — punem cererea în coadă și o reluăm după.
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          refreshWaiters.push({ resolve, reject, original });
        });
      }
      isRefreshing = true;
      try {
        await api.post("/api/auth/refresh");
        isRefreshing = false;
        const waiters = refreshWaiters;
        refreshWaiters = [];
        waiters.forEach((w) => w.resolve(api(w.original)));
        return api(original);
      } catch (refreshErr) {
        isRefreshing = false;
        const waiters = refreshWaiters;
        refreshWaiters = [];
        waiters.forEach((w) => w.reject(refreshErr));
        // Redirect la login dacă refresh-ul eșuează (reload-ul curăță starea React).
        if (typeof window !== "undefined") window.location.href = "/login";
        return Promise.reject(refreshErr);
      }
    }
    return Promise.reject(error);
  }
);

// Autentificare
export const authAPI = {
  register: (data) => api.post("/api/auth/register", data),
  login: (data) => api.post("/api/auth/login", data),
  logout: () => api.post("/api/auth/logout"),
  refresh: () => api.post("/api/auth/refresh"),
  getSecurityQuestion: (email) => api.get("/api/auth/security-question", { params: { email } }),
  resetPassword: (data) => api.post("/api/auth/reset-password", data),
  getMe: () => api.get("/api/auth/me"),
};

// Licentiere (KEY-1) — activare pe baza de cheie semnata Ed25519, mod desktop.
export const licenseAPI = {
  status: () => api.get("/api/license/status"),
  activate: (key) => api.post("/api/license/activate", { key }),
  session: () => api.post("/api/license/session"),
};

// Produse
export const productsAPI = {
  getProducts: (params) => api.get("/api/products/", { params }),
  getProduct: (id) => api.get(`/api/products/${id}`),
  getFilterOptions: (params) => api.get("/api/products/filter-options", { params }),
  getStats: () => api.get("/api/products/stats"),
  createProduct: (data) => api.post("/api/products/", data),
  updateProduct: (id, data) => api.put(`/api/products/${id}`, data),
  refreshPrice: (id) => api.post(`/api/products/${id}/refresh-price`),
  deleteProduct: (id) => api.delete(`/api/products/${id}`),
  // Sugestii de surse cross-shop (potrivire pe nume) — confirmare / respingere.
  confirmSuggestion: (productId, suggestionId) =>
    api.post(`/api/products/${productId}/suggestions/${suggestionId}/confirm`),
  deleteSuggestion: (productId, suggestionId) =>
    api.delete(`/api/products/${productId}/suggestions/${suggestionId}`),
};

// Alerte
export const alertsAPI = {
  getAlerts: () => api.get("/api/alerts/"),
  createAlert: (data) => api.post("/api/alerts/", data),
  toggleAlert: (id) => api.put(`/api/alerts/${id}/toggle`),
  deleteAlert: (id) => api.delete(`/api/alerts/${id}`),
};

// Panou principal
export const dashboardAPI = {
  getStats: () => api.get("/api/dashboard/stats"),
  getSalesTimeseries: (days) => api.get("/api/dashboard/sales-timeseries", { params: { days: days || 30 } }),
  getTopProducts: (limit) => api.get("/api/dashboard/top-products", { params: { limit: limit || 5 } }),
  // MODIFICARE 15 — status scheduler (joburi + next run)
  getSchedulerStatus: () => api.get("/api/dashboard/scheduler-status"),
};

// Setari utilizator (FlipRadar — ITEM 16)
export const usersAPI = {
  updateSettings: (data) => api.patch("/api/users/settings", data),
  getSettings: () => api.get("/api/users/settings"),
  updateAIFeatures: (config) => api.patch("/api/users/settings", { ai_features_config: config }),
  updateFlashDealThreshold: (fraction) => api.patch("/api/users/settings", { flash_deal_threshold: fraction }),
  // PKG-2 — furnizor AI comutabil. updateAISettings trimite doar campurile atinse
  // ({ai_provider, ai_model, ai_api_key?}); testAIConnection accepta {provider?, api_key?, model?}.
  updateAISettings: (data) => api.patch("/api/users/settings", data),
  testAIConnection: (data) => api.post("/api/users/ai/test", data),
};

// Jurnale Live — statistici per modul (stream-ul SSE se consuma direct cu EventSource)
export const logsAPI = {
  getLogs: (module) => api.get(`/api/logs/stats`),
};

// Auto Anunturi — keyword-uri + feed monitorizat (scoring + import cost)
export const autoListingsAPI = {
  // Keywords
  getKeywords:    ()         => api.get("/api/auto-listings/keywords"),
  createKeyword:  (data)     => api.post("/api/auto-listings/keywords", data),
  updateKeyword:  (id, data) => api.put(`/api/auto-listings/keywords/${id}`, data),
  deleteKeyword:  (id)       => api.delete(`/api/auto-listings/keywords/${id}`),
  // Feed
  getFeed:        (params)   => api.get("/api/auto-listings/feed", { params }),
  updateStatus:   (id, st)   => api.patch(`/api/auto-listings/feed/${id}/status`, { status: st }),
  deleteListing:  (id)       => api.delete(`/api/auto-listings/feed/${id}`),
  // Actiuni in masa pe selectie (saved/ignored/active/deleted) — mirror pe radarAPI.bulkAction
  bulkAction:     (listing_ids, action) => api.post("/api/auto-listings/feed/bulk-action", { listing_ids, action }),
  // Imbogatire on-demand a detaliului (poze/descriere/vanzator/data), o data per anunt
  getListingDetail: (id)     => api.get(`/api/auto-listings/feed/${id}/detail`),
  generateReview: (id)       => api.post(`/api/auto-listings/feed/${id}/generate-review`),
  renderTemplate: (listingId, data) => api.post(`/api/auto-listings/feed/${listingId}/render-template`, data),
  getStats:       ()         => api.get("/api/auto-listings/stats"),
  scanNow:        ()         => api.post("/api/auto-listings/scan-now"),
  // Categorii + campuri tehnice confirmate per platforma (formular dinamic + cautare manuala)
  getCategories:  ()         => api.get("/api/auto-listings/categories"),
  // MODIFICARE 18 — impact stergere keyword (nr. listinguri asociate)
  getKeywordImpact: (id)     => api.get(`/api/auto-listings/keywords/${id}/impact`),
  // Export Excel al feed-ului (aceleasi filtre ca lista) — descarcat ca blob.
  exportListings: (params)   => api.get("/api/auto-listings/feed/export", { params, responseType: "blob" }),
};

// Loturi Auto — keyword-uri monitorizate + feed de loturi (Copart/IAAI/SCA/OpenLane)
export const autoLotKeywordsAPI = {
  getKeywords:   ()         => api.get("/api/auto-lots/keywords"),
  createKeyword: (data)     => api.post("/api/auto-lots/keywords", data),
  updateKeyword: (id, data) => api.put(`/api/auto-lots/keywords/${id}`, data),
  deleteKeyword: (id)       => api.delete(`/api/auto-lots/keywords/${id}`),
  getFeed:       (params)   => api.get("/api/auto-lots/feed", { params }),
  updateStatus:  (id, st)   => api.patch(`/api/auto-lots/feed/${id}/status`, { status: st }),
  getStats:      ()         => api.get("/api/auto-lots/stats"),
  scanNow:       ()         => api.post("/api/auto-lots/scan-now"),
};

// Imobiliare Monitor — keyword-uri + feed scorat (zone, price history)
export const realEstateMonitorAPI = {
  getCategories: ()         => api.get("/api/real-estate-monitor/categories"),
  getKeywords:   ()         => api.get("/api/real-estate-monitor/keywords"),
  createKeyword: (data)     => api.post("/api/real-estate-monitor/keywords", data),
  updateKeyword: (id, data) => api.put(`/api/real-estate-monitor/keywords/${id}`, data),
  deleteKeyword: (id)       => api.delete(`/api/real-estate-monitor/keywords/${id}`),
  getFeed:       (params)   => api.get("/api/real-estate-monitor/feed", { params }),
  // Optiuni pentru dropdown-urile de filtrare a feed-ului (zone + orase distincte ale userului)
  getFilterOptions: ()      => api.get("/api/real-estate-monitor/feed/filter-options"),
  updateStatus:  (id, st)   => api.patch(`/api/real-estate-monitor/feed/${id}/status`, { status: st }),
  deleteListing: (id)       => api.delete(`/api/real-estate-monitor/feed/${id}`),
  // Actiuni in masa pe selectie (saved/ignored/active/deleted) — mirror pe radarAPI/auto bulkAction
  bulkAction:    (ids, action) => api.post("/api/real-estate-monitor/feed/bulk-action", { listing_ids: ids, action }),
  // Salvare din Cautarea Manuala in tabelul monitor (status="saved") — apare in Salvate & Ignorate
  saveManualListing: (data) => api.post("/api/real-estate-monitor/listings/save-manual", data),
  getStats:      ()         => api.get("/api/real-estate-monitor/stats"),
  scanNow:       ()         => api.post("/api/real-estate-monitor/scan-now"),
  // MODIFICARE 18 — impact stergere keyword (nr. listinguri asociate)
  getKeywordImpact: (id)    => api.get(`/api/real-estate-monitor/keywords/${id}/impact`),
  // Export Excel al feed-ului (aceleasi filtre ca lista) — descarcat ca blob.
  exportListings: (params)  => api.get("/api/real-estate-monitor/feed/export", { params, responseType: "blob" }),
};

// Auto — Loturi & Licitatii (Copart/IAAI/SCA/OpenLane) + calculator import
export const autoAPI = {
  calculateImport: (data) => api.post("/api/auto/calculate-import", data),
  searchLots: (q, platforms = "copart,iaai", filters) =>
    api.get("/api/auto/lots/search", { params: { q, platforms, filters: filters ? JSON.stringify(filters) : undefined } }),
  saveLot: (data) => api.post("/api/auto/lots/save", data),
  getSavedLots: () => api.get("/api/auto/lots/saved"),
  deleteSavedLot: (id) => api.delete(`/api/auto/lots/saved/${id}`),
  // Anunturi auto (OLX Auto / Autovit / Mobile.de / AutoScout24 / Kleinanzeigen)
  searchListings: (q, platforms = "autovit,olx_auto", filters) =>
    api.get("/api/auto/listings/search", { params: { q, platforms, filters: filters ? JSON.stringify(filters) : undefined } }),
  saveListing: (data) => api.post("/api/auto/listings/save", data),
  getSavedListings: () => api.get("/api/auto/listings/saved"),
  deleteSavedListing: (id) => api.delete(`/api/auto/listings/saved/${id}`),
  extractDescription: (data) => api.post("/api/auto/listings/extract-description", data),
};

// Imobiliare (OLX / Storia / Imobiliare.ro / Facebook)
export const realEstateAPI = {
  search: (params) => api.get("/api/real-estate/search", { params }),
  saveListing: (data) => api.post("/api/real-estate/listings/save", data),
  getSavedListings: () => api.get("/api/real-estate/listings/saved"),
  deleteSavedListing: (id) => api.delete(`/api/real-estate/listings/saved/${id}`),
};

// Grupuri Facebook (monitorizare imobiliare)
export const facebookGroupsAPI = {
  getConfigs: () => api.get("/api/facebook-groups"),
  createConfig: (data) => api.post("/api/facebook-groups", data),
  updateConfig: (id, data) => api.put(`/api/facebook-groups/${id}`, data),
  deleteConfig: (id) => api.delete(`/api/facebook-groups/${id}`),
  saveCookies: (id, cookiesJson) =>
    api.post(`/api/facebook-groups/${id}/cookies`, { cookies_json: cookiesJson }),
  deleteCookies: (id) => api.delete(`/api/facebook-groups/${id}/cookies`),
  testRun: (id) => api.post(`/api/facebook-groups/${id}/test-run`),
};

// FlipRadar — Produse Urmarite (fuziune favorite + watchlist)
export const trackedProductsAPI = {
  getAll: () => api.get("/api/tracked-products/"),
  toggleMonitoring: (id, active, alert_threshold) =>
    api.patch(`/api/tracked-products/${id}/monitoring`, { active, alert_threshold }),
  remove: (id) => api.delete(`/api/tracked-products/${id}`),
};

// Web Scraping
const _scrapeParams = (query, max, searchType) => {
  const params = { q: query };
  if (max !== undefined && max !== null) params.max_results = max;
  if (searchType && searchType !== "name") params.search_type = searchType;
  return params;
};

export const scrapingAPI = {
  searchAltex: (query, max, searchType) => api.get("/api/scraping/altex", { params: _scrapeParams(query, max, searchType) }),
  searchSole: (query, max, searchType) => api.get("/api/scraping/sole", { params: _scrapeParams(query, max, searchType) }),
  searchFarmaciatei: (query, max, searchType) => api.get("/api/scraping/farmaciatei", { params: _scrapeParams(query, max, searchType) }),
  searchEmag: (query, max, searchType) => api.get("/api/scraping/emag", { params: _scrapeParams(query, max, searchType) }),
  searchPcgarage: (query, max, searchType) => api.get("/api/scraping/pcgarage", { params: _scrapeParams(query, max, searchType) }),
  searchAll: (query, max, searchType) => api.get("/api/scraping/search-all", { params: _scrapeParams(query, max, searchType) }),
};

// Valute (cursuri BNR)
export const currencyAPI = {
  getRates: () => api.get("/api/currency/rates"),
  convert: (amount, from, to) => api.get("/api/currency/convert", { params: { amount, from, to } }),
};

// Inventar
export const inventoryAPI = {
  getItems: () => api.get("/api/inventory/"),
  getStats: () => api.get("/api/inventory/stats"),
  createItem: (data) => api.post("/api/inventory/", data),
  updateItem: (id, data) => api.put(`/api/inventory/${id}`, data),
  deleteItem: (id) => api.delete(`/api/inventory/${id}`),
  downloadTemplate: () => api.get("/api/inventory/template", { responseType: "blob" }),
  importExcel: (formData) => api.post("/api/inventory/import-excel", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }),
};

// Rapoarte
export const reportsAPI = {
  getSummary: (params) => api.get("/api/reports/summary", { params }),
};

// Radar Marketplace
export const radarAPI = {
  getKeywords: () => api.get("/api/radar/keywords"),
  createKeyword: (data) => api.post("/api/radar/keywords", data),
  updateKeyword: (id, data) => api.put(`/api/radar/keywords/${id}`, data),
  deleteKeyword: (id) => api.delete(`/api/radar/keywords/${id}`),
  // MODIFICARE 18 — impact stergere keyword (nr. listinguri asociate)
  getKeywordImpact: (id) => api.get(`/api/radar/keywords/${id}/impact`),
  toggleKeyword: (id) => api.patch(`/api/radar/keywords/${id}/toggle`),
  getListings: (params) => api.get("/api/radar/listings", { params }),
  searchManual: (data) => api.post("/api/radar/search-manual", data),
  getListing: (id) => api.get(`/api/radar/listings/${id}`),
  generateListingAIReview: (id) => api.get(`/api/radar/listings/${id}/ai-review`),
  getVintedDetail: (id) => api.get(`/api/radar/listings/${id}/vinted-detail`),
  getFacebookDetail: (id) => api.get(`/api/radar/listings/${id}/facebook-detail`),
  updateListingStatus: (id, status) =>
    api.patch(`/api/radar/listings/${id}/status`, { status }),
  deleteListing: (id) => api.delete(`/api/radar/listings/${id}`),
  getSettings: () => api.get("/api/radar/settings"),
  updateSettings: (data) => api.put("/api/radar/settings", data),
  testDiscord: (webhook_url) =>
    api.post("/api/radar/settings/test-discord", { webhook_url }),
  getFacebookStatus: () => api.get("/api/radar/facebook/status"),
  connectFacebook: () => api.post("/api/radar/facebook/connect"),
  getStats: () => api.get("/api/radar/stats"),
  scanNow: () => api.post("/api/radar/scan-now"),
  getCategories: () => api.get("/api/radar/categories"),
  // RP-2 — arbore dinamic de categorii Vinted + tester de excluderi
  getVintedCatalogs: (parentId) =>
    api.get("/api/radar/vinted-catalogs", { params: parentId != null ? { parent_id: parentId } : {} }),
  searchVintedCatalogs: (q) => api.get("/api/radar/vinted-catalogs/search", { params: { q } }),
  testExclusion: (keywordId, data) =>
    api.post(`/api/radar/keywords/${keywordId}/test-exclusion`, data),
  // Proxy
  getProxy: () => api.get("/api/radar/settings/proxy"),
  updateProxy: (data) => api.put("/api/radar/settings/proxy", data),
  // Șabloane mesaje
  getTemplates: () => api.get("/api/radar/templates"),
  createTemplate: (data) => api.post("/api/radar/templates", data),
  updateTemplate: (id, data) => api.put(`/api/radar/templates/${id}`, data),
  deleteTemplate: (id) => api.delete(`/api/radar/templates/${id}`),
  renderTemplate: (id, data) => api.post(`/api/radar/templates/${id}/render`, data),
  // Acțiuni în masă
  bulkAction: (listing_ids, action) =>
    api.post("/api/radar/listings/bulk-action", { listing_ids, action }),
  // Trend preț
  keywordPriceTrend: (id, days) =>
    api.get(`/api/radar/keywords/${id}/price-trend`, { params: { days } }),
  // Push notificări
  getVapidKey: () => api.get("/api/radar/push/vapid-public-key"),
  pushSubscribe: (data) => api.post("/api/radar/push/subscribe", data),
  pushUnsubscribe: (endpoint) =>
    api.delete("/api/radar/push/unsubscribe", { params: { endpoint } }),
  getPushStatus: () => api.get("/api/radar/push/status"),
  // Export Excel
  exportListings: (params) =>
    api.get("/api/radar/listings/export", { params, responseType: "blob" }),
};

// Vânzări
export const salesAPI = {
  getSales: () => api.get("/api/sales/"),
  getStats: () => api.get("/api/sales/stats"),
  createSale: (data) => api.post("/api/sales/", data),
  updateSale: (id, data) => api.put(`/api/sales/${id}`, data),
  deleteSale: (id) => api.delete(`/api/sales/${id}`),
  exportPDF: () => api.get("/api/sales/export-pdf", { responseType: "blob" }),
};

// PKG-UPD — versiune aplicatie + verificare de actualizare (GitHub Releases).
export const systemAPI = {
  getVersion: () => api.get("/api/version"),
};

export default api;
