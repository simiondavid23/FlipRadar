"use client";
import { useState, useEffect, useCallback } from "react";
import { radarAPI } from "@/lib/api";
import {
  Settings as SettingsIcon, ToggleLeft, ToggleRight, CheckCircle2, AlertCircle,
  Save, Send, ChevronDown, ChevronUp, Link as LinkIcon, BellRing, BellOff
} from "lucide-react";
import {
  isPushSupported, registerPushNotifications, unregisterPushNotifications
} from "@/lib/push";

const STAT_GROUPS = [
  { key: "total_listings_found", label: "Total găsite", color: "#60a5fa" },
  { key: "score_A", label: "Grade A", color: "#4ade80" },
  { key: "score_B", label: "Grade B", color: "#60a5fa" },
  { key: "score_CD", label: "Grade C+D", color: "#facc15" },
  { key: "listings_saved", label: "Salvate", color: "#a78bfa" },
];

const EMPTY_PROXY = { enabled: false, host: "", port: "", username: "", password: "", password_set: false };

export default function RadarSettingsPage() {
  const [settings, setSettings] = useState(null);
  const [stats, setStats] = useState(null);
  const [fbStatus, setFbStatus] = useState({ valid: false });
  const [proxy, setProxy] = useState(EMPTY_PROXY);
  const [pushStatus, setPushStatus] = useState({ subscribed: false, configured: false });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [howToOpen, setHowToOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, st, fb, px, ps] = await Promise.all([
        radarAPI.getSettings(),
        radarAPI.getStats(),
        radarAPI.getFacebookStatus(),
        radarAPI.getProxy().catch(() => null),
        radarAPI.getPushStatus().catch(() => null),
      ]);
      setSettings(s.data);
      setStats(st.data);
      setFbStatus(fb.data);
      if (px?.data) setProxy({ ...EMPTY_PROXY, ...px.data, password: "" });
      if (ps?.data) setPushStatus(ps.data);
    } catch (e) {
      console.error("[RadarSettings]", e);
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

  const saveDiscord = async () => {
    setSaving(true);
    try {
      await radarAPI.updateSettings({
        discord_webhook_all: settings.discord_webhook_all || "",
        discord_webhook_buy_now: settings.discord_webhook_buy_now || "",
        discord_webhook_maybe: settings.discord_webhook_maybe || "",
      });
      alert("Webhook-uri Discord salvate.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSaving(false);
    }
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

  if (loading || !settings) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  const cdGrades = stats ? (stats.listings_by_score?.C || 0) + (stats.listings_by_score?.D || 0) : 0;

  return (
    <div style={{ maxWidth: "920px", margin: "0 auto" }}>
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <SettingsIcon style={{ width: "22px", height: "22px", color: "#2563eb" }} />
          Setări Radar
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
          Platforme active, token-uri, webhook-uri Discord
        </p>
      </div>

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

        <div style={{ marginTop: "0.625rem" }}>
          <button onClick={saveVintedCookie} disabled={saving} style={primaryBtn(saving)}>
            <Save style={{ width: "14px", height: "14px" }} />
            Salvează token
          </button>
        </div>
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
        <div style={{ marginTop: "0.625rem" }}>
          <button onClick={saveDiscord} disabled={saving} style={primaryBtn(saving)}>
            <Save style={{ width: "14px", height: "14px" }} />
            Salvează webhooks
          </button>
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
