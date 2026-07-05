import axios from "axios";
  
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

// Produse
export const productsAPI = {
  getProducts: (params) => api.get("/api/products/", { params }),
  getProduct: (id) => api.get(`/api/products/${id}`),
  getFilterOptions: (params) => api.get("/api/products/filter-options", { params }),
  // FlipRadar — autocomplete brand server-side + taxonomie categorii per sursa
  getBrands: (params) => api.get("/api/products/brands", { params }),
  getCategoriesBySource: (source) => api.get("/api/products/categories-by-source", { params: { source } }),
  getSourceCategories: (source) =>
    api.get("/api/products/source-categories", { params: source ? { source } : {} }),
  getStats: () => api.get("/api/products/stats"),
  createProduct: (data) => api.post("/api/products/", data),
  updateProduct: (id, data) => api.put(`/api/products/${id}`, data),
  refreshPrice: (id) => api.post(`/api/products/${id}/refresh-price`),
  deleteProduct: (id) => api.delete(`/api/products/${id}`),
  calculateProfit: (data) => api.post("/api/products/calculate-profit", data),
  // Sugestii de surse cross-shop (potrivire pe nume) — confirmare / respingere.
  confirmSuggestion: (productId, suggestionId) =>
    api.post(`/api/products/${productId}/suggestions/${suggestionId}/confirm`),
  deleteSuggestion: (productId, suggestionId) =>
    api.delete(`/api/products/${productId}/suggestions/${suggestionId}`),
};

