"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import axios from "axios";
import { Mail, Lock, ArrowRight, AlertCircle } from "lucide-react";
import { licenseAPI } from "@/lib/api";
import AuthShell, {
  AuthCardHeader, authLabelStyle, authFieldStyle, authInputStyle,
} from "@/components/shared/AuthShell";

const API_URL = process.env.NEXT_PUBLIC_API_URL
  || (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // KEY-1 — in modul desktop nu exista login clasic: redirectam catre activarea prin cheie.
  useEffect(() => {
    licenseAPI
      .status()
      .then((res) => {
        if (res.data?.local_mode) window.location.href = "/activate";
      })
      .catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      // MODIFICARE 3 — login setează cookie-urile httpOnly; răspunsul conține user-ul.
      await axios.post(
        API_URL + "/api/auth/login",
        { email, password },
        { withCredentials: true }
      );
      window.location.href = "/dashboard";
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (typeof detail === "string") {
        setError(detail);
      } else {
        setError("Email sau parola incorecta");
      }
      setLoading(false);
    }
  };

  return (
    <AuthShell>
      <AuthCardHeader title="Autentificare" subtitle="Introdu datele contului tău pentru a continua" />

      {error && (
        <div
          style={{
            display: "flex", alignItems: "center", gap: "9px", padding: "11px 13px",
            borderRadius: "11px", marginBottom: "16px",
            background: "rgba(248,113,113,.08)", border: "1px solid rgba(248,113,113,.3)",
          }}
        >
          <AlertCircle style={{ width: "14px", height: "14px", color: "#f87171", flexShrink: 0 }} strokeWidth={1.8} />
          <p style={{ color: "#fca5a5", fontSize: "12px", margin: 0 }}>{error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        <div>
          <label style={authLabelStyle}>Email</label>
          <div style={authFieldStyle}>
            <Mail style={{ width: "14px", height: "14px", color: "#54648a", flexShrink: 0 }} strokeWidth={1.8} />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@exemplu.com"
              required
              style={authInputStyle}
            />
          </div>
        </div>

        <div>
          <label style={authLabelStyle}>Parolă</label>
          <div style={authFieldStyle}>
            <Lock style={{ width: "14px", height: "14px", color: "#54648a", flexShrink: 0 }} strokeWidth={1.8} />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Introdu parola"
              required
              style={authInputStyle}
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="btn-auth"
        >
          {loading ? (
            <div style={{ width: "16px", height: "16px", border: "2px solid rgba(34,211,238,.5)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
          ) : (
            <>Intră în cont <ArrowRight style={{ width: "13px", height: "13px" }} strokeWidth={2} /></>
          )}
        </button>
      </form>

      <div style={{ display: "flex", alignItems: "center", gap: "10px", margin: "22px 0 16px" }}>
        <div style={{ flex: 1, height: "1px", background: "rgba(94,140,255,.14)" }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".14em", color: "#41547a" }}>SAU</span>
        <div style={{ flex: 1, height: "1px", background: "rgba(94,140,255,.14)" }} />
      </div>

      <p style={{ textAlign: "center", color: "#8b9cbd", fontSize: "12.5px", margin: 0 }}>
        Nu ai cont? <Link href="/register" style={{ fontWeight: 600 }}>Creează cont gratuit</Link>
      </p>

      <p style={{ textAlign: "center", fontSize: "12.5px", marginTop: "10px" }}>
        <Link href="/reset-password" style={{ color: "#54648a" }}>Ai uitat parola?</Link>
      </p>
    </AuthShell>
  );
}
