"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { radarAPI, usersAPI, facebookGroupsAPI } from "@/lib/api";
import {
  Settings as SettingsIcon, Radar, Save, Send, ToggleLeft, ToggleRight,
  CheckCircle2, AlertCircle, Activity,
  BellRing, BellOff, Link as LinkIcon, Sparkles, FileText, MessageCircle, FileBarChart,
  Users, Plus, Pencil, Trash2, RefreshCw, X, ExternalLink, Play, AlertTriangle, Clock
} from "lucide-react";
import {
  isPushSupported, registerPushNotifications, unregisterPushNotifications
} from "@/lib/push";

const EMPTY_PROXY = { enabled: false, host: "", port: "", username: "", password: "", password_set: false };

const NAV_SECTIONS = [
  { id: "radar", label: "Setări Radar", icon: Radar },
  { id: "ai_features", label: "Funcționalități AI", icon: Sparkles },
];

const AI_FEATURES = [
  {
    key: "ai_radar_review",
    label: "Review AI în feed",
    description: "Generează automat o analiză AI pentru fiecare anunț deschis în Radar Piată. Implică un apel la API-ul Groq.",
    icon: Sparkles,
  },
  {
    key: "ai_listing_creator",
    label: "Creator Anunțuri",
    description: "Generează descrieri optimizate pentru OLX, Vinted sau Facebook Marketplace pe baza detaliilor produsului.",
    icon: FileText,
  },
  {
    key: "ai_advisor",
    label: "Consilier AI",
    description: "Analizează produse și oportunități de revânzare cu ajutorul inteligenței artificiale.",
    icon: Sparkles,
  },
  {
    key: "ai_support",
    label: "Asistent AI",
    description: "Chat cu un asistent specializat în comerț online și arbitraj de produse.",
    icon: MessageCircle,
  },
  {
    key: "ai_report",
    label: "Raport Piată",
    description: "Generează rapoarte detaliate despre tendințele pieței pe baza datelor colectate.",
    icon: FileBarChart,
  },
];

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState("radar");

  // ── Radar settings state (copiat din vechea pagina /dashboard/radar/settings) ──
  const [settings, setSettings] = useState(null);
  const [stats, setStats] = useState(null);
  const [fbStatus, setFbStatus] = useState({ valid: false });
  const [proxy, setProxy] = useState(EMPTY_PROXY);
  const [pushStatus, setPushStatus] = useState({ subscribed: false, configured: false });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [lajumateTestResult, setLajumateTestResult] = useState(null);
  const [testingLajumate, setTestingLajumate] = useState(false);
  const [okaziiTestResult, setOkaziiTestResult] = useState(null);
  const [testingOkazii, setTestingOkazii] = useState(false);
  const [aiFeatures, setAiFeatures] = useState({});
  const [newAlias, setNewAlias] = useState("");
  const [newZone, setNewZone] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, st, fb, px, ps, us] = await Promise.all([
        radarAPI.getSettings(),
        radarAPI.getStats(),
        radarAPI.getFacebookStatus(),
        radarAPI.getProxy().catch(() => null),
        radarAPI.getPushStatus().catch(() => null),
        usersAPI.getSettings().catch(() => null),
      ]);
      setSettings(s.data);
      setStats(st.data);
      setFbStatus(fb.data);
      if (px?.data) setProxy({ ...EMPTY_PROXY, ...px.data, password: "" });
      if (ps?.data) setPushStatus(ps.data);
      if (us?.data?.ai_features_config) setAiFeatures(us.data.ai_features_config);
    } catch (e) {
      console.error("[Settings]", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const update = (patch) => setSettings({ ...settings, ...patch });

  const togglePlatform = async (key) => {
    const newVal = !settings[key];
    update({ [key]: newVal });
    try {
      await radarAPI.updateSettings({ [key]: newVal });
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la actualizare.");
      update({ [key]: !newVal });
    }
  };

  const saveLajumateCookie = async () => {
    setSaving(true);
    try {
      await radarAPI.updateSettings({ lajumate_cookie: settings.lajumate_cookie || "" });
      alert("Cookie LaJumate salvat.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSaving(false);
    }
  };

  const testLajumate = async () => {
    setTestingLajumate(true);
    setLajumateTestResult(null);
    try {
      const r = await radarAPI.testLaJumateCookie();
      setLajumateTestResult(r.data);
    } catch {
      setLajumateTestResult({ valid: false, message: "Eroare la testare." });
    } finally {
      setTestingLajumate(false);
    }
  };

  const saveOkaziiCookie = async () => {
    setSaving(true);
    try {
      await radarAPI.updateSettings({ okazii_cookie: settings.okazii_cookie || "" });
      alert("Cookie Okazii salvat.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSaving(false);
    }
  };

  const testOkazii = async () => {
    setTestingOkazii(true);
    setOkaziiTestResult(null);
    try {
      const r = await radarAPI.testOkaziiCookie();
      setOkaziiTestResult(r.data);
    } catch {
      setOkaziiTestResult({ valid: false, message: "Eroare la testare." });
    } finally {
      setTestingOkazii(false);
    }
  };

  const saveDiscord = async () => {
    setSaving(true);
    try {
      await radarAPI.updateSettings({
        discord_webhook_all: settings.discord_webhook_all || "",
        discord_webhook_buy_now: settings.discord_webhook_buy_now || "",
        discord_webhook_maybe: settings.discord_webhook_maybe || "",
        discord_webhook_auto: settings.discord_webhook_auto || "",
        discord_webhook_auto_all: settings.discord_webhook_auto_all || "",
        discord_webhook_auto_b: settings.discord_webhook_auto_b || "",
        discord_webhook_imob_all: settings.discord_webhook_imob_all || "",
        discord_webhook_imob_a: settings.discord_webhook_imob_a || "",
        discord_webhook_imob_b: settings.discord_webhook_imob_b || "",
      });
      alert("Webhook-uri Discord salvate.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSaving(false);
    }
  };

  const addZoneAlias = async () => {
    if (!newAlias.trim() || !newZone.trim()) return;
    const updated = { ...(settings.custom_zone_aliases || {}), [newAlias.toLowerCase().trim()]: newZone.trim() };
    update({ custom_zone_aliases: updated });
    setNewAlias(""); setNewZone("");
    try { await radarAPI.updateSettings({ custom_zone_aliases: updated }); }
    catch (e) { alert(e.response?.data?.detail || "Eroare la salvare zonă."); }
  };

  const removeZoneAlias = async (alias) => {
    const updated = { ...(settings.custom_zone_aliases || {}) };
    delete updated[alias];
    update({ custom_zone_aliases: updated });
    try { await radarAPI.updateSettings({ custom_zone_aliases: updated }); }
    catch (e) { alert(e.response?.data?.detail || "Eroare la ștergere zonă."); }
  };

  const testWebhook = async (url) => {
    if (!url) {
      alert("Webhook-ul este gol.");
      return;
    }
    try {
      await radarAPI.testDiscord(url);
      alert("Mesaj test trimis cu succes!");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la trimitere.");
    }
  };

  const saveProxy = async () => {
    setSaving(true);
    try {
      await radarAPI.updateProxy({
        enabled: !!proxy.enabled,
        host: proxy.host || "",
        port: proxy.port || "",
        username: proxy.username || "",
        password: proxy.password || "",
      });
      alert("Configurația proxy a fost salvată.");
      const px = await radarAPI.getProxy();
      setProxy({ ...EMPTY_PROXY, ...px.data, password: "" });
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare proxy.");
    } finally {
      setSaving(false);
    }
  };

  const activatePush = async () => {
    try {
      await registerPushNotifications();
      const r = await radarAPI.getPushStatus();
      setPushStatus(r.data);
      alert("Notificări push activate.");
    } catch (e) {
      alert(e.message || "Eroare la activare push.");
    }
  };

  const deactivatePush = async () => {
    try {
      await unregisterPushNotifications();
      const r = await radarAPI.getPushStatus();
      setPushStatus(r.data);
      alert("Notificări push dezactivate.");
    } catch (e) {
      alert(e.message || "Eroare la dezactivare push.");
    }
  };

  const connectFacebook = async () => {
    if (!confirm("Se va deschide o fereastră browser ca să te loghezi în Facebook. Continui?")) return;
    try {
      const r = await radarAPI.connectFacebook();
      alert(r.data?.message || "Browserul se deschide...");
      setTimeout(load, 130000);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la pornire login.");
    }
  };

  const cdGrades = stats ? (stats.listings_by_score?.C || 0) + (stats.listings_by_score?.D || 0) : 0;

  const navBtnStyle = (active) => ({
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: "0.625rem",
    padding: "0.5rem 0.75rem",
    fontSize: "0.8125rem",
    cursor: "pointer",
    borderRadius: "0.5rem",
    backgroundColor: active ? "rgba(37,99,235,0.15)" : "transparent",
    color: active ? "#60a5fa" : "var(--text-secondary)",
    border: active ? "1px solid rgba(37,99,235,0.3)" : "1px solid transparent",
    fontWeight: active ? 600 : 500,
  });

  const toggleAIFeature = async (key) => {
    const isCurrentlyEnabled = aiFeatures[key] !== false;
    const updated = { ...aiFeatures, [key]: !isCurrentlyEnabled };
    setAiFeatures(updated);
    try {
      await usersAPI.updateAIFeatures(updated);
    } catch {
      setAiFeatures(aiFeatures); // rollback
      alert("Eroare la salvare.");
    }
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.375rem" }}>
          <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#2563eb", display: "flex" }}>
            <SettingsIcon style={{ width: "20px", height: "20px", color: "white" }} />
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Setări</h1>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginLeft: "3rem" }}>
          Preferințele contului tău
        </p>
      </div>

      <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start" }}>
        {/* LEFT PANEL — navigatie */}
        <div style={{ width: "200px", flexShrink: 0, position: "sticky", top: "2rem" }}>
          <div style={{
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "0.75rem",
            padding: "0.5rem",
          }}>
            {NAV_SECTIONS.map((sec) => {
              const Icon = sec.icon;
              return (
                <button key={sec.id} onClick={() => setActiveSection(sec.id)} style={navBtnStyle(activeSection === sec.id)}>
                  <Icon style={{ width: "16px", height: "16px" }} />
                  {sec.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* RIGHT CONTENT */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {loading || !settings ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
              <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
            </div>
          ) : (
            <>
            {activeSection === "radar" && (
              <div>
                {/* MODIFICARE 13 — status sesiuni platforme (badge-uri OK/Lipsă/Expirat) */}
                <SessionStatusPanel />
                {/* Platforms */}
                <Section title="Platforme active">
                  <PlatformToggle label="OLX" enabled={settings.platform_olx_enabled} onToggle={() => togglePlatform("platform_olx_enabled")} />
                  <PlatformToggle label="Vinted" enabled={settings.platform_vinted_enabled} onToggle={() => togglePlatform("platform_vinted_enabled")} />
                  <PlatformToggle label="Okazii" enabled={settings.platform_okazii_enabled} onToggle={() => togglePlatform("platform_okazii_enabled")} />
                  <PlatformToggle label="Facebook Marketplace" enabled={settings.platform_facebook_enabled} onToggle={() => togglePlatform("platform_facebook_enabled")} />
                  <PlatformToggle
                    label="Lajumate.ro"
                    subtitle="Anunturi clasificate generaliste"
                    enabled={!!settings.platform_lajumate_enabled}
                    onToggle={() => togglePlatform("platform_lajumate_enabled")}
                  />
                  <PlatformToggle
                    label="Publi24.ro"
                    subtitle="Anunturi clasificate generaliste"
                    enabled={!!settings.platform_publi24_enabled}
                    onToggle={() => togglePlatform("platform_publi24_enabled")}
                  />
                  <PlatformToggle
                    label="Autovit.ro"
                    subtitle="Masini second-hand Romania"
                    enabled={!!settings.platform_autovit_enabled}
                    onToggle={() => togglePlatform("platform_autovit_enabled")}
                  />
                  <PlatformToggle
                    label="Mobile.de"
                    subtitle="Masini second-hand Germania - preturi in EUR"
                    enabled={!!settings.platform_mobilede_enabled}
                    onToggle={() => togglePlatform("platform_mobilede_enabled")}
                  />

                  <div style={{ marginTop: "0.5rem", padding: "0.625rem 0.75rem", backgroundColor: "var(--bg-dark)", borderRadius: "0.5rem", border: "1px solid var(--border-color)" }}>
                    {fbStatus.valid ? (
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
                        <span style={{ color: "#4ade80", fontSize: "0.8125rem", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                          <CheckCircle2 style={{ width: "14px", height: "14px" }} />
                          Sesiune Facebook activă
                        </span>
                        <button onClick={connectFacebook} style={smallBtn("#60a5fa")}>Reconectează</button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
                        <span style={{ color: "#facc15", fontSize: "0.8125rem", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                          <AlertCircle style={{ width: "14px", height: "14px" }} />
                          Sesiune Facebook inactivă
                        </span>
                        <button onClick={connectFacebook} style={smallBtn("#60a5fa")}>Conectează Facebook</button>
                      </div>
                    )}
                  </div>
                </Section>

                {/* Grupuri Facebook — Chirii (mutat din pagina standalone real-estate-monitor/groups) */}
                <FacebookGroupsSection />

                {/* Șabloane Mesaje (mutat din pagina standalone radar/templates; generalizat pe toate modulele) */}
                <MessageTemplatesSection />

                {/* Cookie LaJumate */}
                <Section title="Cookie LaJumate">
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0 0 0.25rem" }}>
                    Cookie-ul de sesiune de pe LaJumate.ro. Intră în Chrome → F12 → Network →
                    orice request → Request Headers → copiază valoarea de după &quot;Cookie:&quot;
                  </p>
                  <textarea
                    value={settings.lajumate_cookie || ""}
                    onChange={(e) => update({ lajumate_cookie: e.target.value })}
                    placeholder="Lipește cookie-ul LaJumate aici..."
                    rows={3}
                    style={{ ...inputStyle, fontFamily: "monospace", fontSize: "0.75rem", resize: "vertical" }}
                  />
                  <div style={{ marginTop: "0.625rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <button onClick={saveLajumateCookie} disabled={saving} style={primaryBtn(saving)}>
                      <Save style={{ width: "14px", height: "14px" }} />
                      Salvează cookie
                    </button>
                    <button
                      onClick={testLajumate}
                      disabled={testingLajumate}
                      style={{ ...primaryBtn(testingLajumate), backgroundColor: "rgba(37,99,235,0.15)", color: "#60a5fa", border: "1px solid rgba(37,99,235,0.3)" }}
                    >
                      <Activity style={{ width: "14px", height: "14px" }} />
                      {testingLajumate ? "Se testează..." : "Testează cookie"}
                    </button>
                  </div>
                  {lajumateTestResult && (
                    <div style={{ fontSize: "0.8125rem", marginTop: "0.375rem", color: lajumateTestResult.valid ? "#4ade80" : "#f87171" }}>
                      {lajumateTestResult.valid ? "✓ " : "✗ "}{lajumateTestResult.message}
                    </div>
                  )}
                </Section>

                {/* Cookie Okazii */}
                <Section title="Cookie Okazii">
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0 0 0.25rem" }}>
                    Cookie-ul de sesiune de pe Okazii.ro. Același proces: F12 → Network →
                    Request Headers → copiază &quot;Cookie:&quot;
                  </p>
                  <textarea
                    value={settings.okazii_cookie || ""}
                    onChange={(e) => update({ okazii_cookie: e.target.value })}
                    placeholder="Lipește cookie-ul Okazii aici..."
                    rows={3}
                    style={{ ...inputStyle, fontFamily: "monospace", fontSize: "0.75rem", resize: "vertical" }}
                  />
                  <div style={{ marginTop: "0.625rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <button onClick={saveOkaziiCookie} disabled={saving} style={primaryBtn(saving)}>
                      <Save style={{ width: "14px", height: "14px" }} />
                      Salvează cookie
                    </button>
                    <button
                      onClick={testOkazii}
                      disabled={testingOkazii}
                      style={{ ...primaryBtn(testingOkazii), backgroundColor: "rgba(37,99,235,0.15)", color: "#60a5fa", border: "1px solid rgba(37,99,235,0.3)" }}
                    >
                      <Activity style={{ width: "14px", height: "14px" }} />
                      {testingOkazii ? "Se testează..." : "Testează cookie"}
                    </button>
                  </div>
                  {okaziiTestResult && (
                    <div style={{ fontSize: "0.8125rem", marginTop: "0.375rem", color: okaziiTestResult.valid ? "#4ade80" : "#f87171" }}>
                      {okaziiTestResult.valid ? "✓ " : "✗ "}{okaziiTestResult.message}
                    </div>
                  )}
                </Section>

                {/* Discord */}
                <Section title="Discord Webhooks">
                  <WebhookInput
                    label="Webhook ALL — toate deal-urile"
                    value={settings.discord_webhook_all || ""}
                    onChange={(v) => update({ discord_webhook_all: v })}
                    onTest={() => testWebhook(settings.discord_webhook_all)}
                  />
                  <WebhookInput
                    label="Webhook BUY NOW — doar grade A și B"
                    value={settings.discord_webhook_buy_now || ""}
                    onChange={(v) => update({ discord_webhook_buy_now: v })}
                    onTest={() => testWebhook(settings.discord_webhook_buy_now)}
                  />
                  <WebhookInput
                    label="Webhook MAYBE — doar grade C și D"
                    value={settings.discord_webhook_maybe || ""}
                    onChange={(v) => update({ discord_webhook_maybe: v })}
                    onTest={() => testWebhook(settings.discord_webhook_maybe)}
                  />

                  <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.75rem" }}>Discord — Auto Anunțuri</div>
                  <WebhookInput label="Auto — Toate anunțurile" value={settings.discord_webhook_auto_all || ""} onChange={(v) => update({ discord_webhook_auto_all: v })} onTest={() => testWebhook(settings.discord_webhook_auto_all)} />
                  <WebhookInput label="Auto — Doar Grade A" value={settings.discord_webhook_auto || ""} onChange={(v) => update({ discord_webhook_auto: v })} onTest={() => testWebhook(settings.discord_webhook_auto)} />
                  <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "-0.25rem" }}>Primești notificări doar pentru anunțuri de Grad A.</div>
                  <WebhookInput label="Auto — Doar Grade B" value={settings.discord_webhook_auto_b || ""} onChange={(v) => update({ discord_webhook_auto_b: v })} onTest={() => testWebhook(settings.discord_webhook_auto_b)} />
                  <PlatformToggle label="Menționează @here pentru Grade A în Auto Anunțuri" enabled={!!settings.discord_here_auto} onToggle={() => togglePlatform("discord_here_auto")} />

                  <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.75rem" }}>Discord — Imobiliare</div>
                  <WebhookInput label="Imobiliare — Toate anunțurile" value={settings.discord_webhook_imob_all || ""} onChange={(v) => update({ discord_webhook_imob_all: v })} onTest={() => testWebhook(settings.discord_webhook_imob_all)} />
                  <WebhookInput label="Imobiliare — Doar Grade A" value={settings.discord_webhook_imob_a || ""} onChange={(v) => update({ discord_webhook_imob_a: v })} onTest={() => testWebhook(settings.discord_webhook_imob_a)} />
                  <WebhookInput label="Imobiliare — Doar Grade B" value={settings.discord_webhook_imob_b || ""} onChange={(v) => update({ discord_webhook_imob_b: v })} onTest={() => testWebhook(settings.discord_webhook_imob_b)} />
                  <PlatformToggle label="Menționează @here pentru Grade A în Imobiliare" enabled={!!settings.discord_here_imob} onToggle={() => togglePlatform("discord_here_imob")} />
                  <PlatformToggle label="Menționează @here pentru Grade A în Radar Piață" enabled={!!settings.discord_here_radar} onToggle={() => togglePlatform("discord_here_radar")} />

                  <div style={{ marginTop: "0.625rem" }}>
                    <button onClick={saveDiscord} disabled={saving} style={primaryBtn(saving)}>
                      <Save style={{ width: "14px", height: "14px" }} />
                      Salvează webhooks
                    </button>
                  </div>
                </Section>

                {/* Zone personalizate — Imobiliare */}
                <Section title="Zone personalizate — Imobiliare">
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0 0 0.5rem" }}>
                    Adaugă alias-uri pentru zone nerecunoscute automat. Ex: „langa IKEA Băneasa” → „Băneasa”.
                  </p>
                  {Object.entries(settings.custom_zone_aliases || {}).map(([alias, zone]) => (
                    <div key={alias} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.375rem 0", borderBottom: "0.5px solid var(--border-color)", fontSize: "0.8125rem" }}>
                      <span style={{ color: "var(--text-secondary)", flex: 1 }}>&quot;{alias}&quot;</span>
                      <span style={{ color: "var(--text-muted)" }}>→</span>
                      <span style={{ fontWeight: 500, flex: 1 }}>{zone}</span>
                      <button onClick={() => removeZoneAlias(alias)} style={{ background: "transparent", border: "none", color: "#f87171", cursor: "pointer", fontSize: "0.9rem" }}>✕</button>
                    </div>
                  ))}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr auto", gap: "0.5rem", marginTop: "0.75rem", alignItems: "center" }}>
                    <input placeholder='Alias (ex: "langa ikea")' value={newAlias} onChange={(e) => setNewAlias(e.target.value)} style={inputStyle} />
                    <span style={{ color: "var(--text-secondary)" }}>→</span>
                    <input placeholder='Zonă canonică (ex: "Băneasa")' value={newZone} onChange={(e) => setNewZone(e.target.value)} style={inputStyle} />
                    <button onClick={addZoneAlias} style={primaryBtn(false)}>Adaugă</button>
                  </div>
                </Section>

                {/* Proxy */}
                <Section title="Proxy (opțional)">
                  <PlatformToggle
                    label="Activează proxy"
                    enabled={!!proxy.enabled}
                    onToggle={() => setProxy({ ...proxy, enabled: !proxy.enabled })}
                  />
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                    <div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>Host</div>
                      <input
                        type="text"
                        value={proxy.host}
                        onChange={(e) => setProxy({ ...proxy, host: e.target.value })}
                        placeholder="proxy.exemplu.ro"
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>Port</div>
                      <input
                        type="text"
                        value={proxy.port}
                        onChange={(e) => setProxy({ ...proxy, port: e.target.value })}
                        placeholder="8080"
                        style={inputStyle}
                      />
                    </div>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                    <div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>Username</div>
                      <input
                        type="text"
                        value={proxy.username}
                        onChange={(e) => setProxy({ ...proxy, username: e.target.value })}
                        placeholder="(opțional)"
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>
                        Parolă {proxy.password_set && <span style={{ color: "#4ade80" }}>(setată)</span>}
                      </div>
                      <input
                        type="password"
                        value={proxy.password}
                        onChange={(e) => setProxy({ ...proxy, password: e.target.value })}
                        placeholder={proxy.password_set ? "Lasă gol pentru a păstra parola existentă" : "(opțional)"}
                        style={inputStyle}
                      />
                    </div>
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                    Folosește un proxy dacă primești erori de blocare la scraping. Lasă gol dacă nu ai nevoie.
                  </div>
                  <div>
                    <button onClick={saveProxy} disabled={saving} style={primaryBtn(saving)}>
                      <Save style={{ width: "14px", height: "14px" }} />
                      Salvează configurație proxy
                    </button>
                  </div>
                </Section>

                {/* Push notifications */}
                <Section title="Notificări Push Browser">
                  {!isPushSupported() ? (
                    <div style={{ padding: "0.75rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
                      Browserul tău nu suportă notificări push.
                    </div>
                  ) : !pushStatus.configured ? (
                    <div style={{ padding: "0.75rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", color: "#facc15", fontSize: "0.8125rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <AlertCircle style={{ width: "14px", height: "14px" }} />
                      Notificările push nu sunt configurate pe server (VAPID_PUBLIC_KEY lipsește din .env).
                    </div>
                  ) : (
                    <>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
                        <span style={{
                          color: pushStatus.subscribed ? "#4ade80" : "#facc15",
                          fontSize: "0.875rem",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.375rem",
                        }}>
                          {pushStatus.subscribed ? <CheckCircle2 style={{ width: "14px", height: "14px" }} /> : <AlertCircle style={{ width: "14px", height: "14px" }} />}
                          {pushStatus.subscribed ? "✅ Activate" : "⚠️ Inactive"}
                        </span>
                        {pushStatus.subscribed ? (
                          <button onClick={deactivatePush} style={smallBtn("#f87171")}>
                            <BellOff style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.25rem" }} />
                            Dezactivează
                          </button>
                        ) : (
                          <button onClick={activatePush} style={smallBtn("#60a5fa")}>
                            <BellRing style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.25rem" }} />
                            Activează notificări push
                          </button>
                        )}
                      </div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                        Funcționează în Brave, Chrome, Edge, Firefox când browserul e deschis. Permite notificările pentru acest site din setările browserului dacă e blocat.
                      </div>
                    </>
                  )}
                </Section>

                {/* Stats */}
                <Section title="Statistici Radar">
                  <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                    gap: "0.625rem",
                  }}>
                    <StatCard label="Total găsite" value={stats?.total_listings_found || 0} color="#60a5fa" />
                    <StatCard label="Grade A" value={stats?.listings_by_score?.A || 0} color="#4ade80" />
                    <StatCard label="Grade B" value={stats?.listings_by_score?.B || 0} color="#60a5fa" />
                    <StatCard label="Grade C+D" value={cdGrades} color="#facc15" />
                    <StatCard label="Salvate" value={stats?.listings_saved || 0} color="#a78bfa" />
                  </div>
                  <a href="/dashboard/reports" style={{ display: "inline-block", marginTop: "0.75rem", color: "var(--blue-light)", fontSize: "0.8125rem", textDecoration: "none" }}>
                    Vezi toate statisticile →
                  </a>
                </Section>
              </div>
            )}
            {activeSection === "ai_features" && (
              <div>
                <Section title="Funcționalități AI">
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0 0 0.25rem" }}>
                    Activează sau dezactivează funcționalitățile care folosesc API-ul Groq.
                  </p>
                  {AI_FEATURES.map((feat, idx) => {
                    const FeatIcon = feat.icon;
                    const enabled = aiFeatures[feat.key] !== false;
                    return (
                      <div key={feat.key} style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem",
                        padding: "0.75rem 0",
                        borderBottom: idx < AI_FEATURES.length - 1 ? "0.5px solid var(--border-color)" : "none",
                      }}>
                        <div style={{ display: "flex", alignItems: "flex-start", gap: "0.625rem", minWidth: 0 }}>
                          <FeatIcon style={{ width: "16px", height: "16px", color: "#60a5fa", flexShrink: 0, marginTop: "0.125rem" }} />
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontWeight: 500, fontSize: "0.9375rem", color: "var(--text-primary)" }}>{feat.label}</div>
                            <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.125rem" }}>{feat.description}</div>
                          </div>
                        </div>
                        <button
                          onClick={() => toggleAIFeature(feat.key)}
                          style={{ background: "none", border: "none", cursor: "pointer", color: enabled ? "#4ade80" : "var(--text-muted)", flexShrink: 0 }}
                        >
                          {enabled ? <ToggleRight style={{ width: "26px", height: "26px" }} /> : <ToggleLeft style={{ width: "26px", height: "26px" }} />}
                        </button>
                      </div>
                    );
                  })}
                </Section>
              </div>
            )}
            </>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// MODIFICARE 13 — panou status sesiuni platforme (Vinted/Okazii/LaJumate/Facebook).
function SessionStatusPanel() {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let cancelled = false;
    usersAPI.getSessionStatus()
      .then((r) => { if (!cancelled) setStatus(r.data); })
      .catch(() => { if (!cancelled) setStatus(null); });
    return () => { cancelled = true; };
  }, []);

  const badge = (st) => {
    if (st === "ok") return { bg: "var(--bg-success, rgba(34,197,94,0.15))", fg: "var(--text-success, #16a34a)", label: "OK" };
    if (st === "expired") return { bg: "var(--bg-warning, rgba(245,158,11,0.15))", fg: "var(--text-warning, #d97706)", label: "Expirat" };
    return { bg: "var(--bg-danger, rgba(239,68,68,0.15))", fg: "var(--text-danger, #dc2626)", label: "Lipsă" };
  };

  const rows = status ? [
    { key: "vinted", label: "Vinted", info: status.vinted },
    { key: "okazii", label: "Okazii", info: status.okazii },
    { key: "lajumate", label: "LaJumate", info: status.lajumate },
    { key: "facebook", label: "Facebook", info: status.facebook },
  ] : [];

  return (
    <Section title="Status sesiuni platforme">
      {!status ? (
        <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>Se încarcă...</p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "0.625rem" }}>
          {rows.map(({ key, label, info }) => {
            const b = badge(info?.status);
            return (
              <div key={key} style={{ display: "flex", flexDirection: "column", gap: "0.375rem", padding: "0.75rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>{label}</span>
                  <span style={{ fontSize: "0.6875rem", fontWeight: 700, padding: "0.125rem 0.5rem", borderRadius: "999px", background: b.bg, color: b.fg }}>{b.label}</span>
                </div>
                {key === "vinted" && info?.status === "ok" && info?.token_preview && (
                  <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "monospace" }}>token: {info.token_preview}</span>
                )}
                {key === "facebook" && info?.age_hours != null && (
                  <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>sesiune: acum {info.age_hours}h</span>
                )}
                {info?.detail && (
                  <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{info.detail}</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Section>
  );
}

function Section({ title, children }) {
  return (
    <section style={{
      backgroundColor: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      borderRadius: "0.75rem",
      padding: "1.25rem",
      marginBottom: "1rem",
    }}>
      <h2 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.875rem" }}>{title}</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
        {children}
      </div>
    </section>
  );
}

// ── Grupuri Facebook — Chirii (migrat din real-estate-monitor/groups; tab "posts" eliminat,
//    redundant cu Feed Imobiliare filtrat pe platforma facebook_groups) ─────────────────────
// Doar valorile acceptate de validatorul backend (FacebookGroupCreate: 1/2/4 ore).
// Pagina standalone veche oferea si 0.5/6, dar backend-ul le respingea la salvare (bug preexistent).
const FG_INTERVAL_OPTIONS = [
  { value: 1, label: "1 oră" }, { value: 2, label: "2 ore" }, { value: 4, label: "4 ore" },
];
const fgInputStyle = {
  width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
  borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)", fontSize: "0.875rem", outline: "none",
};
const fgLabelStyle = { display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.375rem" };
const fgIconBtn = {
  display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "0.375rem",
  backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.375rem",
  color: "var(--text-secondary)", cursor: "pointer",
};
const fgPrimaryBtn = {
  display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem", borderRadius: "0.5rem",
  backgroundColor: "var(--blue-primary)", color: "white", border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600,
};
const fgSecondaryBtn = {
  display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem", borderRadius: "0.5rem",
  backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
};
const fgDangerBtn = {
  display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem", borderRadius: "0.5rem",
  backgroundColor: "transparent", color: "#f87171", border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 600,
};

// Status cookies pentru un grup (portat din vechea pagina standalone Grupuri Facebook).
function cookieStatus(c) {
  if (c.last_run_status === "cookies_expirate") return { label: "Cookies expirate — reînnoire necesară", color: "#f87171", icon: AlertTriangle };
  if (!c.has_cookies || !c.cookies_saved_at) return { label: "Fără cookies", color: "var(--text-muted)", icon: AlertTriangle };
  const days = (Date.now() - new Date(c.cookies_saved_at).getTime()) / 86400000;
  if (days >= 53) return { label: "Cookies expiră în curând", color: "#fb923c", icon: Clock };
  return { label: "Cookies active", color: "#4ade80", icon: CheckCircle2 };
}
function cookieDaysLeft(c) {
  if (!c.cookies_saved_at) return null;
  const days = 60 - Math.floor((Date.now() - new Date(c.cookies_saved_at).getTime()) / 86400000);
  return Math.max(0, days);
}
function fgToList(v) {
  if (Array.isArray(v)) return v;
  try { const p = JSON.parse(v || "[]"); return Array.isArray(p) ? p : []; } catch { return []; }
}

// ── Șabloane Mesaje (migrat din pagina standalone radar/templates) ──────────────
// Generalizat: platforma acoperă TOATE cele 3 module (Radar + Imobiliare + Auto) + "all".
const TEMPLATE_PLATFORM_OPTIONS = [
  { value: "all", label: "Universal (toate platformele)" },
  { value: "olx", label: "OLX" },
  { value: "vinted", label: "Vinted" },
  { value: "okazii", label: "Okazii" },
  { value: "facebook", label: "Facebook" },
  { value: "lajumate", label: "LaJumate" },
  { value: "publi24", label: "Publi24" },
  { value: "storia", label: "Storia (imobiliare)" },
  { value: "imobiliare_ro", label: "Imobiliare.ro" },
  { value: "autovit", label: "Autovit" },
  { value: "olx_auto", label: "OLX Auto" },
  { value: "mobile_de", label: "Mobile.de" },
  { value: "autoscout24", label: "AutoScout24" },
  { value: "facebook_auto", label: "Facebook Auto" },
  { value: "kleinanzeigen_auto", label: "Kleinanzeigen" },
];
const TEMPLATE_PLACEHOLDERS = ["{titlu}", "{pret_cerut}", "{pret_oferit}", "{platforma}"];
const EMPTY_TEMPLATE_FORM = { name: "", platform: "all", template_text: "", is_default: false };

function MessageTemplatesSection() {
  const [items, setItems] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_TEMPLATE_FORM);
  const textareaRef = useRef(null);

  const load = useCallback(async () => {
    try { const r = await radarAPI.getTemplates(); setItems(r.data || []); }
    catch (e) { console.error("[Templates]", e); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditingId(null); setForm(EMPTY_TEMPLATE_FORM); setShowForm(true); };
  const openEdit = (t) => {
    setEditingId(t.id);
    setForm({ name: t.name, platform: t.platform, template_text: t.template_text, is_default: t.is_default });
    setShowForm(true);
  };

  const submit = async (e) => {
    e?.preventDefault();
    if (!form.name.trim() || !form.template_text.trim()) { alert("Numele și textul sunt obligatorii."); return; }
    try {
      if (editingId) await radarAPI.updateTemplate(editingId, form);
      else await radarAPI.createTemplate(form);
      setShowForm(false); load();
    } catch (e) { alert(e.response?.data?.detail || "Eroare la salvare."); }
  };

  const remove = async (id) => {
    if (!confirm("Ștergi acest șablon?")) return;
    try { await radarAPI.deleteTemplate(id); load(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare la ștergere."); }
  };

  const insertPlaceholder = (ph) => {
    const ta = textareaRef.current;
    if (!ta) { setForm({ ...form, template_text: form.template_text + ph }); return; }
    const start = ta.selectionStart || 0;
    const end = ta.selectionEnd || 0;
    const newText = form.template_text.slice(0, start) + ph + form.template_text.slice(end);
    setForm({ ...form, template_text: newText });
    requestAnimationFrame(() => { ta.focus(); const pos = start + ph.length; ta.setSelectionRange(pos, pos); });
  };

  const tInput = {
    width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
    borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
    fontSize: "0.875rem", outline: "none",
  };

  return (
    <Section title="Șabloane Mesaje">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", marginBottom: "0.875rem", flexWrap: "wrap" }}>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", margin: 0 }}>
          Mesaje pre-formulate pe care le poți copia rapid când contactezi vânzătorul, în orice modul ({items.length} șabloane).
        </p>
        <button onClick={openCreate} style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.875rem",
          backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem",
          fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer", flexShrink: 0,
        }}>
          <Plus style={{ width: "16px", height: "16px" }} /> Șablon nou
        </button>
      </div>

      {items.length === 0 ? (
        <div style={{ textAlign: "center", padding: "1.75rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.625rem", color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
          Nu ai niciun șablon. Creează unul cu butonul de mai sus.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "0.75rem" }}>
          {items.map((t) => (
            <div key={t.id} style={{ backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.625rem", padding: "0.875rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
                <h3 style={{ margin: 0, fontSize: "0.9rem", fontWeight: 600, color: "var(--text-primary)" }}>{t.name}</h3>
                <span style={{ padding: "0.125rem 0.5rem", backgroundColor: "rgba(37,99,235,0.15)", color: "#60a5fa", border: "1px solid rgba(37,99,235,0.3)", borderRadius: "0.375rem", fontSize: "0.7rem", fontWeight: 600, textTransform: "uppercase" }}>{t.platform}</span>
              </div>
              <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, whiteSpace: "pre-wrap", display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{t.template_text}</p>
              <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto" }}>
                <button onClick={() => openEdit(t)} style={tmplSmallBtn("#60a5fa")}><Pencil style={{ width: "12px", height: "12px", marginRight: "0.25rem", display: "inline" }} />Editează</button>
                <button onClick={() => remove(t.id)} style={tmplSmallBtn("#f87171")}><Trash2 style={{ width: "12px", height: "12px", marginRight: "0.25rem", display: "inline" }} />Șterge</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div onClick={() => setShowForm(false)} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1.5rem" }}>
          <form onClick={(e) => e.stopPropagation()} onSubmit={submit} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.875rem", maxWidth: "560px", width: "100%", maxHeight: "90vh", overflowY: "auto", padding: "1.25rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
              <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>{editingId ? "Editează șablon" : "Șablon nou"}</h2>
              <button type="button" onClick={() => setShowForm(false)} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}><X style={{ width: "20px", height: "20px" }} /></button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <label>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>Nume</div>
                <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={tInput} placeholder="ex: Interes general OLX" required />
              </label>
              <label>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>Platformă</div>
                <select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })} style={tInput}>
                  {TEMPLATE_PLATFORM_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </label>
              <label>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>Text șablon</div>
                <textarea ref={textareaRef} value={form.template_text} onChange={(e) => setForm({ ...form, template_text: e.target.value })} rows={6} style={{ ...tInput, resize: "vertical", fontFamily: "inherit" }} placeholder="Bună ziua, sunt interesat de {titlu}..." required />
              </label>
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: "0.375rem" }}>Click pe un placeholder pentru a-l insera la poziția cursorului:</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                  {TEMPLATE_PLACEHOLDERS.map((ph) => (
                    <button key={ph} type="button" onClick={() => insertPlaceholder(ph)} style={{ padding: "0.25rem 0.5rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.375rem", color: "var(--blue-light)", fontFamily: "monospace", fontSize: "0.75rem", cursor: "pointer" }}>{ph}</button>
                  ))}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button type="button" onClick={() => setShowForm(false)} style={{ padding: "0.5rem 0.875rem", backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem", cursor: "pointer" }}>Anulează</button>
              <button type="submit" style={{ padding: "0.5rem 0.875rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}><Save style={{ width: "14px", height: "14px" }} />Salvează</button>
            </div>
          </form>
        </div>
      )}
    </Section>
  );
}

function tmplSmallBtn(color) {
  return {
    padding: "0.3rem 0.625rem", backgroundColor: "var(--bg-card)", color,
    border: `1px solid ${color}55`, borderRadius: "0.375rem", fontSize: "0.75rem",
    fontWeight: 500, cursor: "pointer", display: "inline-flex", alignItems: "center",
  };
}

function FacebookGroupsSection() {
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [cookiesInput, setCookiesInput] = useState("");
  const [cookieBusy, setCookieBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const loadConfigs = useCallback(async () => {
    setLoading(true);
    try { const r = await facebookGroupsAPI.getConfigs(); setConfigs(r.data || []); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadConfigs(); }, [loadConfigs]);

  const toggleActive = async (cfg) => {
    try { await facebookGroupsAPI.updateConfig(cfg.id, { is_active: !cfg.is_active }); await loadConfigs(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  const verifyNow = async (cfg) => {
    try { await facebookGroupsAPI.testRun(cfg.id); alert("Verificare pornită."); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  const remove = async (cfg) => {
    if (!confirm(`Ștergi grupul „${cfg.group_name}”?`)) return;
    try { await facebookGroupsAPI.deleteConfig(cfg.id); await loadConfigs(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
  };
  const openSettings = (cfg) => {
    setExpandedId(expandedId === cfg.id ? null : cfg.id);
    setCookiesInput(""); setTestResult(null);
  };
  const saveCookies = async (cfg) => {
    if (!cookiesInput.trim()) { alert("Lipește JSON-ul cu cookies."); return; }
    setCookieBusy(true);
    try { await facebookGroupsAPI.saveCookies(cfg.id, cookiesInput.trim()); setCookiesInput(""); await loadConfigs(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare la salvarea cookies."); }
    finally { setCookieBusy(false); }
  };
  const deleteCookies = async (cfg) => {
    if (!confirm("Ștergi cookies-urile pentru acest grup?")) return;
    setCookieBusy(true);
    try { await facebookGroupsAPI.deleteCookies(cfg.id); await loadConfigs(); }
    catch (e) { alert(e.response?.data?.detail || "Eroare."); }
    finally { setCookieBusy(false); }
  };
  const testRun = async (cfg) => {
    setTesting(true); setTestResult(null);
    try {
      const r = await facebookGroupsAPI.testRun(cfg.id);
      const n = r.data?.new_posts ?? 0;
      setTestResult({ ok: true, text: n > 0 ? `S-au găsit ${n} postări noi.` : "Nicio postare nouă." });
      await loadConfigs();
    } catch (e) {
      setTestResult({ ok: false, text: e.response?.data?.detail || "Eroare la testare." });
    } finally { setTesting(false); }
  };

  return (
    <Section title="Grupuri Facebook — Chirii">
      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: 0 }}>
        Grupuri de închirieri monitorizate. Postările care se potrivesc criteriilor keyword-urilor
        tale de tip „Grupuri Facebook” apar automat în Feed Imobiliare.
      </p>
      <div>
        <button onClick={() => { setEditing(null); setShowModal(true); }} style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer" }}>
          <Plus style={{ width: "16px", height: "16px" }} /> Adaugă grup
        </button>
      </div>
      {loading ? (
        <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.8125rem" }}>Se încarcă...</div>
      ) : configs.length === 0 ? (
        <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.8125rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.5rem" }}>
          Niciun grup configurat. Apasă „Adaugă grup”.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {configs.map((cfg) => {
            const kws = fgToList(cfg.keywords); const negs = fgToList(cfg.negative_keywords);
            const cs = cookieStatus(cfg); const CsIcon = cs.icon; const expanded = expandedId === cfg.id;
            return (
              <div key={cfg.id} style={{ backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)", borderRadius: "0.625rem", padding: "0.875rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.75rem", flexWrap: "wrap" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)" }}>{cfg.group_name}</div>
                    <a href={cfg.group_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "0.75rem", color: "#60a5fa", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                      {String(cfg.group_url).slice(0, 50)} <ExternalLink style={{ width: "11px", height: "11px" }} />
                    </a>
                  </div>
                  <span style={{ fontSize: "0.6875rem", fontWeight: 600, padding: "0.125rem 0.5rem", borderRadius: "999px", color: cfg.is_active ? "#4ade80" : "var(--text-muted)", backgroundColor: cfg.is_active ? "rgba(34,197,94,0.15)" : "var(--bg-card)" }}>
                    {cfg.is_active ? "Activ" : "Inactiv"}
                  </span>
                </div>
                {(kws.length > 0 || negs.length > 0) && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem", marginTop: "0.5rem" }}>
                    {kws.map((w) => <span key={`k${w}`} style={{ fontSize: "0.6875rem", padding: "0.125rem 0.4rem", borderRadius: "0.25rem", backgroundColor: "rgba(34,197,94,0.12)", color: "#86efac" }}>{w}</span>)}
                    {negs.map((w) => <span key={`n${w}`} style={{ fontSize: "0.6875rem", padding: "0.125rem 0.4rem", borderRadius: "0.25rem", backgroundColor: "rgba(239,68,68,0.12)", color: "#fca5a5" }}>−{w}</span>)}
                  </div>
                )}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                    <span>Interval: {cfg.check_interval_hours}h · Ultima verificare: {cfg.last_run_at ? new Date(cfg.last_run_at).toLocaleString("ro-RO") : "niciodată"}{cfg.last_run_status ? ` · ${cfg.last_run_status}` : ""}</span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", color: cs.color, fontWeight: 600 }}>
                      <CsIcon style={{ width: "12px", height: "12px" }} /> {cs.label}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: "0.375rem" }}>
                    <button onClick={() => { setEditing(cfg); setShowModal(true); }} title="Editează" style={fgIconBtn}><Pencil style={{ width: "14px", height: "14px" }} /></button>
                    <button onClick={() => verifyNow(cfg)} title="Verifică acum" style={fgIconBtn}><RefreshCw style={{ width: "14px", height: "14px" }} /></button>
                    <button onClick={() => openSettings(cfg)} title="Cookies" style={{ ...fgIconBtn, color: expanded ? "#60a5fa" : "var(--text-secondary)" }}><SettingsIcon style={{ width: "14px", height: "14px" }} /></button>
                    <button onClick={() => toggleActive(cfg)} title={cfg.is_active ? "Dezactivează" : "Activează"} style={{ ...fgIconBtn, color: cfg.is_active ? "#4ade80" : "var(--text-muted)" }}>
                      {cfg.is_active ? <ToggleRight style={{ width: "16px", height: "16px" }} /> : <ToggleLeft style={{ width: "16px", height: "16px" }} />}
                    </button>
                    <button onClick={() => remove(cfg)} title="Șterge" style={{ ...fgIconBtn, color: "#f87171" }}><Trash2 style={{ width: "14px", height: "14px" }} /></button>
                  </div>
                </div>
                {expanded && (
                  <div style={{ marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-color)" }}>
                    <h4 style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-primary)", margin: "0 0 0.5rem" }}>Cum conectezi contul Facebook dedicat:</h4>
                    <ol style={{ fontSize: "0.7rem", color: "var(--text-secondary)", margin: "0 0 0.75rem", paddingLeft: "1.1rem", lineHeight: 1.7 }}>
                      <li>Instalează extensia <strong>Cookie-Editor</strong> în Chrome sau Firefox.</li>
                      <li>Deschide facebook.com și loghează-te cu contul dedicat FlipRadar.</li>
                      <li>Click pe extensia Cookie-Editor → Export → Export as JSON.</li>
                      <li>Copiază tot textul JSON și lipește-l mai jos:</li>
                    </ol>
                    <textarea value={cookiesInput} onChange={(e) => setCookiesInput(e.target.value)} placeholder="Lipește aici JSON-ul cu cookies..." rows={4} style={{ ...fgInputStyle, resize: "vertical", fontFamily: "monospace", fontSize: "0.72rem" }} />
                    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
                      <button onClick={() => saveCookies(cfg)} disabled={cookieBusy} style={fgPrimaryBtn}>{cookieBusy ? "Se salvează..." : "Salvează cookies"}</button>
                      {cfg.has_cookies && (
                        <button onClick={() => deleteCookies(cfg)} disabled={cookieBusy} style={fgDangerBtn}><Trash2 style={{ width: "13px", height: "13px" }} /> Șterge cookies</button>
                      )}
                      <button onClick={() => testRun(cfg)} disabled={testing || !cfg.has_cookies} style={{ ...fgSecondaryBtn, opacity: cfg.has_cookies ? 1 : 0.5 }}><Play style={{ width: "13px", height: "13px" }} /> {testing ? "Se testează..." : "Testează acum"}</button>
                    </div>
                    {cfg.has_cookies && cfg.cookies_saved_at && (
                      <p style={{ fontSize: "0.72rem", color: "#4ade80", margin: "0.5rem 0 0" }}>Cookies active · Salvate pe {new Date(cfg.cookies_saved_at).toLocaleDateString("ro-RO")} · Valabile ~{cookieDaysLeft(cfg)} zile</p>
                    )}
                    {testResult && (
                      <p style={{ fontSize: "0.78rem", margin: "0.5rem 0 0", color: testResult.ok ? "#4ade80" : "#f87171" }}>{testResult.text}</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {showModal && <FacebookGroupModal config={editing} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); loadConfigs(); }} />}
    </Section>
  );
}

function FacebookGroupModal({ config, onClose, onSaved }) {
  const [groupUrl, setGroupUrl] = useState(config?.group_url || "");
  const [groupName, setGroupName] = useState(config?.group_name || "");
  const [kw, setKw] = useState(fgToList(config?.keywords));
  const [neg, setNeg] = useState(fgToList(config?.negative_keywords));
  const [interval, setIntervalV] = useState(config?.check_interval_hours ?? 2);
  const [kwInput, setKwInput] = useState("");
  const [negInput, setNegInput] = useState("");
  const [saving, setSaving] = useState(false);

  const addChip = (val, list, setList, setInput) => {
    const v = (val || "").trim();
    if (v && !list.includes(v)) setList([...list, v]);
    setInput("");
  };

  const submit = async () => {
    if (!groupUrl.trim() || !groupName.trim()) { alert("URL și nume sunt obligatorii."); return; }
    const payload = {
      group_url: groupUrl, group_name: groupName,
      keywords: kw, negative_keywords: neg,
      check_interval_hours: parseFloat(interval),
    };
    setSaving(true);
    try {
      if (config) await facebookGroupsAPI.updateConfig(config.id, payload);
      else await facebookGroupsAPI.createConfig(payload);
      onSaved();
    } catch (e) { alert(e.response?.data?.detail || "Eroare la salvare."); }
    finally { setSaving(false); }
  };

  const chipBox = (list, setList) => (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem", marginTop: "0.375rem" }}>
      {list.map((w) => (
        <span key={w} style={{ fontSize: "0.6875rem", padding: "0.125rem 0.4rem", borderRadius: "0.25rem", backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
          {w}<button onClick={() => setList(list.filter((x) => x !== w))} style={{ background: "none", border: "none", color: "#f87171", cursor: "pointer", padding: 0 }}>×</button>
        </span>
      ))}
    </div>
  );

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1.5rem" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.875rem", width: "100%", maxWidth: "560px", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "1.25rem", borderBottom: "1px solid var(--border-color)" }}>
          <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>{config ? "Editează grup" : "Adaugă grup"}</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)" }}><X style={{ width: "20px", height: "20px" }} /></button>
        </div>
        <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div><label style={fgLabelStyle}>URL grup *</label><input value={groupUrl} onChange={(e) => setGroupUrl(e.target.value)} placeholder="https://www.facebook.com/groups/..." style={fgInputStyle} /></div>
          <div><label style={fgLabelStyle}>Nume afișat *</label><input value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="ex: Chirii București" style={fgInputStyle} /></div>
          <div>
            <label style={fgLabelStyle}>Keyword-uri incluse</label>
            <input value={kwInput} onChange={(e) => setKwInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addChip(kwInput, kw, setKw, setKwInput); } }} placeholder="Scrie și Enter" style={fgInputStyle} />
            {chipBox(kw, setKw)}
          </div>
          <div>
            <label style={fgLabelStyle}>Keyword-uri excluse</label>
            <input value={negInput} onChange={(e) => setNegInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addChip(negInput, neg, setNeg, setNegInput); } }} placeholder="Scrie și Enter" style={fgInputStyle} />
            {chipBox(neg, setNeg)}
          </div>
          <div>
            <label style={fgLabelStyle}>Interval verificare</label>
            <select value={interval} onChange={(e) => setIntervalV(e.target.value)} style={fgInputStyle}>
              {FG_INTERVAL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", padding: "1rem 1.25rem", borderTop: "1px solid var(--border-color)" }}>
          <button onClick={onClose} style={{ padding: "0.5rem 1rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 500, cursor: "pointer" }}>Anulează</button>
          <button onClick={submit} disabled={saving} style={{ padding: "0.5rem 1.25rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: saving ? "wait" : "pointer", opacity: saving ? 0.7 : 1 }}>
            {saving ? "Se salvează..." : config ? "Salvează" : "Adaugă"}
          </button>
        </div>
      </div>
    </div>
  );
}

function PlatformToggle({ label, subtitle, enabled, onToggle }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0.5rem 0.75rem", backgroundColor: "var(--bg-dark)",
      border: "1px solid var(--border-color)", borderRadius: "0.5rem",
      gap: "0.5rem",
    }}>
      <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span style={{ fontSize: "0.875rem", color: "var(--text-primary)", fontWeight: 500 }}>{label}</span>
        {subtitle && (
          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{subtitle}</span>
        )}
      </div>
      <button onClick={onToggle} style={{ background: "none", border: "none", cursor: "pointer", color: enabled ? "#4ade80" : "var(--text-muted)", flexShrink: 0 }}>
        {enabled ? <ToggleRight style={{ width: "26px", height: "26px" }} /> : <ToggleLeft style={{ width: "26px", height: "26px" }} />}
      </button>
    </div>
  );
}

function WebhookInput({ label, value, onChange, onTest }) {
  return (
    <div>
      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>{label}</div>
      <div style={{ display: "flex", gap: "0.375rem" }}>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="https://discord.com/api/webhooks/..."
          style={{ ...inputStyle, flex: 1 }}
        />
        <button onClick={onTest} style={{
          padding: "0.5rem 0.75rem",
          backgroundColor: "rgba(147,51,234,0.15)",
          color: "#c4b5fd",
          border: "1px solid rgba(147,51,234,0.3)",
          borderRadius: "0.5rem",
          fontSize: "0.75rem",
          fontWeight: 600,
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          gap: "0.25rem",
        }}>
          <Send style={{ width: "12px", height: "12px" }} />
          Testează
        </button>
      </div>
    </div>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{
      padding: "0.75rem",
      backgroundColor: "var(--bg-dark)",
      border: "1px solid var(--border-color)",
      borderRadius: "0.5rem",
      textAlign: "center",
    }}>
      <div style={{ fontSize: "1.25rem", fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>{label}</div>
    </div>
  );
}

const inputStyle = {
  width: "100%",
  backgroundColor: "var(--bg-dark)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.5rem",
  padding: "0.5rem 0.75rem",
  color: "var(--text-primary)",
  fontSize: "0.875rem",
  outline: "none",
};

function primaryBtn(disabled) {
  return {
    padding: "0.5rem 0.875rem",
    backgroundColor: "var(--blue-primary)",
    color: "white",
    border: "none",
    borderRadius: "0.5rem",
    fontSize: "0.8125rem",
    fontWeight: 600,
    cursor: disabled ? "wait" : "pointer",
    opacity: disabled ? 0.7 : 1,
    display: "inline-flex",
    alignItems: "center",
    gap: "0.375rem",
  };
}

function smallBtn(color) {
  return {
    padding: "0.3rem 0.625rem",
    backgroundColor: "var(--bg-card)",
    color,
    border: `1px solid ${color}55`,
    borderRadius: "0.375rem",
    fontSize: "0.75rem",
    fontWeight: 500,
    cursor: "pointer",
  };
}
