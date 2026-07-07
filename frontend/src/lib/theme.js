"use client";
import { createContext, useContext, useEffect, useSyncExternalStore } from "react";

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

// Store extern minimal pentru temă. Folosim useSyncExternalStore în loc de
// useState + setState-în-efect: getServerSnapshot => "dark" păstrează hidratarea
// în doi pași (server + prima randare client = "dark", apoi valoarea reală din
// localStorage), deci fără nepotriviri de hidratare în Sidebar/login și fără
// setState în efect. Un lazy initializer simplu ar randa direct valoarea din
// localStorage pe client, nepotrivită cu "dark" randat pe server.
const listeners = new Set();
function subscribe(callback) {
  listeners.add(callback);
  if (typeof window !== "undefined") window.addEventListener("storage", callback);
  return () => {
    listeners.delete(callback);
    if (typeof window !== "undefined") window.removeEventListener("storage", callback);
  };
}
function notify() {
  listeners.forEach((l) => l());
}

export function ThemeProvider({ children }) {
  const theme = useSyncExternalStore(subscribe, readStoredTheme, () => "dark");

  // Scriptul inline din layout setează data-theme la primul paint; aici acoperim
  // schimbările ulterioare (toggle în tab curent, eveniment storage din alt tab).
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // localStorage poate fi indisponibil (mod privat, etc.) — ignorăm
    }
    document.documentElement.setAttribute("data-theme", next);
    notify();
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
