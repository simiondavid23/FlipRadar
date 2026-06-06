import axios from "axios";
  
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("flipradar_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login")
    ) {
      localStorage.removeItem("flipradar_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// Autentificare
export const authAPI = {
  register: (data) => api.post("/api/auth/register", data),
  login: (data) => api.post("/api/auth/login", data),
  getSecurityQuestion: (email) => api.get("/api/auth/security-question", { params: { email } }),
  resetPassword: (data) => api.post("/api/auth/reset-password", data),
  getMe: () => api.get("/api/auth/me"),
};

// Produse
export const productsAPI = {
  getProducts: (params) => api.get("/api/products/", { params }),
  getProduct: (id) => api.get(`/api/products/${id}`),
  getFilterOptions: () => api.get("/api/products/filter-options"),
  getStats: () => api.get("/api/products/stats"),
  createProduct: (data) => api.post("/api/products/", data),
  updateProduct: (id, data) => api.put(`/api/products/${id}`, data),
  refreshPrice: (id) => api.post(`/api/products/${id}/refresh-price`),
  deleteProduct: (id) => api.delete(`/api/products/${id}`),
  calculateProfit: (data) => api.post("/api/products/calculate-profit", data),
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
  toggleKeyword: (id) => api.patch(`/api/radar/keywords/${id}/toggle`),
  getListings: (params) => api.get("/api/radar/listings", { params }),
  getListing: (id) => api.get(`/api/radar/listings/${id}`),
  generateListingAIReview: (id) => api.get(`/api/radar/listings/${id}/ai-review`),
  updateListingStatus: (id, status) =>
    api.patch(`/api/radar/listings/${id}/status`, { status }),
  blockSeller: (id) => api.post(`/api/radar/listings/${id}/block-seller`),
  getBlockedSellers: () => api.get("/api/radar/blocked-sellers"),
  unblockSeller: (id) => api.delete(`/api/radar/blocked-sellers/${id}`),
  getPresets: () => api.get("/api/radar/presets"),
  savePreset: (data) => api.post("/api/radar/presets", data),
  deletePreset: (id) => api.delete(`/api/radar/presets/${id}`),
  loadPreset: (id) => api.post(`/api/radar/presets/${id}/load`),
  getSettings: () => api.get("/api/radar/settings"),
  updateSettings: (data) => api.put("/api/radar/settings", data),
  testDiscord: (webhook_url) =>
    api.post("/api/radar/settings/test-discord", { webhook_url }),
  getFacebookStatus: () => api.get("/api/radar/facebook/status"),
  connectFacebook: () => api.post("/api/radar/facebook/connect"),
  getStats: () => api.get("/api/radar/stats"),
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