// Lista de urmărit
export const watchlistAPI = {
  getWatchlist: () => api.get("/api/watchlist/"),
  addToWatchlist: (data) => api.post("/api/watchlist/", data),
  updateWatchlist: (id, data) => api.put(`/api/watchlist/${id}`, data),
  removeFromWatchlist: (id) => api.delete(`/api/watchlist/${id}`),
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

// Inteligență Artificială
export const aiAPI = {
  analyzeProduct: (data) => api.post("/api/ai/analyze-product", data),
  generateListing: (data) => api.post("/api/ai/generate-listing", data),
  getReport: () => api.get("/api/ai/report"),
  chat: (data) => api.post("/api/ai/chat", data),
  getChatHistory: () => api.get("/api/ai/chat/history"),
  clearChatHistory: () => api.delete("/api/ai/chat/history"),
};

// Administrare
export const adminAPI = {
  getStats: () => api.get("/api/admin/stats"),
  // tickets acceptă filtre { user_id, status }
  getTickets: (params) => api.get("/api/admin/tickets", { params }),
  getTicket: (id) => api.get(`/api/admin/tickets/${id}`),
  replyTicket: (id, data) => api.post(`/api/admin/tickets/${id}/reply`, data),
  closeTicket: (id) => api.put(`/api/admin/tickets/${id}/close`),
  runAlertCheck: () => api.post("/api/admin/run-alert-check"),
  // Administrare per utilizator
  getUsers: () => api.get("/api/admin/users"),
  getUser: (id) => api.get(`/api/admin/users/${id}`),
  setUserActive: (id, isActive) => api.put(`/api/admin/users/${id}/active`, { is_active: isActive }),
  updateUserFeatures: (id, flags) => api.put(`/api/admin/users/${id}/features`, flags),
  getProducts: (params) => api.get("/api/admin/products", { params }),
  getProductsReport: (params) => api.get("/api/admin/products/report", { params }),
  // FlipRadar — ITEM 17: export PDF al raportului de produse (acelasi filtru)
  exportProductsReportPdf: (params) => api.get("/api/admin/products/report/pdf", { params, responseType: "blob" }),
  getWatchlist: (params) => api.get("/api/admin/watchlist", { params }),
  getAlerts: (params) => api.get("/api/admin/alerts", { params }),
  getInventory: (params) => api.get("/api/admin/inventory", { params }),
  getSales: (params) => api.get("/api/admin/sales", { params }),
  getFavorites: (params) => api.get("/api/admin/favorites", { params }),
  getChatMessages: (params) => api.get("/api/admin/chat-messages", { params }),
};

// Setari utilizator (FlipRadar — ITEM 16)
export const usersAPI = {
  updateSettings: (data) => api.patch("/api/users/settings", data),
  getSettings: () => api.get("/api/users/settings"),
  // MODIFICARE 13 — status sesiuni platforme (Vinted/Okazii/LaJumate/Facebook)
  getSessionStatus: () => api.get("/api/users/settings/session-status"),
  updateAIFeatures: (config) => api.patch("/api/users/settings", { ai_features_config: config }),
};

// Jurnale Live — statistici per modul (stream-ul SSE se consuma direct cu EventSource)
export const logsAPI = {
  getLogs: (module) => api.get(`/api/logs/stats`),
};

// ML Predictor — statistici colectare date + predictie pret/timp + reantrenare
export const mlAPI = {
  getStats: () => api.get("/api/ml/stats"),
  predict: (payload) => api.post("/api/ml/predict", payload),
  retrain: () => api.post("/api/ml/retrain"),
  runSoldDetection: () => api.post("/api/ml/sold-detection"),
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
  getStats:       ()         => api.get("/api/auto-listings/stats"),
  scanNow:        ()         => api.post("/api/auto-listings/scan-now"),
  // Categorii + campuri tehnice confirmate per platforma (formular dinamic + cautare manuala)
  getCategories:  ()         => api.get("/api/auto-listings/categories"),
  // MODIFICARE 18 — impact stergere keyword (nr. listinguri asociate)
  getKeywordImpact: (id)     => api.get(`/api/auto-listings/keywords/${id}/impact`),
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

// Imobiliare Monitor — keyword-uri + feed scorat (zone, duplicate, price history)
export const realEstateMonitorAPI = {
  getKeywords:   ()         => api.get("/api/real-estate-monitor/keywords"),
  createKeyword: (data)     => api.post("/api/real-estate-monitor/keywords", data),
  updateKeyword: (id, data) => api.put(`/api/real-estate-monitor/keywords/${id}`, data),
  deleteKeyword: (id)       => api.delete(`/api/real-estate-monitor/keywords/${id}`),
  getFeed:       (params)   => api.get("/api/real-estate-monitor/feed", { params }),
  updateStatus:  (id, st)   => api.patch(`/api/real-estate-monitor/feed/${id}/status`, { status: st }),
  deleteListing: (id)       => api.delete(`/api/real-estate-monitor/feed/${id}`),
  flagDuplicate: (id, dupId) => api.post(`/api/real-estate-monitor/feed/${id}/flag-duplicate`, { duplicate_of_id: dupId }),
  getStats:      ()         => api.get("/api/real-estate-monitor/stats"),
  scanNow:       ()         => api.post("/api/real-estate-monitor/scan-now"),
  // MODIFICARE 18 — impact stergere keyword (nr. listinguri asociate)
  getKeywordImpact: (id)    => api.get(`/api/real-estate-monitor/keywords/${id}/impact`),
};

// Modulul 1 Marketplace — cautare live pe platforme (OLX, Vinted, etc.).
// `filters` se trimite ca JSON encodat in query string.
const _mpFilters = (filters) => (filters ? JSON.stringify(filters) : undefined);
export const marketplaceAPI = {
  // MODIFICARE 17 — opts = { page, per_page } pentru paginare "Încarcă mai multe".
  olxGeneral: (q, category = "", filters, opts = {}) =>
    api.get("/api/marketplace/olx-general", { params: { q, category, filters: _mpFilters(filters), page: opts.page, per_page: opts.per_page } }),
  vinted: (q, filters, opts = {}) =>
    api.get("/api/marketplace/vinted", { params: { q, filters: _mpFilters(filters), page: opts.page, per_page: opts.per_page } }),
  lajumate: (q, filters, opts = {}) => api.get("/api/marketplace/lajumate", { params: { q, filters: _mpFilters(filters), page: opts.page, per_page: opts.per_page } }),
  publi24: (q, filters, opts = {}) => api.get("/api/marketplace/publi24", { params: { q, filters: _mpFilters(filters), page: opts.page, per_page: opts.per_page } }),
  okazii: (q, filters, opts = {}) => api.get("/api/marketplace/okazii", { params: { q, filters: _mpFilters(filters), page: opts.page, per_page: opts.per_page } }),
  kleinanzeigen: (q, categoryId = "", filters, opts = {}) =>
    api.get("/api/marketplace/kleinanzeigen", { params: { q, category_id: categoryId, filters: _mpFilters(filters), page: opts.page, per_page: opts.per_page } }),
  searchAll: (q, platforms = "olx,vinted,okazii", filters, opts = {}) =>
    api.get("/api/marketplace/search-all", { params: { q, platforms, filters: _mpFilters(filters), page: opts.page, per_page: opts.per_page } }),
  // Anunturi salvate
  getSaved: () => api.get("/api/marketplace/saved"),
  saveListing: (data) => api.post("/api/marketplace/saved", data),
  deleteSaved: (id) => api.delete(`/api/marketplace/saved/${id}`),
  // Alerte keyword
  getKeywordAlerts: () => api.get("/api/marketplace/keyword-alerts"),
  createKeywordAlert: (data) => api.post("/api/marketplace/keyword-alerts", data),
  updateKeywordAlert: (id, data) => api.put(`/api/marketplace/keyword-alerts/${id}`, data),
  deleteKeywordAlert: (id) => api.delete(`/api/marketplace/keyword-alerts/${id}`),
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
  getAlerts: () => api.get("/api/real-estate/alerts"),
  createAlert: (data) => api.post("/api/real-estate/alerts", data),
  updateAlert: (id, data) => api.put(`/api/real-estate/alerts/${id}`, data),
  deleteAlert: (id) => api.delete(`/api/real-estate/alerts/${id}`),
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
  getPosts: (id, params) => api.get(`/api/facebook-groups/${id}/posts`, { params }),
  getAllPosts: (params) => api.get("/api/facebook-groups/posts/all", { params }),
  testRun: (id) => api.post(`/api/facebook-groups/${id}/test-run`),
};

// Tickete de suport
export const ticketsAPI = {
  getMyTickets: () => api.get("/api/support/tickets"),
  createTicket: (data) => api.post("/api/support/tickets", data),
  getTicket: (id) => api.get(`/api/support/tickets/${id}`),
  replyTicket: (id, data) => api.post(`/api/support/tickets/${id}/reply`, data),
};

// Favorite și Blacklist
export const favoritesAPI = {
  getFavorites: () => api.get("/api/favorites/"),
  getBlacklist: () => api.get("/api/favorites/blacklist"),
  addFavorite: (data) => api.post("/api/favorites/", data),
  removeFavorite: (id) => api.delete(`/api/favorites/${id}`),
};

// FlipRadar — Produse Urmarite (fuziune favorite + watchlist)
export const trackedProductsAPI = {
  getAll: () => api.get("/api/tracked-products/"),
  toggleMonitoring: (id, active, alert_threshold) =>
    api.patch(`/api/tracked-products/${id}/monitoring`, { active, alert_threshold }),
  remove: (id) => api.delete(`/api/tracked-products/${id}`),
};

// Notificări
export const notificationsAPI = {
  getNotifications: () => api.get("/api/notifications/"),
  getUnreadCount: () => api.get("/api/notifications/unread-count"),
  markAsRead: (id) => api.put(`/api/notifications/${id}/read`),
  markAllAsRead: () => api.put("/api/notifications/read-all"),
  clearAll: () => api.delete("/api/notifications/clear"),
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

// Import/Export date
export const importExportAPI = {
  importCSV: (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.post("/api/import-export/import-csv", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  importExcel: (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.post("/api/import-export/import-excel", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  exportProducts: () => api.get("/api/import-export/export-products", { responseType: "blob" }),
  exportWatchlist: () => api.get("/api/import-export/export-watchlist", { responseType: "blob" }),
  downloadTemplate: () => api.get("/api/import-export/template", { responseType: "blob" }),
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
  blockSeller: (id) => api.post(`/api/radar/listings/${id}/block-seller`),
  getBlockedSellers: () => api.get("/api/radar/blocked-sellers"),
  unblockSeller: (id) => api.delete(`/api/radar/blocked-sellers/${id}`),
  getSettings: () => api.get("/api/radar/settings"),
  updateSettings: (data) => api.put("/api/radar/settings", data),
  testDiscord: (webhook_url) =>
    api.post("/api/radar/settings/test-discord", { webhook_url }),
  testLaJumateCookie: () => api.get("/api/radar/lajumate/test"),
  testOkaziiCookie: () => api.get("/api/radar/okazii/test"),
  getFacebookStatus: () => api.get("/api/radar/facebook/status"),
  connectFacebook: () => api.post("/api/radar/facebook/connect"),
  getStats: () => api.get("/api/radar/stats"),
  scanNow: () => api.post("/api/radar/scan-now"),
  getCategories: () => api.get("/api/radar/categories"),
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

export default api;
