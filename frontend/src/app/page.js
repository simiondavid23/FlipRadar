"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL
  || (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

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
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(4,9,18,.45)" }}>
      <div style={{ width: "3rem", height: "3rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }}></div>
    </div>
  );
}