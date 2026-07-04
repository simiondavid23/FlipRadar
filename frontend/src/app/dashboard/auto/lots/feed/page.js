"use client";
import { useState, useEffect, useCallback } from "react";
import { autoLotKeywordsAPI } from "@/lib/api";
import { Car, RefreshCw } from "lucide-react";
import { STATUS_TABS, selectStyle } from "@/lib/uiStyles";
import StatCardsRow from "@/components/shared/StatCardsRow";
import StatusTabsBar from "@/components/shared/StatusTabsBar";
import ScanNowButton from "@/components/shared/ScanNowButton";
import AutoLotCard from "@/components/AutoLotCard";

const PLATFORM_LABELS = { copart: "Copart", iaai: "IAAI", sca: "SCA", openlane: "OpenLane" };

export default function AutoLotsFeedPage() {
  const [lots, setLots] = useState([]);
  const [keywords, setKeywords] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ platform: "", status: "active", keyword_id: "" });
  const [scanning, setScanning] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const loadFeed = useCallback(async () => {
    setLoading(true);
    try {
      const params = { status: filters.status, limit: 100 };
      if (filters.platform) params.platform = filters.platform;
      if (filters.keyword_id) params.keyword_id = filters.keyword_id;
      const r = await autoLotKeywordsAPI.getFeed(params);
      setLots(r.data?.items || []);
    } catch (e) {
      console.error("[AutoLotsFeed]", e);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const loadStats = useCallback(async () => {
    try { const r = await autoLotKeywordsAPI.getStats(); setStats(r.data || {}); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => {
    autoLotKeywordsAPI.getKeywords().then((r) => setKeywords(r.data || [])).catch(() => {});
  }, []);
  useEffect(() => { loadFeed(); loadStats(); }, [loadFeed, loadStats]);

  const setStatus = async (id, status) => {
    setBusyId(id);
    try {
      await autoLotKeywordsAPI.updateStatus(id, status);
      await loadFeed();
      await loadStats();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la actualizare.");
    } finally {
      setBusyId(null);
    }
  };

  const handleScanNow = async () => {
    setScanning(true);
    try {
      await autoLotKeywordsAPI.scanNow();
      // Lasam scannerul de fundal sa lucreze, apoi reimprospatam feed + statistici.
      setTimeout(() => { loadFeed(); loadStats(); setScanning(false); }, 15000);
    } catch {
      setScanning(false);
    }
  };

  const byPlatform = stats.by_platform || {};
  const statCards = [
    { label: "Loturi găsite", value: stats.total_lots ?? 0, color: "#60a5fa" },
    { label: "Keyword-uri active", value: stats.active_keywords ?? 0, color: "#a78bfa" },
    { label: "Copart", value: byPlatform.copart ?? 0, color: "#38bdf8" },
    { label: "IAAI", value: byPlatform.iaai ?? 0, color: "#f87171" },
  ];

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#2563eb", display: "flex" }}>
            <Car style={{ width: "20px", height: "20px", color: "white" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Feed Loturi Auto</h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", margin: 0 }}>Loturi din licitații (Copart / IAAI / SCA / OpenLane), monitorizate pe keyword</p>
          </div>
        </div>
        <ScanNowButton onScan={handleScanNow} scanning={scanning} />
      </div>

      {/* Stats */}
      <StatCardsRow cards={statCards} />

      {/* Filter bar */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.625rem", marginBottom: "1.25rem" }}>
        <StatusTabsBar tabs={STATUS_TABS} active={filters.status} onChange={(v) => setFilters((f) => ({ ...f, status: v }))} />
        <select value={filters.platform} onChange={(e) => setFilters((f) => ({ ...f, platform: e.target.value }))} style={selectStyle}>
          <option value="">Toate platformele</option>
          {Object.entries(PLATFORM_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={filters.keyword_id} onChange={(e) => setFilters((f) => ({ ...f, keyword_id: e.target.value }))} style={selectStyle}>
          <option value="">Toate keyword-urile</option>
          {keywords.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
        </select>
        <button onClick={() => { loadFeed(); loadStats(); }} style={{ ...selectStyle, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.375rem", color: "var(--text-secondary)" }}>
          <RefreshCw style={{ width: "14px", height: "14px" }} /> Reîmprospătează
        </button>
      </div>

      {/* Grid */}
      {loading ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>Se încarcă...</div>
      ) : lots.length === 0 ? (
        <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem", backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem" }}>
          Niciun lot în această categorie. Adaugă keyword-uri și apasă „Scanează acum” sau așteaptă scanarea automată (la 15 min).
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "1rem" }}>
          {lots.map((lot) => (
            <AutoLotCard
              key={lot.id}
              lot={lot}
              isSaved={lot.status === "saved"}
              busy={busyId === lot.id}
              onSave={(l) => setStatus(l.id, "saved")}
              onDelete={(l) => setStatus(l.id, "ignored")}
            />
          ))}
        </div>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
