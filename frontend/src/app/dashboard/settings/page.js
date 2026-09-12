"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { radarAPI, usersAPI, facebookGroupsAPI, dealsAPI } from "@/lib/api";
import {
  Settings as SettingsIcon, Save, Send, ToggleLeft, ToggleRight,
  CheckCircle2, AlertCircle,
  Plus, Pencil, Trash2, RefreshCw, X, ExternalLink, Play, AlertTriangle, Clock
} from "lucide-react";
import TopBar from "@/components/shared/TopBar";
import PageHeading from "@/components/shared/PageHeading";

const EMPTY_PROXY = { enabled: false, host: "", port: "", username: "", password: "", password_set: false };

// DISC-1 — canalele Discord ale modulului Magazine, in ordinea din server.
// `toate` primeste orice deal; restul sunt canalele pe care le ruteaza registrul
// (cheia `channel` a fiecarui domeniu). Un magazin fara canal cade pe „diverse”.
const CANALE_DEAL = [
  ["toate", "Magazine — Toate deal-urile"],
  ["electronice", "Magazine — Electronice"],
  ["sneakers", "Magazine — Sneakers"],
  ["haine", "Magazine — Haine"],
  ["jucarii", "Magazine — Jucării"],
  ["beauty", "Magazine — Beauty"],
  ["diverse", "Magazine — Diverse"],
];

