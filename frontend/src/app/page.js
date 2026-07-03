"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    // MODIFICARE 3 — cookie-ul de sesiune e httpOnly și nu poate fi citit din JS;
    // verificăm sesiunea printr-un apel /me (cookie-ul pleacă automat).
    axios
      .get(API_URL + "/api/auth/me", { withCredentials: true })
      .then(() => router.push("/dashboard"))
      .catch(() => router.push("/login"));
  }, [router]);

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "var(--bg-dark)" }}>
      <div style={{ width: "3rem", height: "3rem", border: "4px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }}></div>
    </div>
  );
}