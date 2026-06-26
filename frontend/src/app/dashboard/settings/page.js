"use client";
import { useState, useEffect, useCallback } from "react";
import { radarAPI, usersAPI } from "@/lib/api";
import {
  Settings as SettingsIcon, Radar, Save, Send, ToggleLeft, ToggleRight,
  CheckCircle2, AlertCircle, ChevronDown, ChevronUp, Activity,
  BellRing, BellOff, Link as LinkIcon, Sparkles, FileText, MessageCircle, FileBarChart
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
  const [howToOpen, setHowToOpen] = useState(false);
  const [vintedTestResult, setVintedTestResult] = useState(null);
  const [testingVinted, setTestingVinted] = useState(false);
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

  const saveVintedCookie = async () => {
    setSaving(true);
    try {
      await radarAPI.updateSettings({ vinted_cookie: settings.vinted_cookie || "" });
      alert("Token Vinted salvat.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSaving(false);
    }
  };

  const testVinted = async () => {
    setTestingVinted(true);
    setVintedTestResult(null);
    try {
      const r = await radarAPI.testVintedToken();
      setVintedTestResult(r.data);
    } catch {
      setVintedTestResult({ valid: false, message: "Eroare la testare." });
    } finally {
      setTestingVinted(false);
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

                {/* Vinted Cookie */}
                <Section title="Token Vinted">
                  <textarea
                    value={settings.vinted_cookie || ""}
                    onChange={(e) => update({ vinted_cookie: e.target.value })}
                    placeholder="Lipește cookie-ul Vinted aici (access_token_web=...)..."
                    rows={3}
                    style={{ ...inputStyle, fontFamily: "monospace", fontSize: "0.75rem", resize: "vertical" }}
                  />

                  <button
                    onClick={() => setHowToOpen(!howToOpen)}
                    style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: "0.8125rem", display: "inline-flex", alignItems: "center", gap: "0.25rem", padding: 0, marginTop: "0.5rem" }}
                  >
                    {howToOpen ? <ChevronUp style={{ width: "14px", height: "14px" }} /> : <ChevronDown style={{ width: "14px", height: "14px" }} />}
                    Cum obțin cookie-ul Vinted?
                  </button>
                  {howToOpen && (
                    <ol style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.5rem", paddingLeft: "1.25rem", lineHeight: 1.6 }}>
                      <li>Loghează-te pe vinted.ro</li>
                      <li>Deschide DevTools (F12) → Application → Cookies</li>
                      <li>Copiază valoarea cookie-ului care conține <code>access_token_web</code></li>
                      <li>Lipește-o mai sus</li>
                    </ol>
                  )}

                  <div style={{ marginTop: "0.625rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <button onClick={saveVintedCookie} disabled={saving} style={primaryBtn(saving)}>
                      <Save style={{ width: "14px", height: "14px" }} />
                      Salvează token
                    </button>
                    <button
                      onClick={testVinted}
                      disabled={testingVinted}
                      style={{ ...primaryBtn(testingVinted), backgroundColor: "rgba(37,99,235,0.15)", color: "#60a5fa", border: "1px solid rgba(37,99,235,0.3)" }}
                    >
                      <Activity style={{ width: "14px", height: "14px" }} />
                      {testingVinted ? "Se testează..." : "Testează token"}
                    </button>
                  </div>
                  {vintedTestResult && (
                    <div style={{ fontSize: "0.8125rem", marginTop: "0.375rem", color: vintedTestResult.valid ? "#4ade80" : "#f87171" }}>
                      {vintedTestResult.valid ? "✓ " : "✗ "}{vintedTestResult.message}
                    </div>
                  )}
                </Section>

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
