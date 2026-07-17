"use client";
import { createContext, useContext, useState, useEffect, useCallback } from "react";
import axios from "axios";

const AuthContext = createContext(null);

const API_URL = process.env.NEXT_PUBLIC_API_URL
  || (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // MODIFICARE 3 — sesiunea e ținută în cookie-uri httpOnly; verificăm autentificarea
  // printr-un apel /me (cookie-ul pleacă automat cu withCredentials).
  const checkAuth = useCallback(async () => {
    try {
      const response = await axios.get(API_URL + "/api/auth/me", {
        withCredentials: true,
      });
      setUser(response.data);
    } catch {
      setUser(null);
    }
    setLoading(false);
  }, []);

  // Pattern legitim "fetch on mount": validam sesiunea (cookie) la pornirea
  // provider-ului. setState dupa fetch e inevitabil aici.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    checkAuth();
  }, [checkAuth]);

  const login = async (email, password) => {
    // Login setează cookie-urile httpOnly; răspunsul conține datele user-ului.
    const response = await axios.post(
      API_URL + "/api/auth/login",
      { email, password },
      { withCredentials: true }
    );
    const loggedUser = response.data?.user || null;
    setUser(loggedUser);
    return loggedUser;
  };

  const register = async (userData) => {
    const response = await axios.post(API_URL + "/api/auth/register", userData);
    return response.data;
  };

  const logout = async () => {
    // Cere backend-ului să șteargă cookie-urile de sesiune.
    try {
      await axios.post(API_URL + "/api/auth/logout", {}, { withCredentials: true });
    } catch {
      /* chiar dacă apelul eșuează, curățăm starea locală */
    }
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
};