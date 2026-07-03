"use client";
import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import axios from "axios";
import { useTheme } from "@/lib/theme";
import { Mail, Lock, ArrowRight, AlertCircle, TrendingUp, ShieldCheck, Zap, Sun, Moon } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function ThemeToggleFloating() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      onClick={toggleTheme}
      title={theme === "light" ? "Comuta la tema intunecata" : "Comuta la tema luminoasa"}
      style={{
        position: "fixed", top: "1rem", right: "1rem", zIndex: 100,
        padding: "0.5rem", borderRadius: "0.5rem",
        border: "1px solid var(--border-color)",
        backgroundColor: "var(--bg-card)",
        color: "var(--text-secondary)",
        cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      {theme === "light" ? (
        <Moon style={{ width: "20px", height: "20px" }} />
      ) : (
        <Sun style={{ width: "20px", height: "20px" }} />
      )}
    </button>
  );
}

export default function LoginPage() {
  const { theme } = useTheme();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      // MODIFICARE 3 — login setează cookie-urile httpOnly; răspunsul conține user-ul.
      const loginRes = await axios.post(
        API_URL + "/api/auth/login",
        { email, password },
        { withCredentials: true }
      );
      if (loginRes.data?.user?.is_admin) {
        window.location.href = "/admin";
      } else {
        window.location.href = "/dashboard";
      }
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

  const inputStyle = {
    width: "100%",
    borderRadius: "0.75rem",
    color: "var(--text-primary)",
    fontSize: "0.875rem",
    backgroundColor: "var(--bg-dark)",
    border: "1px solid var(--border-color)",
    paddingLeft: "3rem",
    paddingRight: "1rem",
    paddingTop: "0.75rem",
    paddingBottom: "0.75rem",
    outline: "none",
  };

  const labelStyle = { display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.625rem", color: "var(--text-secondary)" };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", backgroundColor: "var(--bg-dark)" }}>
      <ThemeToggleFloating />
      <div className="login-topbar" style={{ alignItems: "center", padding: "1.5rem", position: "relative", zIndex: 10 }}>
        <Image
          src={theme === "light" ? "/flipradar-logo-light.svg" : "/flipradar-logo.svg"}
          alt="FlipRadar"
          width={180}
          height={39}
          priority
          style={{ height: "auto" }}
        />
      </div>

      <div className="login-grid" style={{ flex: 1, display: "grid", alignItems: "center" }}>
        <div className="login-branding" style={{ flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "3rem", position: "relative", overflow: "hidden" }}>
          <div
            style={{
              position: "absolute", inset: 0,
              backgroundImage: `linear-gradient(rgba(51, 65, 85, 0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(51, 65, 85, 0.3) 1px, transparent 1px)`,
              backgroundSize: "60px 60px",
              maskImage: "radial-gradient(ellipse at center, black 40%, transparent 75%)",
              WebkitMaskImage: "radial-gradient(ellipse at center, black 40%, transparent 75%)",
            }}
          />
          <div
            style={{
              position: "absolute", top: "50%", left: "50%",
              transform: "translate(-50%, -50%)",
              width: "500px", height: "500px", borderRadius: "50%",
              background: "radial-gradient(circle, rgba(37, 99, 235, 0.15) 0%, transparent 70%)",
            }}
          />
          <div style={{ position: "relative", zIndex: 10, textAlign: "center", maxWidth: "32rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <h1 style={{ fontSize: "2.25rem", fontWeight: 700, color: "var(--text-primary)", lineHeight: 1.2 }}>
              Descopera produse <span style={{ color: "#60a5fa" }}>profitabile</span> pentru revanzare
            </h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "1.125rem" }}>
              Analizeaza piata, monitorizeaza preturile si gaseste cele mai bune oportunitati de revanzare.
            </p>
            <div style={{ alignSelf: "center", display: "inline-flex", flexDirection: "column", gap: "0.75rem", paddingTop: "1rem" }}>
              {[
                { icon: TrendingUp, text: "Analiza automata a profitabilitatii" },
                { icon: Zap, text: "Alerte in timp real pentru oportunitati" },
                { icon: ShieldCheck, text: "Date verificate din surse multiple" },
              ].map(({ icon: Icon, text }, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <div style={{ width: "2.25rem", height: "2.25rem", borderRadius: "0.5rem", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, backgroundColor: "rgba(37, 99, 235, 0.15)" }}>
                    <Icon style={{ width: "1rem", height: "1rem", color: "#60a5fa" }} />
                  </div>
                  <span style={{ color: "var(--text-secondary)", fontSize: "0.875rem", textAlign: "left" }}>{text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="login-form-wrap" style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem" }}>
          <div style={{ width: "100%", maxWidth: "28rem" }}>
            <div className="login-mobile-logo" style={{ textAlign: "center", marginBottom: "2rem" }}>
              <Image
                src="/flipradar-icon.svg"
                alt=""
                width={56}
                height={56}
                priority
                style={{ marginBottom: "0.75rem" }}
              />
              <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>FlipRadar</h1>
            </div>

            <div style={{ marginBottom: "2.5rem", textAlign: "center" }}>
              <h2 style={{ fontSize: "1.875rem", fontWeight: 600, color: "var(--text-primary)" }}>Autentificare</h2>
              <p style={{ color: "var(--text-secondary)", marginTop: "0.75rem", fontSize: "1rem" }}>Introdu datele contului tau<br />pentru a continua</p>
            </div>

            {error && (
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", padding: "1rem", borderRadius: "0.75rem", marginBottom: "1.5rem", backgroundColor: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.15)" }}>
                <AlertCircle style={{ width: "1rem", height: "1rem", color: "#f87171", flexShrink: 0 }} />
                <p style={{ color: "#f87171", fontSize: "0.875rem", margin: 0 }}>{error}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.5rem", marginBottom: 0 }}>
              <div>
                <label style={labelStyle}>Email</label>
                <div style={{ position: "relative" }}>
                  <Mail style={{ position: "absolute", left: "1rem", top: "50%", transform: "translateY(-50%)", width: "1.25rem", height: "1.25rem", color: "var(--text-muted)", pointerEvents: "none", zIndex: 10 }} />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="email@exemplu.com"
                    required
                    style={inputStyle}
                  />
                </div>
              </div>

              <div>
                <label style={labelStyle}>Parola</label>
                <div style={{ position: "relative" }}>
                  <Lock style={{ position: "absolute", left: "1rem", top: "50%", transform: "translateY(-50%)", width: "1.25rem", height: "1.25rem", color: "var(--text-muted)", pointerEvents: "none", zIndex: 10 }} />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Introdu parola"
                    required
                    style={inputStyle}
                  />
                </div>
              </div>

              <div style={{ paddingTop: "0.5rem" }}>
                <button
                  type="submit"
                  disabled={loading}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.5rem",
                    borderRadius: "0.75rem",
                    color: "var(--text-primary)",
                    fontWeight: 500,
                    fontSize: "0.875rem",
                    border: "none",
                    cursor: loading ? "not-allowed" : "pointer",
                    opacity: loading ? 0.5 : 1,
                    background: "linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)",
                    boxShadow: "0 4px 14px rgba(37, 99, 235, 0.35)",
                    paddingTop: "0.875rem",
                    paddingBottom: "0.875rem",
                    transition: "box-shadow 0.2s",
                  }}
                  onMouseEnter={(e) => {
                    if (!loading) e.currentTarget.style.boxShadow = "0 6px 20px rgba(37, 99, 235, 0.5)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.boxShadow = "0 4px 14px rgba(37, 99, 235, 0.35)";
                  }}
                >
                  {loading ? (
                    <div style={{ width: "1.25rem", height: "1.25rem", border: "2px solid white", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
                  ) : (
                    <>Intra in cont <ArrowRight style={{ width: "1rem", height: "1rem" }} /></>
                  )}
                </button>
              </div>
            </form>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", margin: "2rem 0" }}>
              <div style={{ flex: 1, height: "1px", backgroundColor: "var(--bg-card)" }} />
              <span style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>sau</span>
              <div style={{ flex: 1, height: "1px", backgroundColor: "var(--bg-card)" }} />
            </div>

            <p style={{ textAlign: "center", color: "var(--text-secondary)", fontSize: "1rem" }}>
              Nu ai cont?{" "}
              <Link href="/register" style={{ color: "#60a5fa", fontWeight: 500, textDecoration: "none" }}>
                Creeaza cont gratuit
              </Link>
            </p>

            <p style={{ textAlign: "center", fontSize: "1rem", marginTop: "1rem" }}>
              <Link href="/reset-password" style={{ color: "var(--text-muted)", textDecoration: "none" }}>
                Ai uitat parola?
              </Link>
            </p>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        .login-topbar { display: flex; }
        .login-branding { display: flex; }
        .login-mobile-logo { display: none; }
        .login-grid { grid-template-columns: 1fr 1fr; }
        @media (max-width: 1024px) {
          .login-topbar { display: none; }
          .login-branding { display: none; }
          .login-mobile-logo { display: block; }
          .login-grid { grid-template-columns: 1fr; }
          .login-form-wrap { padding: 1.5rem; }
        }
        @media (min-width: 1024px) {
          .login-form-wrap { padding: 3rem; }
        }
      `}</style>
    </div>
  );
}
