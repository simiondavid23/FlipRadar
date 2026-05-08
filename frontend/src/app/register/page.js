"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { AuthProvider, useAuth } from "@/lib/auth";
import { Mail, Lock, User, ArrowRight, AlertCircle, CheckCircle, TrendingUp, ShieldCheck, Zap, HelpCircle, Key } from "lucide-react";

const SECURITY_QUESTIONS = [
  "Care este numele primului tau animal de companie?",
  "In ce oras te-ai nascut?",
  "Care este numele de fata al mamei tale?",
  "Care a fost numele primei scoli pe care ai urmat-o?",
  "Care este numele celui mai bun prieten din copilarie?",
  "Care a fost marca primei tale masini?",
  "Care este felul tau de mancare preferat?",
  "Care este numele cartii tale preferate?",
];

function RegisterForm() {
  const [formData, setFormData] = useState({
    email: "",
    username: "",
    password: "",
    confirmPassword: "",
    full_name: "",
    security_question: "",
    security_answer: "",
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const router = useRouter();

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (formData.password !== formData.confirmPassword) {
      setError("Parolele nu coincid");
      return;
    }

    if (formData.password.length < 6) {
      setError("Parola trebuie sa aiba minim 6 caractere");
      return;
    }

    if (!formData.security_question.trim() || !formData.security_answer.trim()) {
      setError("Completeaza intrebarea si raspunsul de securitate");
      return;
    }

    setLoading(true);
    try {
      await register({
        email: formData.email,
        username: formData.username,
        password: formData.password,
        full_name: formData.full_name,
        security_question: formData.security_question.trim(),
        security_answer: formData.security_answer.trim(),
      });
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2000);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (typeof detail === "string") {
        setError(detail);
      } else if (Array.isArray(detail)) {
        setError(detail.map((d) => d.msg).join(", "));
      } else {
        setError("Eroare la inregistrare");
      }
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    width: "100%",
    borderRadius: "0.75rem",
    color: "white",
    fontSize: "0.875rem",
    backgroundColor: "#0f172a",
    border: "1px solid #334155",
    paddingLeft: "3rem",
    paddingRight: "1rem",
    paddingTop: "0.75rem",
    paddingBottom: "0.75rem",
    outline: "none",
  };
  const labelStyle = { display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.625rem", color: "#94a3b8" };
  const iconStyle = { position: "absolute", left: "1rem", top: "50%", transform: "translateY(-50%)", width: "1.25rem", height: "1.25rem", color: "#64748b", pointerEvents: "none", zIndex: 10 };

  const renderInput = (name, type, placeholder, Icon, required = true) => (
    <div>
      <label style={labelStyle}>{placeholder.label}</label>
      <div style={{ position: "relative" }}>
        <Icon style={iconStyle} />
        <input
          type={type}
          name={name}
          value={formData[name]}
          onChange={handleChange}
          placeholder={placeholder.ph}
          required={required}
          style={inputStyle}
        />
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", backgroundColor: "#0f172a" }}>
      <div className="register-topbar" style={{ alignItems: "center", padding: "1.5rem", position: "relative", zIndex: 10 }}>
        <Image
          src="/flipradar-logo.svg"
          alt="FlipRadar"
          width={200}
          height={44}
          priority
          style={{ height: "auto" }}
        />
      </div>

      <div className="register-grid" style={{ flex: 1, display: "grid", alignItems: "center" }}>
        <div className="register-branding" style={{ flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "3rem", position: "relative", overflow: "hidden" }}>
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
            <h1 style={{ fontSize: "2.25rem", fontWeight: 700, color: "white", lineHeight: 1.2 }}>
              Descopera produse <span style={{ color: "#60a5fa" }}>profitabile</span> pentru revanzare
            </h1>
            <p style={{ color: "#94a3b8", fontSize: "1.125rem" }}>
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
                  <span style={{ color: "#cbd5e1", fontSize: "0.875rem", textAlign: "left" }}>{text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="register-form-wrap" style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem" }}>
          <div style={{ width: "100%", maxWidth: "28rem" }}>
            <div className="register-mobile-logo" style={{ textAlign: "center", marginBottom: "2rem" }}>
              <Image
                src="/flipradar-icon.svg"
                alt=""
                width={56}
                height={56}
                priority
                style={{ marginBottom: "0.75rem" }}
              />
              <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white" }}>FlipRadar</h1>
            </div>

            <div style={{ marginBottom: "2.5rem", textAlign: "center" }}>
              <h2 style={{ fontSize: "1.875rem", fontWeight: 600, color: "white" }}>Creeaza cont</h2>
              <p style={{ color: "#94a3b8", marginTop: "0.75rem", fontSize: "1rem" }}>Completeaza formularul<br />pentru a incepe</p>
            </div>

            {error && (
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", padding: "1rem", borderRadius: "0.75rem", marginBottom: "1.5rem", backgroundColor: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.15)" }}>
                <AlertCircle style={{ width: "1rem", height: "1rem", color: "#f87171", flexShrink: 0 }} />
                <p style={{ color: "#f87171", fontSize: "0.875rem", margin: 0 }}>{error}</p>
              </div>
            )}

            {success && (
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", padding: "1rem", borderRadius: "0.75rem", marginBottom: "1.5rem", backgroundColor: "rgba(34, 197, 94, 0.08)", border: "1px solid rgba(34, 197, 94, 0.15)" }}>
                <CheckCircle style={{ width: "1rem", height: "1rem", color: "#4ade80", flexShrink: 0 }} />
                <p style={{ color: "#4ade80", fontSize: "0.875rem", margin: 0 }}>Cont creat cu succes! Redirectionare...</p>
              </div>
            )}

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                {renderInput("full_name", "text", { label: "Nume complet", ph: "Ion Popescu" }, User, false)}
                {renderInput("username", "text", { label: "Username", ph: "ionpopescu" }, User)}
              </div>

              {renderInput("email", "email", { label: "Email", ph: "email@exemplu.com" }, Mail)}
              {renderInput("password", "password", { label: "Parola", ph: "Minim 6 caractere" }, Lock)}
              {renderInput("confirmPassword", "password", { label: "Confirma parola", ph: "Repeta parola" }, Lock)}

              <div>
                <label style={labelStyle}>Intrebare de securitate</label>
                <div style={{ position: "relative" }}>
                  <HelpCircle style={iconStyle} />
                  <select
                    name="security_question"
                    value={formData.security_question}
                    onChange={handleChange}
                    required
                    style={{
                      ...inputStyle,
                      appearance: "none",
                      cursor: "pointer",
                      paddingRight: "2.5rem",
                    }}
                  >
                    <option value="" disabled>Alege o intrebare...</option>
                    {SECURITY_QUESTIONS.map((q) => (
                      <option key={q} value={q}>{q}</option>
                    ))}
                  </select>
                </div>
              </div>

              {renderInput("security_answer", "text", { label: "Raspuns de securitate", ph: "Raspunsul tau (folosit la resetarea parolei)" }, Key)}

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
                  color: "white",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  border: "none",
                  cursor: loading ? "not-allowed" : "pointer",
                  opacity: loading ? 0.5 : 1,
                  marginTop: "0.5rem",
                  background: "linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)",
                  boxShadow: "0 4px 14px rgba(37, 99, 235, 0.35)",
                  paddingTop: "0.75rem",
                  paddingBottom: "0.75rem",
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
                  <>Creeaza cont <ArrowRight style={{ width: "1rem", height: "1rem" }} /></>
                )}
              </button>
            </form>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", margin: "2rem 0" }}>
              <div style={{ flex: 1, height: "1px", backgroundColor: "#1e293b" }} />
              <span style={{ fontSize: "0.875rem", color: "#64748b" }}>sau</span>
              <div style={{ flex: 1, height: "1px", backgroundColor: "#1e293b" }} />
            </div>

            <p style={{ textAlign: "center", color: "#94a3b8", fontSize: "1rem" }}>
              Ai deja cont?{" "}
              <Link href="/login" style={{ color: "#60a5fa", fontWeight: 500, textDecoration: "none" }}>
                Autentifica-te
              </Link>
            </p>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        .register-topbar { display: flex; }
        .register-branding { display: flex; }
        .register-mobile-logo { display: none; }
        .register-grid { grid-template-columns: 1fr 1fr; }
        @media (max-width: 1024px) {
          .register-topbar { display: none; }
          .register-branding { display: none; }
          .register-mobile-logo { display: block; }
          .register-grid { grid-template-columns: 1fr; }
          .register-form-wrap { padding: 1.5rem; }
        }
        @media (min-width: 1024px) {
          .register-form-wrap { padding: 3rem; }
        }
      `}</style>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <AuthProvider>
      <RegisterForm />
    </AuthProvider>
  );
}
