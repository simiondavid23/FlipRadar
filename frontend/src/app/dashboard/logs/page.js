"use client";
import { useState, useEffect, useRef } from "react";
import { Activity, Pause, Play } from "lucide-react";
import { logsAPI, dashboardAPI } from "@/lib/api";

// EventSource se conecteaza direct la backend (alt origin decat Next),
// folosind acelasi base URL ca instanta axios.
const API_BASE = process.env.NEXT_PUBLIC_API_URL
  || (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

const MODULES = [
  { key: "radar", label: "Radar Piață" },
  { key: "catalog", label: "Catalog" },
  { key: "auto_lots", label: "Auto Loturi" },
  { key: "auto_listings", label: "Auto Anunțuri" },
  { key: "real_estate", label: "Imobiliare" },
];

const LEVEL_COLORS = {
  OK: { fg: "#4ade80", bg: "rgba(34,197,94,0.15)" },
  ERR: { fg: "#f87171", bg: "rgba(239,68,68,0.15)" },
  WARN: { fg: "#fbbf24", bg: "rgba(245,158,11,0.15)" },
  INFO: { fg: "#60a5fa", bg: "rgba(37,99,235,0.15)" },
  SCAN: { fg: "#a78bfa", bg: "rgba(139,92,246,0.15)" },
  NOTIF: { fg: "#f472b6", bg: "rgba(236,72,153,0.15)" },
  AI: { fg: "#a78bfa", bg: "rgba(139,92,246,0.15)" },
  CLEAN: { fg: "#fbbf24", bg: "rgba(245,158,11,0.15)" },
};
const ALL_LEVELS = ["OK", "ERR", "WARN", "INFO", "SCAN", "NOTIF", "AI", "CLEAN"];

function levelCfg(level) {
  return LEVEL_COLORS[level] || { fg: "var(--text-secondary)", bg: "rgba(148,163,184,0.15)" };
}

// Evidentiaza in mesaj: "siruri citate", numere (48, 34%, 2300) si
// intervale orare (08:00–22:00). Intoarce segmente {text, hi}.
function parseLogMessage(text) {
  const PATTERN = /("(?:[^"\\]|\\.)*?"|\b\d{1,2}:\d{2}(?:[–-]\d{1,2}:\d{2})?|\b\d+(?:[.,]\d+)?%?\b)/g;
  const parts = [];
  let last = 0;
  let match;
  const src = String(text ?? "");
  while ((match = PATTERN.exec(src)) !== null) {
    if (match.index > last) {
      parts.push({ text: src.slice(last, match.index), hi: false });
    }
    parts.push({ text: match[0], hi: true });
    last = match.index + match[0].length;
  }
  if (last < src.length) {
    parts.push({ text: src.slice(last), hi: false });
  }
  return parts;
}

