"use client";
import { createContext, useContext, useState, useEffect, useCallback } from "react";
import axios from "axios";

const AuthContext = createContext(null);

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const getToken = () => {
    try {
      return localStorage.getItem("flipradar_token");
    } catch {
      return null;
    }
  };

  const checkAuth = useCallback(async () => {
    const token = getToken();
    if (token) {
      try {
        const response = await axios.get(API_URL + "/api/auth/me", {
          headers: { Authorization: "Bearer " + token },
        });
        setUser(response.data);
      } catch {
        console.log("Token invalid, clearing");
        localStorage.removeItem("flipradar_token");
      }
    }
    setLoading(false);
  }, []);

  // Pattern legitim "fetch on mount": validam token-ul din localStorage la
  // pornirea provider-ului. setState dupa fetch e inevitabil aici.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    checkAuth();
  }, [checkAuth]);

  const login = async (email, password) => {
    const response = await axios.post(API_URL + "/api/auth/login", {
      email,
      password,
    });
    const token = response.data.access_token;
    localStorage.setItem("flipradar_token", token);

    const userResponse = await axios.get(API_URL + "/api/auth/me", {
      headers: { Authorization: "Bearer " + token },
    });
    setUser(userResponse.data);
    return userResponse.data;
  };

  const register = async (userData) => {
    const response = await axios.post(API_URL + "/api/auth/register", userData);
    return response.data;
  };

  const logout = () => {
    localStorage.removeItem("flipradar_token");
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