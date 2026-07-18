"use client";
import { useState, useEffect } from "react";
import Image from "next/image";
import { KeyRound, ArrowRight, AlertCircle, TrendingUp, ShieldCheck, Zap } from "lucide-react";
import { licenseAPI } from "@/lib/api";

export default function ActivatePage() {
  const [licenseKey, setLicenseKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // Cat verificam starea licentei nu aratam formularul (evitam un flash inutil).
  const [checking, setChecking] = useState(true);

  // La mount: daca nu suntem in mod desktop -> login clasic; daca licenta e deja
  // activa -> sesiune silentioasa + dashboard; altfel afisam formularul de activare.
  useEffect(() => {
    let cancelled = false;
    licenseAPI
      .status()
      .then(async (res) => {
        const data = res.data || {};
        if (!data.local_mode) {
          window.location.href = "/login";
          return;
        }
        if (data.activated) {
          try {
            await licenseAPI.session();
            window.location.href = "/dashboard";
            return;
          } catch (_e) {
            // Licenta prezenta dar invalida intre timp — ramanem pe formular.
          }
        }
        if (!cancelled) setChecking(false);
      })
      .catch(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await licenseAPI.activate(licenseKey.trim());
      window.location.href = "/dashboard";
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Cheie de activare invalidă.");
      setLoading(false);
    }
  };

  const inputStyle = {
    width: "100%",
    borderRadius: "0.75rem",
    color: "var(--text-primary)",
    fontSize: "0.875rem",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    backgroundColor: "var(--bg-dark)",
    border: "1px solid var(--border-color)",
    paddingLeft: "3rem",
    paddingRight: "1rem",
    paddingTop: "0.75rem",
    paddingBottom: "0.75rem",
    outline: "none",
  };

  const labelStyle = { display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.625rem", color: "var(--text-secondary)" };

  if (checking) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "var(--bg-dark)" }}>
        <div style={{ width: "2rem", height: "2rem", border: "3px solid var(--border-color)", borderTopColor: "#60a5fa", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", backgroundColor: "var(--bg-dark)" }}>
      <div className="login-topbar" style={{ alignItems: "center", padding: "1.5rem", position: "relative", zIndex: 10 }}>
        <Image
          src="/flipradar-logo.svg"
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
              Activează-ți <span style={{ color: "#60a5fa" }}>licența</span> FlipRadar
            </h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "1.125rem" }}>
              O singură activare pe acest calculator. După ce introduci cheia, aplicația pornește automat la fiecare deschidere.
            </p>
            <div style={{ alignSelf: "center", display: "inline-flex", flexDirection: "column", gap: "0.75rem", paddingTop: "1rem" }}>
              {[
                { icon: TrendingUp, text: "Analiza automata a profitabilitatii" },
                { icon: Zap, text: "Alerte in timp real pentru oportunitati" },
                { icon: ShieldCheck, text: "Verificare offline, fara cont online" },
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
              <h2 style={{ fontSize: "1.875rem", fontWeight: 600, color: "var(--text-primary)" }}>Activare</h2>
              <p style={{ color: "var(--text-secondary)", marginTop: "0.75rem", fontSize: "1rem" }}>Lipește cheia de activare<br />primită de la furnizor</p>
            </div>

            {error && (
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", padding: "1rem", borderRadius: "0.75rem", marginBottom: "1.5rem", backgroundColor: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.15)" }}>
                <AlertCircle style={{ width: "1rem", height: "1rem", color: "#f87171", flexShrink: 0 }} />
                <p style={{ color: "#f87171", fontSize: "0.875rem", margin: 0 }}>{error}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.5rem", marginBottom: 0 }}>
              <div>
                <label style={labelStyle}>Cheie de activare</label>
                <div style={{ position: "relative" }}>
                  <KeyRound style={{ position: "absolute", left: "1rem", top: "50%", transform: "translateY(-50%)", width: "1.25rem", height: "1.25rem", color: "var(--text-muted)", pointerEvents: "none", zIndex: 10 }} />
                  <input
                    type="text"
                    value={licenseKey}
                    onChange={(e) => setLicenseKey(e.target.value)}
                    placeholder="FLIP.…"
                    autoComplete="off"
                    autoCapitalize="off"
                    autoCorrect="off"
                    spellCheck={false}
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
                    <>Activează <ArrowRight style={{ width: "1rem", height: "1rem" }} /></>
                  )}
                </button>
              </div>
            </form>

            <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem", marginTop: "2rem", lineHeight: 1.6 }}>
              Cheia se primește de la furnizor și se lipește o singură dată. Verificarea se face local, fără conexiune la internet.
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
