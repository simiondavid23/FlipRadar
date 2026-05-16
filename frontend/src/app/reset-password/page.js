"use client";
import { useState } from "react";
import Link from "next/link";
import { authAPI } from "@/lib/api";
import Image from "next/image";
import { useTheme } from "@/lib/theme";
import { Mail, Lock, ArrowRight, AlertCircle, CheckCircle, KeyRound, HelpCircle, Key, Sun, Moon } from "lucide-react";

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

export default function ResetPasswordPage() {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const { theme } = useTheme();

  const inputStyle = {
    backgroundColor: "var(--bg-dark)",
    border: "1px solid var(--border-color)",
    borderRadius: "0.75rem",
    color: "var(--text-primary)",
    fontSize: "0.875rem",
    width: "100%",
    outline: "none",
    paddingLeft: "3rem",
    paddingRight: "1rem",
    paddingTop: "0.75rem",
    paddingBottom: "0.75rem",
  };
  const labelStyle = { display: "block", fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.5rem", color: "var(--text-secondary)" };
  const iconStyle = { position: "absolute", left: "1rem", top: "50%", transform: "translateY(-50%)", width: "18px", height: "18px", color: "var(--text-secondary)", pointerEvents: "none" };

  const handleFetchQuestion = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await authAPI.getSecurityQuestion(email);
      setQuestion(res.data.security_question);
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.detail || "Nu am gasit un cont pentru acest email.");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (newPassword.length < 6) {
      setError("Parola trebuie sa aiba minim 6 caractere");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Parolele nu coincid");
      return;
    }

    setLoading(true);
    try {
      await authAPI.resetPassword({
        email,
        security_answer: answer,
        new_password: newPassword,
      });
      setSuccess("Parola a fost resetata cu succes! Te poti autentifica acum.");
      setEmail("");
      setAnswer("");
      setNewPassword("");
      setConfirmPassword("");
      setStep(1);
      setQuestion("");
    } catch (err) {
      setError(err.response?.data?.detail || "A aparut o eroare");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", backgroundColor: "var(--bg-dark)" }}>
      <ThemeToggleFloating />
      <div style={{ padding: "1.25rem 2rem" }}>
        <Link href="/login" style={{ display: "inline-flex", alignItems: "center", textDecoration: "none" }}>
          <Image
            src={theme === "light" ? "/flipradar-logo-light.svg" : "/flipradar-logo.svg"}
            alt="FlipRadar"
            width={180}
            height={39}
            priority
            style={{ height: "auto" }}
          />
        </Link>
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "2rem" }}>
        <div style={{ width: "100%", maxWidth: "28rem" }}>
          <div style={{ textAlign: "center", marginBottom: "2rem" }}>
            <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "48px", height: "48px", borderRadius: "12px", backgroundColor: "rgba(37,99,235,0.15)", marginBottom: "1rem" }}>
              <KeyRound style={{ width: "24px", height: "24px", color: "#60a5fa" }} />
            </div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 0.5rem 0" }}>
              Reseteaza parola
            </h1>
            <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
              {step === 1 ? "Introdu adresa de email" : "Raspunde la intrebarea de securitate"}
            </p>
          </div>

          {error && (
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", padding: "0.875rem", borderRadius: "0.75rem", marginBottom: "1.25rem", backgroundColor: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.15)" }}>
              <AlertCircle style={{ width: "16px", height: "16px", color: "#f87171", flexShrink: 0 }} />
              <p style={{ color: "#f87171", fontSize: "0.8125rem", margin: 0 }}>{error}</p>
            </div>
          )}

          {success && (
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", padding: "0.875rem", borderRadius: "0.75rem", marginBottom: "1.25rem", backgroundColor: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.15)" }}>
              <CheckCircle style={{ width: "16px", height: "16px", color: "#4ade80", flexShrink: 0 }} />
              <p style={{ color: "#4ade80", fontSize: "0.8125rem", margin: 0 }}>{success}</p>
            </div>
          )}

          {step === 1 && (
            <form onSubmit={handleFetchQuestion} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              <div>
                <label style={labelStyle}>Email</label>
                <div style={{ position: "relative" }}>
                  <Mail style={iconStyle} />
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email@exemplu.com" required style={inputStyle} />
                </div>
              </div>
              <button type="submit" disabled={loading} style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem", borderRadius: "0.75rem", color: "var(--text-primary)", fontWeight: 500, fontSize: "0.875rem", border: "none", cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.5 : 1, background: "linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)", boxShadow: "0 4px 14px rgba(37,99,235,0.35)", paddingTop: "0.75rem", paddingBottom: "0.75rem" }}>
                {loading ? "Se cauta..." : <>Continua <ArrowRight style={{ width: "16px", height: "16px" }} /></>}
              </button>
            </form>
          )}

          {step === 2 && (
            <form onSubmit={handleReset} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              <div style={{ padding: "0.875rem", borderRadius: "0.75rem", backgroundColor: "rgba(37,99,235,0.08)", border: "1px solid rgba(37,99,235,0.2)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                  <HelpCircle style={{ width: "14px", height: "14px", color: "#60a5fa" }} />
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Intrebare</span>
                </div>
                <p style={{ color: "var(--text-primary)", fontSize: "0.9375rem", margin: 0 }}>{question}</p>
              </div>

              <div>
                <label style={labelStyle}>Raspunsul tau</label>
                <div style={{ position: "relative" }}>
                  <Key style={iconStyle} />
                  <input type="text" value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Introdu raspunsul" required style={inputStyle} />
                </div>
              </div>

              <div>
                <label style={labelStyle}>Parola noua</label>
                <div style={{ position: "relative" }}>
                  <Lock style={iconStyle} />
                  <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Minim 6 caractere" required style={inputStyle} />
                </div>
              </div>

              <div>
                <label style={labelStyle}>Confirma parola noua</label>
                <div style={{ position: "relative" }}>
                  <Lock style={iconStyle} />
                  <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Repeta parola noua" required style={inputStyle} />
                </div>
              </div>

              <div style={{ display: "flex", gap: "0.75rem" }}>
                <button type="button" onClick={() => { setStep(1); setAnswer(""); setNewPassword(""); setConfirmPassword(""); setError(""); }} style={{ flex: 1, borderRadius: "0.75rem", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem", border: "1px solid var(--border-color)", cursor: "pointer", backgroundColor: "transparent", paddingTop: "0.75rem", paddingBottom: "0.75rem" }}>
                  Inapoi
                </button>
                <button type="submit" disabled={loading} style={{ flex: 2, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem", borderRadius: "0.75rem", color: "var(--text-primary)", fontWeight: 500, fontSize: "0.875rem", border: "none", cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.5 : 1, background: "linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)", boxShadow: "0 4px 14px rgba(37,99,235,0.35)", paddingTop: "0.75rem", paddingBottom: "0.75rem" }}>
                  {loading ? "Se proceseaza..." : <>Reseteaza parola <ArrowRight style={{ width: "16px", height: "16px" }} /></>}
                </button>
              </div>
            </form>
          )}

          <div style={{ textAlign: "center", marginTop: "1.5rem" }}>
            <p style={{ fontSize: "0.9375rem", color: "var(--text-secondary)" }}>
              Ti-ai amintit parola?{" "}
              <Link href="/login" style={{ color: "#60a5fa", fontWeight: 500, textDecoration: "none" }}>
                Autentifica-te
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
