"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";
import { systemAPI } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import ModuleTabs from "@/components/ModuleTabs";
import { Menu, X } from "lucide-react";

function DashboardContent({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [prevPathname, setPrevPathname] = useState(pathname);
  // PKG-UPD — versiune + banner "versiune noua disponibila".
  const [versionInfo, setVersionInfo] = useState(null);
  const [updateDismissed, setUpdateDismissed] = useState(false);

  // Inchide meniul mobil cand se schimba ruta — pattern "compute during render"
  // ca sa evitam un useEffect care declanseaza re-render in cascada.
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    setMobileMenuOpen(false);
  }

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [user, loading, router]);

  // PKG-UPD — verificare versiune la mount; erorile se ignora silentios.
  useEffect(() => {
    systemAPI.getVersion().then((r) => setVersionInfo(r.data)).catch(() => {});
  }, []);

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-dark)" }}>
        <div style={{ width: "3rem", height: "3rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: "var(--bg-dark)" }}>
      {/* Fundal global — grila, glow-uri ambientale, linia de accent de sus */}
      <div className="fx-grid" aria-hidden="true" />
      <div className="fx-glow-top" aria-hidden="true" />
      <div className="fx-glow-bottom" aria-hidden="true" />
      <div className="fx-topline" aria-hidden="true" />

      {/* Header mobil */}
      <div className="mobile-header">
        <span style={{ fontSize: "14.5px", fontWeight: 700, color: "var(--text-primary)" }}>
          Flip<span style={{ color: "#7ee7f8" }}>Radar</span>
          {versionInfo ? (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", color: "var(--text-mono)", marginLeft: "8px" }}>
              v{versionInfo.version}
            </span>
          ) : null}
        </span>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Meniu"
          style={{ background: "none", border: "none", color: "var(--text-primary)", cursor: "pointer", padding: "0.25rem" }}
        >
          {mobileMenuOpen ? <X style={{ width: "22px", height: "22px" }} /> : <Menu style={{ width: "22px", height: "22px" }} />}
        </button>
      </div>

      {/* Overlay mobil */}
      {mobileMenuOpen && (
        <div onClick={() => setMobileMenuOpen(false)} className="mobile-overlay" />
      )}

      {/* Sidebar */}
      <div className={`sidebar-wrapper ${mobileMenuOpen ? "open" : ""}`}>
        <Sidebar />
      </div>

      {/* Conținut principal */}
      <main className="dashboard-main">
        {/* PKG-UPD — versiune curenta (vizibila pe desktop; pe mobil apare in header) */}
        {versionInfo && (
          <div className="app-version-line">
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".12em", color: "var(--text-faint)" }}>
              V{versionInfo.version}
            </span>
          </div>
        )}
        {/* PKG-UPD — banner dismissible cand exista o versiune noua */}
        {versionInfo?.update_available && !updateDismissed && (
          <div
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem",
              flexWrap: "wrap", marginBottom: "14px", padding: "10px 14px", borderRadius: "12px",
              background: "linear-gradient(rgba(8,14,27,.72),rgba(8,14,27,.72)) padding-box, linear-gradient(135deg, rgba(253,224,71,.4), rgba(253,224,71,.06) 55%, transparent) border-box",
              border: "1px solid transparent", backdropFilter: "blur(20px)",
            }}
          >
            <span style={{ fontSize: "12.5px", color: "var(--text-secondary)" }}>
              Versiune nouă disponibilă: <strong style={{ color: "#fde047" }}>{versionInfo.latest}</strong>
              {versionInfo.url ? (
                <a href={versionInfo.url} target="_blank" rel="noopener noreferrer" style={{ marginLeft: "8px" }}>Vezi noutățile</a>
              ) : null}
            </span>
            <button
              onClick={() => setUpdateDismissed(true)}
              aria-label="Închide"
              style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: "1.125rem", lineHeight: 1, padding: "0 0.25rem" }}
            >
              ×
            </button>
          </div>
        )}
        <ModuleTabs />
        {children}
      </main>

      <style>{`
        .dashboard-main {
          position: relative;
          z-index: 1;
          margin-left: 274px;
          padding: 18px 26px 34px;
        }
        .sidebar-wrapper { display: block; }
        .mobile-header {
          display: none;
          position: fixed;
          top: 0; left: 0; right: 0;
          z-index: 40;
          background: rgba(8,14,27,.82);
          backdrop-filter: blur(20px);
          border-bottom: 1px solid rgba(94,140,255,.13);
          padding: 0.75rem 1rem;
          align-items: center;
          justify-content: space-between;
        }
        .mobile-overlay {
          display: none;
          position: fixed;
          inset: 0;
          background: rgba(2,5,12,.6);
          backdrop-filter: blur(3px);
          z-index: 45;
        }
        .app-version-line {
          display: flex;
          justify-content: flex-end;
          margin-bottom: 2px;
        }

        @media (max-width: 900px) {
          .mobile-header { display: flex; }
          .mobile-overlay { display: block; }
          .dashboard-main {
            margin-left: 0;
            padding: 4rem 1rem 2rem;
          }
          .sidebar-wrapper .app-sidebar {
            left: -280px;
            transition: left 0.3s ease;
          }
          .sidebar-wrapper.open .app-sidebar {
            left: 18px;
          }
          .app-version-line { display: none; }
        }
      `}</style>
    </div>
  );
}

export default function DashboardLayout({ children }) {
  return (
    <AuthProvider>
      <DashboardContent>{children}</DashboardContent>
    </AuthProvider>
  );
}