export default function SettingsPage() {
  // ── Radar settings state (copiat din vechea pagina /dashboard/radar/settings) ──
  const [settings, setSettings] = useState(null);
  const [fbStatus, setFbStatus] = useState({ status: null });
  // FB-LOGIN — asteptare activa + polling de status (in loc de setTimeout orb).
  const [fbConnecting, setFbConnecting] = useState(false);
  const fbPollRef = useRef(null);
  const [proxy, setProxy] = useState(EMPTY_PROXY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [flashThreshold, setFlashThreshold] = useState(15);
  const [savingThreshold, setSavingThreshold] = useState(false);
  const [aiFeatures, setAiFeatures] = useState({});
  // PKG-2 — furnizor AI comutabil (Groq/Gemini) + cheie per utilizator.
  const [aiProvider, setAiProvider] = useState("groq");
  const [aiModel, setAiModel] = useState("");
  const [aiKeyInput, setAiKeyInput] = useState("");   // valoarea NU se precompleteaza niciodata
  const [aiKeySet, setAiKeySet] = useState(false);
  const [aiSaving, setAiSaving] = useState(false);
  const [aiTesting, setAiTesting] = useState(false);
  const [aiTestResult, setAiTestResult] = useState(null);  // {ok, model} | {ok:false, error}
  const [newAlias, setNewAlias] = useState("");
  const [newZone, setNewZone] = useState("");
  // SHOP-2b — scannerul de deal-uri: prag + lista de magazine scanate.
  const [dealThreshold, setDealThreshold] = useState("");
  const [savingDealThreshold, setSavingDealThreshold] = useState(false);
  // DEAL-2b — pragul separat pentru R1 pe listari (preț tăiat de tip PRP).
  const [listingR1Threshold, setListingR1Threshold] = useState("");
  const [savingListingR1, setSavingListingR1] = useState(false);
  const [dealShops, setDealShops] = useState([]);

  const load = useCallback(async () => {
    const [s, fb, px, us, ds] = await Promise.all([
      radarAPI.getSettings().catch(() => null),
      radarAPI.getFacebookStatus().catch(() => null),
      radarAPI.getProxy().catch(() => null),
      usersAPI.getSettings().catch(() => null),
      dealsAPI.shops().catch(() => null),
    ]);
    if (s?.data) setSettings(s.data);
    if (s?.data?.deal_discount_threshold != null) {
      setDealThreshold(String(s.data.deal_discount_threshold));
    }
    if (s?.data?.listing_r1_threshold != null) {
      setListingR1Threshold(String(s.data.listing_r1_threshold));
    }
    if (ds?.data) setDealShops(ds.data);
    if (fb?.data) setFbStatus(fb.data);
    if (px?.data) setProxy({ ...EMPTY_PROXY, ...px.data, password: "" });
    if (us?.data?.ai_features_config) setAiFeatures(us.data.ai_features_config);
    if (us?.data) {
      setAiProvider(us.data.ai_provider || "groq");
      setAiModel(us.data.ai_model || "");
      setAiKeySet(!!us.data.ai_api_key_set);
    }
    if (us?.data?.flash_deal_threshold != null) setFlashThreshold(Math.round(us.data.flash_deal_threshold * 100));
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // FB-LOGIN — curata intervalul de polling la unmount.
  useEffect(() => () => { if (fbPollRef.current) clearInterval(fbPollRef.current); }, []);

  const update = (patch) => setSettings({ ...settings, ...patch });

  // DISC-1 — o singura cheie din harta de webhook-uri a modulului Magazine.
  const updateDealWebhook = (canal, valoare) =>
    update({ discord_webhooks_deals: { ...(settings.discord_webhooks_deals || {}), [canal]: valoare } });

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
        discord_webhook_alerts: settings.discord_webhook_alerts || "",
        // DISC-1 — harta se trimite INTREAGA: backend-ul o inlocuieste, iar un
        // camp golit in formular sterge cheia. De aceea nu se filtreaza aici.
        discord_webhooks_deals: settings.discord_webhooks_deals || {},
      });
      alert("Webhook-uri Discord salvate.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSaving(false);
    }
  };

  const saveFlashThreshold = async () => {
    const pct = Number(flashThreshold);
    if (!Number.isFinite(pct) || pct < 5 || pct > 50) {
      alert("Pragul trebuie să fie între 5 și 50%.");
      return;
    }
    setSavingThreshold(true);
    try {
      await usersAPI.updateFlashDealThreshold(pct / 100);
      alert("Pragul Flash Deal a fost salvat.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSavingThreshold(false);
    }
  };

  // SHOP-2b — pragul de discount. Gol = revenire la implicitul din backend (20%),
  // trimis ca null, nu ca 0 (backendul respinge valorile nepozitive).
  const saveDealThreshold = async () => {
    const brut = String(dealThreshold).trim();
    const pct = brut === "" ? null : Number(brut);
    if (pct !== null && (!Number.isFinite(pct) || pct <= 0 || pct > 95)) {
      alert("Pragul trebuie să fie între 1 și 95%, sau gol pentru implicit.");
      return;
    }
    setSavingDealThreshold(true);
    try {
      await radarAPI.updateSettings({ deal_discount_threshold: pct });
      update({ deal_discount_threshold: pct });
      alert(pct === null ? "Pragul revine la implicit (20%)." : "Pragul de discount a fost salvat.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSavingDealThreshold(false);
    }
  };

  // DEAL-2b — aceleasi validari si acelasi flux ca pragul de mai sus, pe cealalta
  // setare. Implicitul difera (40%), fiindca referinta e alta.
  const saveListingR1 = async () => {
    const brut = String(listingR1Threshold).trim();
    const pct = brut === "" ? null : Number(brut);
    if (pct !== null && (!Number.isFinite(pct) || pct <= 0 || pct > 95)) {
      alert("Pragul trebuie să fie între 1 și 95%, sau gol pentru implicit.");
      return;
    }
    setSavingListingR1(true);
    try {
      await radarAPI.updateSettings({ listing_r1_threshold: pct });
      update({ listing_r1_threshold: pct });
      alert(pct === null ? "Pragul revine la implicit (40%)." : "Pragul pentru listări a fost salvat.");
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    } finally {
      setSavingListingR1(false);
    }
  };

  const toggleDealShop = async (domain) => {
    const dezactivate = new Set(settings.deal_shops_disabled || []);
    if (dezactivate.has(domain)) dezactivate.delete(domain);
    else dezactivate.add(domain);
    const lista = [...dezactivate];

    // Optimist pe ambele surse: checkbox-ul citeste `dealShops`, iar calculul
    // urmator citeste `settings`.
    setDealShops((prev) => prev.map((s) => (s.domain === domain ? { ...s, disabled: !s.disabled } : s)));
    update({ deal_shops_disabled: lista });
    try {
      await radarAPI.updateSettings({ deal_shops_disabled: lista });
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la actualizare.");
      setDealShops((prev) => prev.map((s) => (s.domain === domain ? { ...s, disabled: !s.disabled } : s)));
      update({ deal_shops_disabled: settings.deal_shops_disabled || [] });
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

  const connectFacebook = async () => {
    if (!confirm("Se va deschide o fereastră browser ca să te loghezi în Facebook. Continui?")) return;
    try {
      await radarAPI.connectFacebook();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la pornire login.");
      return;
    }
    // Asteptam login-ul urmarind STATUSUL (nu un setTimeout orb): devine verde
    // la secunde dupa ce fisierul de sesiune e scris (varsta ~0).
    setFbConnecting(true);
    if (fbPollRef.current) clearInterval(fbPollRef.current);
    const startedAt = Date.now();
    fbPollRef.current = setInterval(async () => {
      if (Date.now() - startedAt > 260000) {   // LOGIN_TIMEOUT_S (240s) + buffer
        clearInterval(fbPollRef.current);
        fbPollRef.current = null;
        setFbConnecting(false);
        return;
      }
      try {
        const st = (await radarAPI.getFacebookStatus())?.data;
        // fisier proaspat scris (<0.1h) => login nou finalizat; merge si la Reconectare.
        if (st?.status === "active" && st.age_hours != null && st.age_hours < 0.1) {
          clearInterval(fbPollRef.current);
          fbPollRef.current = null;
          setFbConnecting(false);
          load();
        }
      } catch { /* un poll esuat nu opreste asteptarea */ }
    }, 3000);
  };

  // FB-LOGIN — in timpul asteptarii butonul e inlocuit de un mesaj (toate starile).
  const fbActionButton = (label) => fbConnecting ? (
    <span style={{ color: "#fde047", fontSize: "0.8125rem", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
      <AlertCircle style={{ width: "14px", height: "14px" }} />
      Se așteaptă login-ul în fereastra de browser deschisă...
    </span>
  ) : (
    <button onClick={connectFacebook} style={smallBtn("#60a5fa")}>{label}</button>
  );

  const toggleRadarReview = async () => {
    const enabled = aiFeatures.ai_radar_review !== false;
    const updated = { ...aiFeatures, ai_radar_review: !enabled };
    setAiFeatures(updated);
    try {
      await usersAPI.updateAIFeatures(updated);
    } catch {
      setAiFeatures(aiFeatures);
      alert("Eroare la salvare.");
    }
  };

  // PKG-2 — model default per furnizor (placeholder-ul câmpului Model).
  const PROVIDER_DEFAULT_MODEL = { groq: "llama-3.3-70b-versatile", gemini: "gemini-2.5-flash" };

  const saveAiSettings = async () => {
    setAiSaving(true);
    setAiTestResult(null);
    try {
      const payload = { ai_provider: aiProvider, ai_model: aiModel };
      if (aiKeyInput) payload.ai_api_key = aiKeyInput;   // cheia doar dacă a fost tastată
      const r = await usersAPI.updateAISettings(payload);
      if (r?.data) {
        setAiKeySet(!!r.data.ai_api_key_set);
        setAiModel(r.data.ai_model || "");
        setAiProvider(r.data.ai_provider || "groq");
      }
      setAiKeyInput("");   // nu păstrăm cheia tastată după salvare
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvarea setărilor AI.");
    } finally {
      setAiSaving(false);
    }
  };

  const testAiConnection = async () => {
    setAiTesting(true);
    setAiTestResult(null);
    try {
      const body = { provider: aiProvider, model: aiModel };
      if (aiKeyInput) body.api_key = aiKeyInput;   // include cheia tastată nesalvată
      const r = await usersAPI.testAIConnection(body);
      setAiTestResult(r.data);
    } catch (e) {
      setAiTestResult({ ok: false, error: e.response?.data?.detail || "Eroare la testare." });
    } finally {
      setAiTesting(false);
    }
  };

  return (
    <div style={{ maxWidth: "900px" }}>
      <TopBar path={["SETĂRI"]} />

      <PageHeading
        icon={SettingsIcon}
        title="Setări"
        subtitle="Preferințele contului tău — notificări, platforme, AI și magazine."
      />

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
          <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        </div>
      ) : !settings ? (
        <div style={{ padding: "1.5rem", background: "var(--bg-card)", backdropFilter: "blur(20px)", border: "1px solid var(--border-color)", borderRadius: "12px", textAlign: "center" }}>
          <p style={{ color: "#f87171", fontSize: "0.875rem", margin: "0 0 0.75rem" }}>
            Nu am putut încărca setările. Verifică dacă serverul răspunde.
          </p>
          <button onClick={() => { setLoading(true); load(); }} style={primaryBtn(false)}>Reîncearcă</button>
        </div>
      ) : (
        <>
          {/* Platforms */}
          <Section title="Platforme active — Radar Piață">
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0 0 0.25rem" }}>
              Aceste comutatoare afectează doar scanările din Radar Piață. Modulele Auto Anunțuri
              și Imobiliare își aleg platformele la nivel de keyword.
            </p>
            <PlatformToggle label="OLX" enabled={settings.platform_olx_enabled} onToggle={() => togglePlatform("platform_olx_enabled")} />
            <PlatformToggle label="Vinted" enabled={settings.platform_vinted_enabled} onToggle={() => togglePlatform("platform_vinted_enabled")} />
            <PlatformToggle label="Okazii" enabled={settings.platform_okazii_enabled} onToggle={() => togglePlatform("platform_okazii_enabled")} />
            <PlatformToggle label="Facebook Marketplace" enabled={settings.platform_facebook_enabled} onToggle={() => togglePlatform("platform_facebook_enabled")} />
            <PlatformToggle
              label="Lajumate.ro"
              subtitle="Anunțuri clasificate generaliste"
              enabled={!!settings.platform_lajumate_enabled}
              onToggle={() => togglePlatform("platform_lajumate_enabled")}
            />
            <PlatformToggle
              label="Publi24.ro"
              subtitle="Anunțuri clasificate generaliste"
              enabled={!!settings.platform_publi24_enabled}
              onToggle={() => togglePlatform("platform_publi24_enabled")}
            />

            <div style={{ marginTop: "0.5rem", padding: "0.625rem 0.75rem", background: "rgba(4,9,18,.45)", borderRadius: "10px", border: "1px solid var(--border-color)" }}>
              {fbStatus.status === "active" ? (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
                  <span style={{ color: "#4ade80", fontSize: "0.8125rem", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                    <CheckCircle2 style={{ width: "14px", height: "14px" }} />
                    Sesiune Facebook activă{fbStatus.age_hours != null ? ` — conectată acum ${fbStatus.age_hours < 48 ? Math.round(fbStatus.age_hours) + "h" : Math.round(fbStatus.age_hours / 24) + " zile"}` : ""}
                  </span>
                  {fbActionButton("Reconectează")}
                </div>
              ) : fbStatus.status === "expired" ? (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
                  <span style={{ color: "#fb923c", fontSize: "0.8125rem", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                    <AlertCircle style={{ width: "14px", height: "14px" }} />
                    Sesiune Facebook expirată{fbStatus.age_hours != null ? ` (acum ${Math.round(fbStatus.age_hours / 24)} zile)` : ""} — reconectare necesară
                  </span>
                  {fbActionButton("Reconectează")}
                </div>
              ) : (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
                  <span style={{ color: "#fde047", fontSize: "0.8125rem", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                    <AlertCircle style={{ width: "14px", height: "14px" }} />
                    Sesiune Facebook inactivă
                  </span>
                  {fbActionButton("Conectează Facebook")}
                </div>
              )}
            </div>
          </Section>

          {/* Grupuri Facebook — Chirii (mutat din pagina standalone real-estate-monitor/groups) */}
          <FacebookGroupsSection />

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

            <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.75rem" }}>Discord — Magazine (deal-uri)</div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0 0 0.25rem" }}>
              Fiecare deal nou pleacă pe canalul magazinului lui <em>și</em> pe „Toate
              deal-urile”. Magazinele fără canal declarat merg în „Diverse”. Un câmp gol
              înseamnă canal dezactivat.
            </p>
            {CANALE_DEAL.map(([canal, eticheta]) => (
              <WebhookInput
                key={canal}
                label={eticheta}
                value={(settings.discord_webhooks_deals || {})[canal] || ""}
                onChange={(v) => updateDealWebhook(canal, v)}
                onTest={() => testWebhook((settings.discord_webhooks_deals || {})[canal])}
              />
            ))}

            <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.75rem" }}>Discord — Alerte preț</div>
            <WebhookInput label="Alerte preț & Flash Deals" value={settings.discord_webhook_alerts || ""} onChange={(v) => update({ discord_webhook_alerts: v })} onTest={() => testWebhook(settings.discord_webhook_alerts)} />

            <div style={{ marginTop: "0.5rem", padding: "0.625rem 0.75rem", background: "rgba(4,9,18,.45)", borderRadius: "10px", border: "1px solid var(--border-color)" }}>
              <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>Prag Flash Deal</label>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0 0 0.5rem" }}>
                Un produs urmărit care scade brusc cu cel puțin acest procent declanșează o alertă Flash Deal pe webhook-ul de mai sus.
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                <input type="number" min={5} max={50} value={flashThreshold} onChange={(e) => setFlashThreshold(e.target.value)}
                  style={{ width: "5rem", padding: "0.375rem 0.5rem", background: "var(--bg-card)", backdropFilter: "blur(20px)", color: "var(--text-primary)", border: "1px solid var(--border-color)", borderRadius: "8px", fontSize: "0.8125rem" }} />
                <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>%</span>
                <button onClick={saveFlashThreshold} disabled={savingThreshold} style={smallBtn("#4ade80")}>
                  {savingThreshold ? "Se salvează..." : "Salvează pragul"}
                </button>
              </div>
            </div>

            <div style={{ marginTop: "0.625rem" }}>
              <button onClick={saveDiscord} disabled={saving} style={primaryBtn(saving)}>
                <Save style={{ width: "14px", height: "14px" }} />
                Salvează webhooks
              </button>
            </div>
          </Section>

          {/* SHOP-2b — scannerul de deal-uri Shopify */}
          <Section title="Deal-uri Catalog">
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0 0 0.5rem" }}>
              Scanarea rulează la fiecare 6 ore pe magazinele Shopify din catalog și
              raportează produsele reduse sub pragul de mai jos.
            </p>

            {/* DISC-1 — webhook-ul unic de deal-uri a fost inlocuit de cele sapte
                canale din sectiunea „Discord — Magazine (deal-uri)”. Nu mai apare
                aici: un input care nu mai ruteaza nimic ar arata identic cu unul
                care ruteaza. */}

            <PlatformToggle
              label="Scanare deal-uri activă"
              enabled={settings.deal_scan_enabled !== false}
              onToggle={() => togglePlatform("deal_scan_enabled")}
            />

            <div style={{ padding: "0.625rem 0.75rem", background: "rgba(4,9,18,.45)", borderRadius: "10px", border: "1px solid var(--border-color)" }}>
              <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>Prag discount</label>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0 0 0.5rem" }}>
                Un produs devine deal când scade cu cel puțin acest procent — față de
                prețul de referință al magazinului sau față de minimul văzut de noi.
                Lasă gol pentru implicit (20%).
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                <input
                  type="number" min={1} max={95} placeholder="20"
                  value={dealThreshold}
                  onChange={(e) => setDealThreshold(e.target.value)}
                  style={{ width: "5rem", padding: "0.375rem 0.5rem", background: "var(--bg-card)", backdropFilter: "blur(20px)", color: "var(--text-primary)", border: "1px solid var(--border-color)", borderRadius: "8px", fontSize: "0.8125rem" }}
                />
                <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>%</span>
                <button onClick={saveDealThreshold} disabled={savingDealThreshold} style={smallBtn("#4ade80")}>
                  {savingDealThreshold ? "Se salvează..." : "Salvează pragul"}
                </button>
              </div>
            </div>

            <div style={{ padding: "0.625rem 0.75rem", background: "rgba(4,9,18,.45)", borderRadius: "10px", border: "1px solid var(--border-color)" }}>
              <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>Prag reducere listări (R1, %)</label>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0 0 0.5rem" }}>
                Pe paginile de reduceri, prețul tăiat e de obicei un preț recomandat
                permanent, față de care aproape tot catalogul pare redus — deci pragul
                lui e separat și mult mai sus. Nu afectează scăderile sub minimul
                istoric, care rămân pe pragul de mai sus. Lasă gol pentru implicit (40%).
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                <input
                  type="number" min={1} max={95} placeholder="40"
                  value={listingR1Threshold}
                  onChange={(e) => setListingR1Threshold(e.target.value)}
                  style={{ width: "5rem", padding: "0.375rem 0.5rem", background: "var(--bg-card)", backdropFilter: "blur(20px)", color: "var(--text-primary)", border: "1px solid var(--border-color)", borderRadius: "8px", fontSize: "0.8125rem" }}
                />
                <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>%</span>
                <button onClick={saveListingR1} disabled={savingListingR1} style={smallBtn("#4ade80")}>
                  {savingListingR1 ? "Se salvează..." : "Salvează pragul"}
                </button>
              </div>
            </div>

            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".15em", textTransform: "uppercase", color: "var(--text-mono)", marginBottom: "6px" }}>
                Magazine scanate
              </div>
              {dealShops.length === 0 ? (
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: 0 }}>
                  Nu am putut încărca lista de magazine.
                </p>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: "6px" }}>
                  {dealShops.map((shop) => (
                    <label
                      key={shop.domain}
                      style={{
                        display: "flex", alignItems: "center", gap: "8px",
                        padding: "7px 10px", background: "rgba(4,9,18,.45)",
                        border: "1px solid rgba(94,140,255,.11)", borderRadius: "10px",
                        fontSize: "12px", color: "var(--text-secondary)", cursor: "pointer",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={!shop.disabled}
                        onChange={() => toggleDealShop(shop.domain)}
                        style={{ accentColor: "#22d3ee", cursor: "pointer" }}
                      />
                      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {shop.label}
                      </span>
                      {shop.last_status && shop.last_status !== "ok" && (
                        <span title={shop.last_status} style={{ color: "#f87171", fontSize: "11px" }}>⚠</span>
                      )}
                    </label>
                  ))}
                </div>
              )}
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

          {/* Analiză AI */}
          <Section title="Analiză AI">
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0 }}>
              Când deschizi un anunț în Radar Piață, Auto Anunțuri sau Imobiliare, se generează
              automat o analiză AI. Fiecare analiză înseamnă un apel către furnizorul AI configurat.
            </p>
            <PlatformToggle
              label="Review AI la deschiderea unui anunț"
              enabled={aiFeatures.ai_radar_review !== false}
              onToggle={toggleRadarReview}
            />

            {/* PKG-2 — furnizor AI comutabil + cheie per utilizator */}
            <div style={{ borderTop: "1px solid var(--border-color)", marginTop: "0.25rem", paddingTop: "0.875rem", display: "flex", flexDirection: "column", gap: "0.625rem" }}>
              <label style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", display: "block" }}>
                Furnizor AI
                <select value={aiProvider} onChange={(e) => setAiProvider(e.target.value)} style={{ ...inputStyle, marginTop: "0.25rem" }}>
                  <option value="groq">Groq</option>
                  <option value="gemini">Google Gemini</option>
                </select>
              </label>
              <label style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", display: "block" }}>
                Cheie API
                <input
                  type="password"
                  value={aiKeyInput}
                  onChange={(e) => setAiKeyInput(e.target.value)}
                  placeholder={aiKeySet ? "Cheie setată — introdu una nouă pentru a o înlocui" : "Introdu cheia API"}
                  style={{ ...inputStyle, marginTop: "0.25rem" }}
                />
              </label>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                Obține cheia:{" "}
                <a href="https://console.groq.com/keys" target="_blank" rel="noopener noreferrer" style={{ color: "#60a5fa" }}>Groq — console.groq.com/keys</a>
                {" · "}
                <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" style={{ color: "#60a5fa" }}>Gemini — aistudio.google.com/apikey</a>
              </div>
              <label style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", display: "block" }}>
                Model (opțional)
                <input
                  type="text"
                  value={aiModel}
                  onChange={(e) => setAiModel(e.target.value)}
                  placeholder={PROVIDER_DEFAULT_MODEL[aiProvider] || ""}
                  style={{ ...inputStyle, marginTop: "0.25rem" }}
                />
              </label>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                <button onClick={saveAiSettings} disabled={aiSaving} style={primaryBtn(aiSaving)}>
                  <Save style={{ width: "14px", height: "14px" }} />
                  {aiSaving ? "Se salvează…" : "Salvează"}
                </button>
                <button onClick={testAiConnection} disabled={aiTesting} style={smallBtn("#60a5fa")}>
                  <Send style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.25rem" }} />
                  {aiTesting ? "Se testează…" : "Testează conexiunea"}
                </button>
                {aiTestResult && (
                  <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: aiTestResult.ok ? "#4ade80" : "#f87171", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                    {aiTestResult.ok
                      ? `✅ Conexiune OK — ${aiTestResult.model}`
                      : `⚠️ ${aiTestResult.error}`}
                  </span>
                )}
              </div>
            </div>
          </Section>
        </>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}


function Section({ title, children }) {
  return (
    <section className="glass-panel" style={{ padding: "18px", marginTop: "14px" }}>
      <h2 style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "14px" }}>{title}</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
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
  width: "100%",
  background: "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.08) 55%, transparent) border-box",
  border: "1px solid transparent",
  borderRadius: "10px", padding: "8px 12px", color: "var(--text-primary)",
  fontSize: "12.5px", fontFamily: "var(--font-sans)", outline: "none",
};
const fgLabelStyle = {
  display: "block", fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".15em",
  textTransform: "uppercase", color: "var(--text-mono)", marginBottom: "6px",
};
const fgIconBtn = {
  display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "6px",
  background: "rgba(255,255,255,.03)", border: "1px solid rgba(94,140,255,.14)", borderRadius: "9px",
  color: "var(--text-tertiary)", cursor: "pointer",
};
const fgPrimaryBtn = {
  display: "inline-flex", alignItems: "center", gap: "8px", padding: "9px 16px", borderRadius: "12px",
  background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)",
  color: "#7ee7f8", border: "1px solid rgba(34,211,238,.42)", cursor: "pointer",
  fontFamily: "var(--font-sans)", fontSize: "12.5px", fontWeight: 600,
  boxShadow: "0 0 22px rgba(34,211,238,.16), inset 0 1px 0 rgba(255,255,255,.1)",
};
const fgSecondaryBtn = {
  display: "inline-flex", alignItems: "center", gap: "8px", padding: "9px 16px", borderRadius: "12px",
  background: "rgba(148,163,184,.07)", color: "var(--text-dim)", border: "1px solid rgba(148,163,184,.2)",
  cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: "12.5px", fontWeight: 500,
};
const fgDangerBtn = {
  display: "inline-flex", alignItems: "center", gap: "8px", padding: "9px 16px", borderRadius: "12px",
  background: "linear-gradient(135deg, rgba(248,113,113,.14), rgba(248,113,113,.03) 60%, transparent)",
  color: "#fca5a5", border: "1px solid rgba(248,113,113,.36)",
  cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: "12.5px", fontWeight: 600,
};

// Status cookies pentru un grup (portat din vechea pagina standalone Grupuri Facebook).
function cookieStatus(c) {
  if (c.last_run_status === "cookies_expirate") return { label: "Cookies expirate — reînnoire necesară", color: "#f87171", icon: AlertTriangle };
  if (c.last_run_status === "cookies_invalide") return { label: "Cookies invalide — re-lipește exportul din Cookie-Editor", color: "#f87171", icon: AlertTriangle };
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
        <button onClick={() => { setEditing(null); setShowModal(true); }} style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem", background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)", color: "#7ee7f8", border: "1px solid rgba(34,211,238,.42)", borderRadius: "10px", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer" }}>
          <Plus style={{ width: "16px", height: "16px" }} /> Adaugă grup
        </button>
      </div>
      {loading ? (
        <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.8125rem" }}>Se încarcă...</div>
      ) : configs.length === 0 ? (
        <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.8125rem", background: "rgba(4,9,18,.45)", border: "1px solid var(--border-color)", borderRadius: "10px" }}>
          Niciun grup configurat. Apasă „Adaugă grup”.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {configs.map((cfg) => {
            const kws = fgToList(cfg.keywords); const negs = fgToList(cfg.negative_keywords);
            const cs = cookieStatus(cfg); const CsIcon = cs.icon; const expanded = expandedId === cfg.id;
            return (
              <div key={cfg.id} style={{ background: "rgba(4,9,18,.45)", border: "1px solid var(--border-color)", borderRadius: "10px", padding: "0.875rem" }}>
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
        <span key={w} style={{ fontSize: "0.6875rem", padding: "0.125rem 0.4rem", borderRadius: "0.25rem", background: "rgba(4,9,18,.45)", color: "var(--text-secondary)", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
          {w}<button onClick={() => setList(list.filter((x) => x !== w))} style={{ background: "none", border: "none", color: "#f87171", cursor: "pointer", padding: 0 }}>×</button>
        </span>
      ))}
    </div>
  );

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(2,5,12,0.72)", backdropFilter: "blur(6px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1.5rem" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "var(--bg-card)", backdropFilter: "blur(20px)", border: "1px solid var(--border-color)", borderRadius: "14px", width: "100%", maxWidth: "560px", maxHeight: "90vh", overflowY: "auto" }}>
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
          <button onClick={onClose} style={{ padding: "0.5rem 1rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "10px", fontSize: "0.8125rem", fontWeight: 500, cursor: "pointer" }}>Anulează</button>
          <button onClick={submit} disabled={saving} style={{ padding: "0.5rem 1.25rem", background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)", color: "#7ee7f8", border: "1px solid rgba(34,211,238,.42)", borderRadius: "10px", fontSize: "0.8125rem", fontWeight: 600, cursor: saving ? "wait" : "pointer", opacity: saving ? 0.7 : 1 }}>
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
      padding: "10px 13px", background: "rgba(4,9,18,.45)",
      border: "1px solid rgba(94,140,255,.11)", borderRadius: "11px",
      gap: "10px",
    }}>
      <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span style={{ fontSize: "12.5px", color: "var(--text-primary)", fontWeight: 500 }}>{label}</span>
        {subtitle && (
          <span style={{ fontSize: "10.5px", color: "var(--text-muted)", marginTop: "2px" }}>{subtitle}</span>
        )}
      </div>
      <button
        onClick={onToggle}
        aria-pressed={enabled}
        aria-label={label}
        className={`toggle-cyan${enabled ? " on" : ""}`}
      />
    </div>
  );
}

function WebhookInput({ label, value, onChange, onTest }) {
  return (
    <div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".15em", textTransform: "uppercase", color: "var(--text-mono)", marginBottom: "6px" }}>{label}</div>
      <div style={{ display: "flex", gap: "0.375rem" }}>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="https://discord.com/api/webhooks/..."
          style={{ ...inputStyle, flex: 1 }}
        />
        <button onClick={onTest} style={{
          padding: "8px 13px",
          background: "linear-gradient(135deg, rgba(147,51,234,.2), rgba(147,51,234,.05) 60%, transparent)",
          color: "#c4b5fd",
          border: "1px solid rgba(147,51,234,.4)",
          borderRadius: "10px",
          fontFamily: "var(--font-sans)",
          fontSize: "11.5px",
          fontWeight: 600,
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          gap: "5px",
          whiteSpace: "nowrap",
        }}>
          <Send style={{ width: "12px", height: "12px" }} strokeWidth={2} />
          Testează
        </button>
      </div>
    </div>
  );
}

const inputStyle = {
  width: "100%",
  background: "linear-gradient(rgba(6,11,22,.7),rgba(6,11,22,.7)) padding-box, linear-gradient(135deg, rgba(34,211,238,.3), rgba(59,130,246,.08) 55%, transparent) border-box",
  border: "1px solid transparent",
  borderRadius: "10px",
  padding: "8px 12px",
  color: "var(--text-primary)",
  fontSize: "12.5px",
  fontFamily: "var(--font-sans)",
  outline: "none",
};

function primaryBtn(disabled) {
  return {
    padding: "9px 16px",
    background: "linear-gradient(135deg, rgba(34,211,238,.16), rgba(34,211,238,.04) 60%, transparent)",
    color: "#7ee7f8",
    border: "1px solid rgba(34,211,238,.42)",
    borderRadius: "12px",
    fontFamily: "var(--font-sans)",
    fontSize: "12.5px",
    fontWeight: 600,
    cursor: disabled ? "wait" : "pointer",
    opacity: disabled ? 0.6 : 1,
    boxShadow: "0 0 22px rgba(34,211,238,.16), inset 0 1px 0 rgba(255,255,255,.1)",
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
  };
}

function smallBtn(color) {
  return {
    padding: "6px 11px",
    background: "rgba(4,9,18,.45)",
    color,
    border: `1px solid ${color}55`,
    borderRadius: "9px",
    fontFamily: "var(--font-sans)",
    fontSize: "11.5px",
    fontWeight: 500,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
  };
}
