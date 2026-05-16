"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";
import Sidebar from "@/components/Sidebar";
import { Menu, X } from "lucide-react";

function DashboardContent({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [prevPathname, setPrevPathname] = useState(pathname);

  // Inchide meniul mobil cand se schimba ruta — pattern "compute during render"
  // ca sa evitam un useEffect care declanseaza re-render in cascada.
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    setMobileMenuOpen(false);
  }

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    } else if (!loading && user && user.is_admin) {
      router.push("/admin");
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "var(--bg-dark)" }}>
        <div style={{ width: "3rem", height: "3rem", border: "4px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  if (!user || user.is_admin) return null;

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "var(--bg-dark)" }}>
      {/* Mobile header */}
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
        <span style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>FlipRadar</span>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          style={{ background: "none", border: "none", color: "var(--text-primary)", cursor: "pointer", padding: "0.25rem" }}
        >
          {mobileMenuOpen ? <X style={{ width: "24px", height: "24px" }} /> : <Menu style={{ width: "24px", height: "24px" }} />}
        </button>
      </div>

      {/* Mobile overlay */}
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

      {/* Main content */}
      <main className="dashboard-main" style={{ padding: "2rem 2.5rem" }}>
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
