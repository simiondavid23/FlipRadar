"use client";
import { useState, useEffect, useRef } from "react";
import { Activity, Pause, Play } from "lucide-react";
import { logsAPI, dashboardAPI } from "@/lib/api";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import StatCardsRow from "@/components/shared/StatCardsRow";

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
  return LEVEL_COLORS[level] || { fg: "var(--text-dim)", bg: "rgba(148,163,184,0.15)" };
}

// Cursorul care semnaleaza ca stream-ul SSE e deschis (blink din globals).
function StreamCursor() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "6px 16px 4px" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10.5px", color: "#22d3ee" }}>▍</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: ".1em", color: "var(--text-mono)", animation: "blink 1.6s infinite" }}>
        ASCULT STREAM-UL…
      </span>
    </div>
  );
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
  const dotColor = running ? "#4ade80" : "#f87171";

  return (
    <div className="glass-panel" style={{ padding: "15px 18px", marginTop: "14px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "11px", gap: "10px", flexWrap: "wrap" }}>
        <span style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "13.5px", fontWeight: 600, color: "var(--text-primary)" }}>
          <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: dotColor, boxShadow: `0 0 8px ${dotColor}` }} />
          Status Scheduler{running ? "" : " — oprit"}
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".14em", color: "var(--text-mono)" }}>
          {jobs.length} JOBURI ACTIVE
        </span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "9px" }}>
        {jobs.map((j) => (
          <div
            key={j.id}
            style={{
              minHeight: "52px",
              padding: "9px 12px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              position: "relative",
              background: "rgba(4,9,18,.55)",
              border: "1px solid rgba(94,140,255,.11)",
              borderRadius: "11px",
            }}
          >
            <div
              title={j.name}
              style={{
                fontSize: "12px",
                fontWeight: 500,
                color: "var(--text-primary)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                paddingRight: "14px",
              }}
            >
              {j.name}
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", color: "var(--text-muted)", whiteSpace: "nowrap", marginTop: "3px" }}>
              {_fmtNextRun(j.next_run)}
            </div>
            <div
              style={{
                position: "absolute",
                top: "9px",
                right: "9px",
                width: "5px",
                height: "5px",
                borderRadius: "50%",
                background: dotColor,
                boxShadow: `0 0 6px ${dotColor}`,
              }}
            />
          </div>
        ))}
        {jobs.length === 0 && (
          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Niciun job activ.</span>
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
    <div>
      <TopBar path={["MONITORIZARE", "JURNALE LIVE"]} />

      <PageHeading
        icon={Activity}
        title="Jurnale Live"
        subtitle={<>Flux în timp real al activității scraperelor — <Hl>{visibleLogs.length} linii</Hl> în buffer.</>}
        meta={activeModule ? `${activeModule.toUpperCase()} · STREAM` : null}
      />

      {/* Stats cards */}
      <StatCardsRow cards={statCards.map((c) => ({ ...c, color: "#7ee7f8" }))} />

      {/* Status Scheduler — panou de context deasupra stream-ului */}
      <SchedulerStatusCard />

      {/* Panou tabbed cu stream */}
      <div style={{ marginTop: "12px", borderRadius: "16px", background: "rgba(3,7,14,.82)", backdropFilter: "blur(20px)", border: "1px solid rgba(94,140,255,.13)", boxShadow: "inset 0 1px 0 rgba(255,255,255,.04)", overflow: "hidden" }}>
        {/* Tab-uri module */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", padding: "11px 14px", borderBottom: "1px solid rgba(94,140,255,.1)", background: "rgba(4,9,18,.5)" }}>
          {MODULES.map((m) => {
            const active = activeModule === m.key;
            const modStats = stats[m.key] || {};
            return (
              <button
                key={m.key}
                onClick={() => switchModule(m.key)}
                className={`tab-pill${active ? " active" : ""}`}
                style={{ display: "inline-flex", alignItems: "center", gap: "7px", padding: "6px 14px", fontSize: "11.5px" }}
              >
                {modStats.active && <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#4ade80", boxShadow: "0 0 7px #4ade80" }} />}
                {m.label}
              </button>
            );
          })}
        </div>

        {/* Filtre nivel + auto-scroll */}
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "6px", padding: "10px 14px", borderBottom: "1px solid rgba(94,140,255,.1)" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: ".14em", color: "var(--text-mono)", marginRight: "4px" }}>NIVELE</span>
          {ALL_LEVELS.map((lvl) => {
            const cfg = levelCfg(lvl);
            const hidden = hiddenLevels.has(lvl);
            return (
              <button
                key={lvl}
                onClick={() => toggleLevel(lvl)}
                title={hidden ? "Arată" : "Ascunde"}
                style={{
                  padding: "3px 10px", borderRadius: "99px",
                  fontFamily: "var(--font-mono)", fontSize: "8.5px", fontWeight: 700, letterSpacing: ".08em",
                  cursor: "pointer",
                  border: `1px solid ${cfg.fg}55`,
                  background: hidden ? "transparent" : cfg.bg,
                  color: hidden ? "var(--text-muted)" : cfg.fg,
                  opacity: hidden ? 0.45 : 1,
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
              marginLeft: "auto", padding: "5px 11px", borderRadius: "9px", fontSize: "11px", fontWeight: 600, cursor: "pointer",
              fontFamily: "var(--font-sans)",
              border: `1px solid ${autoScroll ? "rgba(34,211,238,.4)" : "rgba(94,140,255,.16)"}`,
              background: autoScroll ? "rgba(34,211,238,.12)" : "transparent",
              color: autoScroll ? "#7ee7f8" : "var(--text-dim)",
              display: "inline-flex", alignItems: "center", gap: "5px",
            }}
          >
            {autoScroll ? <Pause style={{ width: "11px", height: "11px" }} /> : <Play style={{ width: "11px", height: "11px" }} />}
            Auto-scroll
          </button>
        </div>

        {/* Casuta de loguri */}
        <div
          ref={logBoxRef}
          style={{
            height: "340px", overflowY: "auto",
            fontFamily: "var(--font-mono)",
            fontSize: "10.5px", padding: "12px 0",
            background: "transparent",
          }}
        >
          {visibleLogs.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-mono)", fontSize: "11px", letterSpacing: ".1em" }}>
              Niciun eveniment încă. Logurile apar pe măsură ce scraperele rulează.
            </div>
          ) : (
            visibleLogs.map((e) => {
              const cfg = levelCfg(e.level);
              return (
                <div
                  key={e.id}
                  className="log-row"
                  style={{ display: "flex", alignItems: "baseline", gap: "10px", padding: "3px 16px", lineHeight: 1.5 }}
                >
                  <span style={{ flexShrink: 0, color: "#2b3a5c" }}>{e.id ? new Date(e.id).toLocaleTimeString("ro-RO", { hour12: false }) : e.ts}</span>
                  <span
                    style={{
                      minWidth: "34px", flexShrink: 0, textAlign: "center",
                      color: cfg.fg, fontWeight: 700, fontSize: "8px", letterSpacing: ".08em",
                      background: cfg.bg, borderRadius: "5px", padding: "1.5px 7px",
                    }}
                  >
                    {e.level}
                  </span>
                  <span style={{ flex: 1, wordBreak: "break-word" }}>
                    {parseLogMessage(e.msg).map((part, i) => (
                      <span
                        key={i}
                        style={{
                          color: part.hi ? "#7ee7f8" : "var(--text-tertiary)",
                          fontWeight: part.hi ? 700 : 400,
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
          <StreamCursor />
        </div>
      </div>

      <style>{`
        .log-row:hover { background: rgba(34,211,238,.035); }
        @keyframes blink { 0%, 100% { opacity: 1 } 50% { opacity: .25 } }
      `}</style>
    </div>
  );
}
