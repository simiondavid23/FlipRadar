"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";
import { systemAPI } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
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
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "var(--bg-dark)" }}>
        <div style={{ width: "3rem", height: "3rem", border: "4px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "var(--bg-dark)" }}>
      {/* Header mobil */}
      <div
        style={{
          display: "none",
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          zIndex: 40,
          backgroundColor: "var(--bg-card)",
          borderBottom: "1px solid var(--border-color)",
          padding: "0.75rem 1rem",
          alignItems: "center",
          justifyContent: "space-between",
        }}
        className="mobile-header"
      >
        <span style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>
          FlipRadar{versionInfo ? <span style={{ fontSize: "0.6875rem", fontWeight: 500, color: "var(--text-secondary)", marginLeft: "0.375rem" }}>v{versionInfo.version}</span> : null}
        </span>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          style={{ background: "none", border: "none", color: "var(--text-primary)", cursor: "pointer", padding: "0.25rem" }}
        >
          {mobileMenuOpen ? <X style={{ width: "24px", height: "24px" }} /> : <Menu style={{ width: "24px", height: "24px" }} />}
        </button>
      </div>

      {/* Overlay mobil */}
      {mobileMenuOpen && (
        <div
          onClick={() => setMobileMenuOpen(false)}
          style={{
            position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.5)",
            zIndex: 45, display: "none",
          }}
          className="mobile-overlay"
        />
      )}

      {/* Sidebar */}
      <div className={`sidebar-wrapper ${mobileMenuOpen ? "open" : ""}`}>
        <Sidebar />
      </div>

      {/* Conținut principal */}
      <main className="dashboard-main" style={{ padding: "2rem 2.5rem" }}>
        {/* PKG-UPD — versiune curenta (vizibila pe desktop; pe mobil apare in header) */}
        {versionInfo && (
          <div className="app-version-line">
            <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>v{versionInfo.version}</span>
          </div>
        )}
        {/* PKG-UPD — banner dismissible cand exista o versiune noua */}
        {versionInfo?.update_available && !updateDismissed && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap", marginBottom: "1.25rem", padding: "0.625rem 0.875rem", backgroundColor: "var(--bg-card)", border: "1px solid #facc15", borderRadius: "0.5rem" }}>
            <span style={{ fontSize: "0.8125rem", color: "var(--text-primary)" }}>
              🎉 Versiune nouă disponibilă: <strong>{versionInfo.latest}</strong>
              {versionInfo.url ? (
                <a href={versionInfo.url} target="_blank" rel="noopener noreferrer" style={{ color: "#60a5fa", marginLeft: "0.5rem" }}>Vezi noutățile</a>
              ) : null}
            </span>
            <button onClick={() => setUpdateDismissed(true)} aria-label="Închide" style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: "1.125rem", lineHeight: 1, padding: "0 0.25rem" }}>×</button>
          </div>
        )}
        {children}
      </main>

      <style>{`
        .dashboard-main {
          margin-left: 240px;
        }
        .sidebar-wrapper {
          display: block;
        }
        .mobile-header {
          display: none !important;
        }
        .mobile-overlay {
          display: none !important;
        }
        .app-version-line {
          display: flex;
          justify-content: flex-end;
          margin-bottom: 0.25rem;
        }

        @media (max-width: 768px) {
          .mobile-header {
            display: flex !important;
          }
          .dashboard-main {
            margin-left: 0 !important;
            padding: 1rem !important;
            padding-top: 4rem !important;
          }
          .sidebar-wrapper {
            position: fixed;
            top: 0;
            left: -260px;
            z-index: 50;
            transition: left 0.3s ease;
          }
          .sidebar-wrapper.open {
            left: 0;
          }
          .mobile-overlay {
            display: block !important;
          }
          .app-version-line {
            display: none;
          }
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
