"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";

function AdminContent({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    } else if (!loading && user && !user.is_admin) {
      router.push("/dashboard");
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "var(--bg-dark)" }}>
        <div style={{ width: "3rem", height: "3rem", border: "4px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  if (!user || !user.is_admin) return null;

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "var(--bg-dark)", padding: "2rem" }}>
      {children}
    </div>
  );
}

export default function AdminLayout({ children }) {
  return (
    <AuthProvider>
      <AdminContent>{children}</AdminContent>
    </AuthProvider>
  );
}
