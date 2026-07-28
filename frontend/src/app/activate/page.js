"use client";
import { useState, useEffect } from "react";
import { KeyRound, ArrowRight, AlertCircle, Copy, Check, Lock } from "lucide-react";
import { licenseAPI } from "@/lib/api";
import AuthShell, {
  AuthCardHeader, authLabelStyle, authFieldStyle, authInputStyle,
} from "@/components/shared/AuthShell";

// Cheile emise au forma FLIP.<payload>.<semnatura>; acceptam si formatul
// scurt cu cratime din materialele de vanzare, deci validam doar prefixul.
const looksValid = (k) => /^FLIP[.-]\S+/i.test(k.trim());

export default function ActivatePage() {
  const [licenseKey, setLicenseKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // Cat verificam starea licentei nu aratam formularul (evitam un flash inutil).
  const [checking, setChecking] = useState(true);
  // KEY-2 — codul acestui computer (din /status, doar in mod local) + feedback la copiere.
  const [machineCode, setMachineCode] = useState("");
  const [copied, setCopied] = useState(false);

  // La mount: daca nu suntem in mod desktop -> login clasic; daca licenta e deja
  // activa -> sesiune silentioasa + dashboard; altfel afisam formularul de activare.
  useEffect(() => {
    let cancelled = false;
    licenseAPI
      .status()
      .then(async (res) => {
        const data = res.data || {};
        // KEY-2 — codul de masina, de trimis vanzatorului pentru o cheie legata de el.
        if (!cancelled && data.machine_code) setMachineCode(data.machine_code);
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

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(machineCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (_e) {
      // Clipboard indisponibil (context ne-securizat / permisiune refuzata):
      // codul ramane selectabil manual, nu aratam o eroare inutila.
    }
  };

  if (checking) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#04070e" }}>
        <div style={{ width: "2rem", height: "2rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  const formatOk = licenseKey.trim().length > 0 && looksValid(licenseKey);

  return (
    <AuthShell>
      <AuthCardHeader
        title="Activare licență"
        subtitle="Introdu cheia primită la prima activare pe acest computer"
      />

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
          <label style={authLabelStyle}>Cheie de licență</label>
          <div style={authFieldStyle}>
            <KeyRound style={{ width: "14px", height: "14px", color: "#54648a", flexShrink: 0 }} strokeWidth={1.8} />
            <input
              type="text"
              value={licenseKey}
              onChange={(e) => setLicenseKey(e.target.value)}
              placeholder="FLIP-XXXX-XXXX-XXXX"
              autoComplete="off"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              required
              style={{ ...authInputStyle, fontFamily: "var(--font-mono)", letterSpacing: ".12em" }}
            />
          </div>
          {formatOk && (
            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "8px" }}>
              <Check style={{ width: "11px", height: "11px", color: "#4ade80" }} strokeWidth={2.4} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".08em", color: "#4ade80" }}>
                FORMAT VALID · SE VERIFICĂ LA ACTIVARE
              </span>
            </div>
          )}
        </div>

        {machineCode && (
          <div>
            <label style={authLabelStyle}>Codul acestui computer</label>
            <div
              style={{
                display: "flex", alignItems: "center", gap: "10px",
                borderRadius: "11px", background: "rgba(4,9,18,.5)",
                border: "1px solid rgba(94,140,255,.11)", padding: "10px 10px 10px 13px",
              }}
            >
              <code
                style={{
                  flex: 1, fontFamily: "var(--font-mono)", fontSize: "12px",
                  letterSpacing: ".06em", color: "#e6edf9", userSelect: "all", overflowWrap: "anywhere",
                }}
              >
                {machineCode}
              </code>
              <button
                type="button"
                onClick={handleCopy}
                aria-label="Copiază codul acestui computer"
                style={{
                  display: "inline-flex", alignItems: "center", gap: "5px", flexShrink: 0,
                  borderRadius: "9px", border: "1px solid rgba(94,140,255,.16)",
                  background: "transparent", color: copied ? "#4ade80" : "var(--text-dim)",
                  fontFamily: "var(--font-sans)", fontSize: "11px", cursor: "pointer",
                  padding: "5px 10px", transition: "color 0.2s",
                }}
              >
                {copied ? (
                  <><Check style={{ width: "12px", height: "12px" }} strokeWidth={2} /> Copiat</>
                ) : (
                  <><Copy style={{ width: "12px", height: "12px" }} strokeWidth={2} /> Copiază</>
                )}
              </button>
            </div>
            <p style={{ color: "#54648a", fontSize: "11px", lineHeight: 1.5, margin: "8px 0 0" }}>
              Trimite acest cod vânzătorului pentru a primi o cheie de activare legată de acest computer.
            </p>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="btn-auth"
        >
          {loading ? (
            <div style={{ width: "16px", height: "16px", border: "2px solid rgba(34,211,238,.5)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
          ) : (
            <>Activează pe acest computer <ArrowRight style={{ width: "13px", height: "13px" }} strokeWidth={2} /></>
          )}
        </button>

        <div
          style={{
            display: "flex", alignItems: "center", gap: "9px", padding: "10px 13px",
            borderRadius: "11px", background: "rgba(4,9,18,.5)", border: "1px solid rgba(94,140,255,.11)",
          }}
        >
          <Lock style={{ width: "13px", height: "13px", color: "#41547a", flexShrink: 0 }} strokeWidth={1.8} />
          <span style={{ fontSize: "11px", color: "#54648a", lineHeight: 1.5 }}>
            Cheia se leagă de acest computer la prima activare și pornește automat aplicația la următoarele deschideri.
            Verificarea se face local, fără conexiune la internet.
          </span>
        </div>
      </form>
    </AuthShell>
  );
}
