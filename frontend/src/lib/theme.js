"use client";
import { createContext, useContext, useEffect, useState } from "react";

const ThemeContext = createContext({ theme: "dark", toggleTheme: () => {} });

const STORAGE_KEY = "flipradar-theme";

function readStoredTheme() {
  if (typeof window === "undefined") return "dark";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      return "light";
    }
  } catch {
    // ignorăm — cade pe valoarea implicită
  }
  return "dark";
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState("dark");

  useEffect(() => {
    const initial = readStoredTheme();
    setTheme(initial);
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", initial);
    }
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // localStorage poate fi indisponibil (mod privat, etc.) — ignorăm
      }
      if (typeof document !== "undefined") {
        document.documentElement.setAttribute("data-theme", next);
      }
      return next;
    });
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