// MODIFICARE — Status Scheduler (mutat din Dashboard) afișat ca panou de context
// deasupra stream-ului de log-uri. Carduri uniforme (înălțime fixă, text trunchiat).
function _fmtNextRun(iso) {
  if (!iso) return "—";
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) return "acum";
  const mins = Math.round(diffMs / 60000);
  if (mins < 60) return `peste ${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m > 0 ? `peste ${h}h ${m}min` : `peste ${h}h`;
}

function SchedulerStatusCard() {
  const [data, setData] = useState(null);
  const [, setTick] = useState(0); // re-render periodic pentru recalcularea timpilor

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await dashboardAPI.getSchedulerStatus();
        if (!cancelled) setData(r.data);
      } catch {
        /* ignoram erorile — widget-ul e informativ */
      }
    };
    load();
    const id = setInterval(() => { load(); setTick((t) => t + 1); }, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (!data) return null;
  const running = data.scheduler_running;
  const jobs = data.jobs || [];
  // Variabilele spec (--fill-success/--fill-danger) au fallback pe paleta reală a app-ului.
  const dotColor = running ? "var(--fill-success, #4ade80)" : "var(--fill-danger, #ef4444)";

  return (
    <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem", marginBottom: "1.25rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
        <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: dotColor }} />
        <h2 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
          Status Scheduler{running ? "" : " — oprit"}
        </h2>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "8px" }}>
        {jobs.map((j) => (
          <div
            key={j.id}
            style={{
              minHeight: "56px",
              padding: "0.5rem 0.75rem",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              position: "relative",
              background: "var(--surface-1, var(--bg-dark))",
              border: "0.5px solid var(--border, var(--border-color))",
              borderRadius: "var(--radius, var(--radius-md, 8px))",
            }}
          >
            <div
              title={j.name}
              style={{
                fontSize: "13px",
                fontWeight: 500,
                color: "var(--text-primary)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                paddingRight: "16px",
              }}
            >
              {j.name}
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-secondary)", whiteSpace: "nowrap", marginTop: "2px" }}>
              {_fmtNextRun(j.next_run)}
            </div>
            <div
              style={{
                position: "absolute",
                top: "8px",
                right: "8px",
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: dotColor,
              }}
            />
          </div>
        ))}
        {jobs.length === 0 && (
          <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>Niciun job activ.</span>
        )}
      </div>
    </div>
  );
}

export default function LogsPage() {
  const [activeModule, setActiveModule] = useState("radar");
  const [logs, setLogs] = useState([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [hiddenLevels, setHiddenLevels] = useState(new Set());
  const [stats, setStats] = useState({});
  const logBoxRef = useRef(null);

  // SSE stream — se redeschide cand se schimba modulul activ.
  useEffect(() => {
    // MODIFICARE 3 — EventSource trimite automat cookie-ul httpOnly de sesiune
    // (withCredentials); backend-ul citește token-ul din cookie.
    const url = `${API_BASE}/api/logs/stream?module=${activeModule}`;
    // Reconectare automata: la eroare (ex. restart backend) inchidem si reincercam
    // dupa 4s, cat timp efectul nu a fost curatat (schimbare modul / unmount).
    let cancelled = false, es = null, timer = null;
    const connect = () => {
      es = new EventSource(url, { withCredentials: true });
      es.onmessage = (event) => {
        try {
          const entry = JSON.parse(event.data);
          setLogs((prev) => [...prev, entry].slice(-500));
        } catch {
          /* ignora liniile invalide */
        }
      };
      es.onerror = () => { es.close(); if (!cancelled) timer = setTimeout(connect, 4000); };
    };
    connect();
    return () => { cancelled = true; clearTimeout(timer); es?.close(); };
  }, [activeModule]);

  // Auto-scroll cand sosesc loguri noi.
  useEffect(() => {
    if (autoScroll && logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // Polling statistici la 15s.
  useEffect(() => {
    let cancelled = false;
    const fetchStats = async () => {
      try {
        const r = await logsAPI.getLogs();
        if (!cancelled) setStats(r.data || {});
      } catch {
        /* ignora */
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const switchModule = (key) => {
    setActiveModule(key);
    setLogs([]); // bufferul vine imediat prin SSE la reconectare
  };

  const toggleLevel = (level) => {
    setHiddenLevels((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  };

  const visibleLogs = logs.filter((e) => !hiddenLevels.has(e.level));

  const totals = stats.__totals__ || {};
  const statCards = [
    { label: "Listinguri noi (60 min)", value: totals.new_listings_hour ?? 0 },
    { label: "Evenimente azi", value: totals.events_today ?? 0 },
    { label: "Module active", value: `${totals.active_modules ?? 0} / ${MODULES.length}` },
  ];

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Activity style={{ width: "22px", height: "22px", color: "#2563eb" }} />
          Jurnale Live
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
          Flux în timp real al activității scraperelor (SSE)
        </p>
      </div>

      {/* Stats cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.875rem", marginBottom: "1.25rem" }}>
        {statCards.map((c) => (
          <div key={c.label} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem" }}>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>{c.value}</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.125rem" }}>{c.label}</div>
          </div>
        ))}
      </div>

      {/* Status Scheduler — panou de context deasupra stream-ului */}
      <SchedulerStatusCard />

      {/* Panou tabbed cu stream */}
      <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", overflow: "hidden" }}>
        {/* Tab-uri module */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", padding: "0.75rem 0.875rem", borderBottom: "1px solid var(--border-color)" }}>
          {MODULES.map((m) => {
            const active = activeModule === m.key;
            const modStats = stats[m.key] || {};
            return (
              <button
                key={m.key}
                onClick={() => switchModule(m.key)}
                style={{
                  padding: "0.375rem 0.875rem", borderRadius: "999px", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
                  border: `1px solid ${active ? "rgba(37,99,235,0.3)" : "var(--border-color)"}`,
                  backgroundColor: active ? "rgba(37,99,235,0.15)" : "transparent",
                  color: active ? "#60a5fa" : "var(--text-secondary)",
                  display: "inline-flex", alignItems: "center", gap: "0.375rem",
                }}
              >
                {modStats.active && <span style={{ width: "7px", height: "7px", borderRadius: "50%", backgroundColor: "#4ade80" }} />}
                {m.label}
              </button>
            );
          })}
        </div>

        {/* Filtre nivel + auto-scroll */}
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.375rem", padding: "0.625rem 0.875rem", borderBottom: "1px solid var(--border-color)" }}>
          {ALL_LEVELS.map((lvl) => {
            const cfg = levelCfg(lvl);
            const hidden = hiddenLevels.has(lvl);
            return (
              <button
                key={lvl}
                onClick={() => toggleLevel(lvl)}
                title={hidden ? "Arată" : "Ascunde"}
                style={{
                  padding: "0.125rem 0.5rem", borderRadius: "0.375rem", fontSize: "0.6875rem", fontWeight: 700, cursor: "pointer",
                  border: `1px solid ${cfg.fg}55`,
                  backgroundColor: hidden ? "transparent" : cfg.bg,
                  color: hidden ? "var(--text-muted)" : cfg.fg,
                  opacity: hidden ? 0.5 : 1,
                  textDecoration: hidden ? "line-through" : "none",
                }}
              >
                {lvl}
              </button>
            );
          })}
          <button
            onClick={() => setAutoScroll((v) => !v)}
            style={{
              marginLeft: "auto", padding: "0.25rem 0.625rem", borderRadius: "0.375rem", fontSize: "0.75rem", fontWeight: 600, cursor: "pointer",
              border: "1px solid var(--border-color)",
              backgroundColor: autoScroll ? "rgba(37,99,235,0.15)" : "var(--bg-dark)",
              color: autoScroll ? "#60a5fa" : "var(--text-secondary)",
              display: "inline-flex", alignItems: "center", gap: "0.25rem",
            }}
          >
            {autoScroll ? <Pause style={{ width: "12px", height: "12px" }} /> : <Play style={{ width: "12px", height: "12px" }} />}
            Auto-scroll
          </button>
        </div>

        {/* Casuta de loguri */}
        <div
          ref={logBoxRef}
          style={{
            height: "320px", overflowY: "auto",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            fontSize: "0.75rem", padding: "0.5rem 0",
            backgroundColor: "var(--bg-dark)",
          }}
        >
          {visibleLogs.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.8125rem" }}>
              Niciun eveniment încă. Logurile apar pe măsură ce scraperele rulează.
            </div>
          ) : (
            visibleLogs.map((e) => {
              const cfg = levelCfg(e.level);
              return (
                <div
                  key={e.id}
                  className="log-row"
                  style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", padding: "0.1875rem 0.875rem", lineHeight: 1.45 }}
                >
                  <span style={{ width: "68px", flexShrink: 0, color: "var(--text-muted)" }}>{e.id ? new Date(e.id).toLocaleTimeString("ro-RO", { hour12: false }) : e.ts}</span>
                  <span
                    style={{
                      width: "38px", flexShrink: 0, textAlign: "center",
                      color: cfg.fg, fontWeight: 700, fontSize: "0.625rem",
                      backgroundColor: cfg.bg, borderRadius: "0.25rem", padding: "0.0625rem 0",
                    }}
                  >
                    {e.level}
                  </span>
                  <span style={{ flex: 1, wordBreak: "break-word" }}>
                    {parseLogMessage(e.msg).map((part, i) => (
                      <span
                        key={i}
                        style={{
                          color: part.hi ? "var(--text-primary)" : "var(--text-secondary)",
                          fontWeight: part.hi ? 500 : 400,
                        }}
                      >
                        {part.text}
                      </span>
                    ))}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>

      <style>{`.log-row:hover { background-color: var(--bg-card); }`}</style>
    </div>
  );
}
