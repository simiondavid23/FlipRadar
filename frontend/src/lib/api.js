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

// Auth
export const authAPI = {
  register: (data) => api.post("/api/auth/register", data),
  login: (data) => api.post("/api/auth/login", data),
  getSecurityQuestion: (email) => api.get("/api/auth/security-question", { params: { email } }),
  resetPassword: (data) => api.post("/api/auth/reset-password", data),
  getMe: () => api.get("/api/auth/me"),
};

// Products
export const productsAPI = {
  getProducts: (params) => api.get("/api/products/", { params }),
  getProduct: (id) => api.get(`/api/products/${id}`),
  createProduct: (data) => api.post("/api/products/", data),
  updateProduct: (id, data) => api.put(`/api/products/${id}`, data),
  deleteProduct: (id) => api.delete(`/api/products/${id}`),
  calculateProfit: (data) => api.post("/api/products/calculate-profit", data),
};

// Watchlist
export const watchlistAPI = {
  getWatchlist: () => api.get("/api/watchlist/"),
  addToWatchlist: (data) => api.post("/api/watchlist/", data),
  updateWatchlist: (id, data) => api.put(`/api/watchlist/${id}`, data),
  removeFromWatchlist: (id) => api.delete(`/api/watchlist/${id}`),
};

// Alerts
export const alertsAPI = {
  getAlerts: () => api.get("/api/alerts/"),
  createAlert: (data) => api.post("/api/alerts/", data),
  toggleAlert: (id) => api.put(`/api/alerts/${id}/toggle`),
  deleteAlert: (id) => api.delete(`/api/alerts/${id}`),
};

// Dashboard
export const dashboardAPI = {
  getStats: () => api.get("/api/dashboard/stats"),
  getSalesTimeseries: (days) => api.get("/api/dashboard/sales-timeseries", { params: { days: days || 30 } }),
  getTopProducts: (limit) => api.get("/api/dashboard/top-products", { params: { limit: limit || 5 } }),
};

// AI
export const aiAPI = {
  analyzeProduct: (data) => api.post("/api/ai/analyze-product", data),
  generateListing: (data) => api.post("/api/ai/generate-listing", data),
  getReport: () => api.get("/api/ai/report"),
  chat: (data) => api.post("/api/ai/chat", data),
  getChatHistory: () => api.get("/api/ai/chat/history"),
  clearChatHistory: () => api.delete("/api/ai/chat/history"),
};

// Admin
export const adminAPI = {
  getStats: () => api.get("/api/admin/stats"),
  // tickets supports { user_id, status } filters
  getTickets: (params) => api.get("/api/admin/tickets", { params }),
  getTicket: (id) => api.get(`/api/admin/tickets/${id}`),
  replyTicket: (id, data) => api.post(`/api/admin/tickets/${id}/reply`, data),
  closeTicket: (id) => api.put(`/api/admin/tickets/${id}/close`),
  runAlertCheck: () => api.post("/api/admin/run-alert-check"),
  // Per-user administration
  getUsers: () => api.get("/api/admin/users"),
  getUser: (id) => api.get(`/api/admin/users/${id}`),
  setUserActive: (id, isActive) => api.put(`/api/admin/users/${id}/active`, { is_active: isActive }),
  updateUserFeatures: (id, flags) => api.put(`/api/admin/users/${id}/features`, flags),
  getProducts: (params) => api.get("/api/admin/products", { params }),
  getWatchlist: (params) => api.get("/api/admin/watchlist", { params }),
  getAlerts: (params) => api.get("/api/admin/alerts", { params }),
  getInventory: (params) => api.get("/api/admin/inventory", { params }),
  getSales: (params) => api.get("/api/admin/sales", { params }),
  getFavorites: (params) => api.get("/api/admin/favorites", { params }),
  getChatMessages: (params) => api.get("/api/admin/chat-messages", { params }),
};

// Support Tickets
export const ticketsAPI = {
  getMyTickets: () => api.get("/api/support/tickets"),
  createTicket: (data) => api.post("/api/support/tickets", data),
  getTicket: (id) => api.get(`/api/support/tickets/${id}`),
  replyTicket: (id, data) => api.post(`/api/support/tickets/${id}/reply`, data),
};

// Favorites & Blacklist
export const favoritesAPI = {
  getFavorites: () => api.get("/api/favorites/"),
  getBlacklist: () => api.get("/api/favorites/blacklist"),
  addFavorite: (data) => api.post("/api/favorites/", data),
  removeFavorite: (id) => api.delete(`/api/favorites/${id}`),
};

// Notifications
export const notificationsAPI = {
  getNotifications: () => api.get("/api/notifications/"),
  getUnreadCount: () => api.get("/api/notifications/unread-count"),
  markAsRead: (id) => api.put(`/api/notifications/${id}/read`),
  markAllAsRead: () => api.put("/api/notifications/read-all"),
  clearAll: () => api.delete("/api/notifications/clear"),
};

// Web Scraping
export const scrapingAPI = {
  searchAltex: (query, max) => api.get("/api/scraping/altex", { params: { q: query, max_results: max } }),
  searchSole: (query, max) => api.get("/api/scraping/sole", { params: { q: query, max_results: max } }),
  searchFarmaciatei: (query, max) => api.get("/api/scraping/farmaciatei", { params: { q: query, max_results: max } }),
  searchEmag: (query, max) => api.get("/api/scraping/emag", { params: { q: query, max_results: max } }),
  searchPcgarage: (query, max) => api.get("/api/scraping/pcgarage", { params: { q: query, max_results: max } }),
  searchAll: (query, max) => api.get("/api/scraping/search-all", { params: { q: query, max_results: max } }),
};

// Import/Export
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

// Currency (BNR rates)
export const currencyAPI = {
  getRates: () => api.get("/api/currency/rates"),
  convert: (amount, from, to) => api.get("/api/currency/convert", { params: { amount, from, to } }),
};

// Inventory
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

// Sales
export const salesAPI = {
  getSales: () => api.get("/api/sales/"),
  getStats: () => api.get("/api/sales/stats"),
  createSale: (data) => api.post("/api/sales/", data),
  updateSale: (id, data) => api.put(`/api/sales/${id}`, data),
  deleteSale: (id) => api.delete(`/api/sales/${id}`),
  exportPDF: () => api.get("/api/sales/export-pdf", { responseType: "blob" }),
};

export default api;
