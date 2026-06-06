"use client";
import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { productsAPI, watchlistAPI, alertsAPI } from "@/lib/api";
import {
  ArrowLeft, ExternalLink, Eye, Bell, Package, TrendingUp, TrendingDown, Minus, Trash2, RefreshCw,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";

const SOURCE_COLORS = {
  "altex.ro": { bg: "rgba(59,130,246,0.2)", fg: "#60a5fa" },
  "sole.ro": { bg: "rgba(236,72,153,0.2)", fg: "#f472b6" },
  "farmaciatei.ro": { bg: "rgba(34,197,94,0.2)", fg: "#4ade80" },
};

export default function ProductDetailPage() {
  const params = useParams();
  const router = useRouter();
  const productId = params.id;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [alertForm, setAlertForm] = useState({ show: false, target_price: "", currency: "EUR", alert_type: "price_drop" });
  const [alertMsg, setAlertMsg] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResults, setRefreshResults] = useState(null);
  const [copiedKey, setCopiedKey] = useState(null);

  const copyToClipboard = async (value, key) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(String(value));
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((curr) => (curr === key ? null : curr)), 1200);
    } catch {
      alert("Nu am putut copia in clipboard. Verifica permisiunile browser-ului.");
    }
  };

  const loadProduct = useCallback(async () => {
    try {
      const response = await productsAPI.getProduct(productId);
      setData(response.data);
    } catch (error) {
      console.error("Error loading product:", error);
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    if (productId) loadProduct();
  }, [productId, loadProduct]);

  const handleAddToWatchlist = async () => {
    try {
      await watchlistAPI.addToWatchlist({ product_id: parseInt(productId) });
      alert("Produs adaugat in watchlist!");
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare");
    }
  };

  const handleCreateAlert = async (e) => {
    e.preventDefault();
    try {
      await alertsAPI.createAlert({
        product_id: parseInt(productId),
        target_price: parseFloat(alertForm.target_price),
        alert_type: alertForm.alert_type,
        currency: alertForm.currency,
      });
      setAlertMsg("Alerta creata cu succes!");
      setAlertForm({ show: false, target_price: "", currency: "EUR", alert_type: "price_drop" });
      setTimeout(() => setAlertMsg(""), 3000);
    } catch (error) {
      setAlertMsg(error.response?.data?.detail || "Eroare la creare alerta");
    }
  };

  const handleRefreshPrice = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshResults(null);
    try {
      const response = await productsAPI.refreshPrice(productId);
      setRefreshResults(response.data.results || []);
      await loadProduct();
    } catch (error) {
      setRefreshResults([{
        source: "-", source_url: "", success: false,
        error: error.response?.data?.detail || "Eroare la actualizarea pretului",
      }]);
    } finally {
      setRefreshing(false);
    }
  };

  const handleDeleteProduct = async () => {
    const name = data?.product?.name || "acest produs";
    const ok = window.confirm(
      `Esti sigur ca vrei sa stergi produsul "${name}"?\n\nAceasta actiune este ireversibila si va sterge si:\n- Istoricul de preturi\n- Alertele asociate\n- Intrarile din watchlist`
    );
    if (!ok) return;
    try {
      await productsAPI.deleteProduct(productId);
      router.push("/dashboard/products");
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la stergere");
    }
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ maxWidth: "960px", margin: "0 auto", textAlign: "center", paddingTop: "4rem" }}>
        <Package style={{ width: "3rem", height: "3rem", margin: "0 auto 1rem", color: "var(--text-secondary)" }} />
        <p style={{ color: "var(--text-primary)", fontSize: "1rem", marginBottom: "0.5rem" }}>Produsul nu a fost gasit</p>
        <Link href="/dashboard/products" style={{ color: "#60a5fa", fontSize: "0.875rem" }}>← Inapoi la produse</Link>
      </div>
    );
  }

  const { product, price_history, lowest_price, highest_price, average_price } = data;

  // Pregătim datele graficului (cele mai vechi primele)
  const chartData = [...(price_history || [])].reverse().map((ph) => ({
    date: new Date(ph.recorded_at).toLocaleDateString("ro-RO", { day: "2-digit", month: "short" }),
    fullDate: new Date(ph.recorded_at).toLocaleDateString("ro-RO"),
    price: ph.price,
  }));

  // Determinăm trendul prețului
  let trend = "stable";
  if (chartData.length >= 2) {
    const first = chartData[0].price;
    const last = chartData[chartData.length - 1].price;
    if (last < first) trend = "down";
    else if (last > first) trend = "up";
  }

  const trendConfig = {
    up: { icon: TrendingUp, color: "#f87171", label: "In crestere" },
    down: { icon: TrendingDown, color: "#4ade80", label: "In scadere" },
    stable: { icon: Minus, color: "var(--text-secondary)", label: "Stabil" },
  };
  const TrendIcon = trendConfig[trend].icon;

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      {/* Back link */}
      <Link
        href="/dashboard/products"
        style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", color: "var(--text-secondary)", fontSize: "0.8125rem", textDecoration: "none", marginBottom: "1.25rem" }}
        onMouseEnter={(e) => { e.currentTarget.style.color = "white"; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = "#94a3b8"; }}
      >
        <ArrowLeft style={{ width: "14px", height: "14px" }} /> Inapoi la produse
      </Link>

      {/* Product header */}
      <div style={{
        backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
        borderRadius: "0.75rem", padding: "1.5rem", marginBottom: "1rem",
      }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.5rem" }}>
              <h1 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>{product.name}</h1>
              {product.sku && (
                <button
                  type="button"
                  onClick={() => copyToClipboard(product.sku, "sku-main")}
                  title="Click pentru a copia SKU-ul"
                  style={{
                    padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                    backgroundColor: copiedKey === "sku-main" ? "rgba(34,197,94,0.35)" : "rgba(34,197,94,0.15)",
                    color: "#4ade80", fontFamily: "monospace", border: "none", cursor: "pointer",
                  }}
                >
                  {copiedKey === "sku-main" ? "Copiat!" : `SKU: ${product.sku}`}
                </button>
              )}
              {product.ean && (
                <button
                  type="button"
                  onClick={() => copyToClipboard(product.ean, "ean-main")}
                  title="Click pentru a copia EAN-ul"
                  style={{
                    padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                    backgroundColor: copiedKey === "ean-main" ? "rgba(234,179,8,0.35)" : "rgba(234,179,8,0.15)",
                    color: "#facc15", fontFamily: "monospace", border: "none", cursor: "pointer",
                  }}
                >
                  {copiedKey === "ean-main" ? "Copiat!" : `EAN: ${product.ean}`}
                </button>
              )}
              {product.source && (
                product.source_url ? (
                  <button
                    type="button"
                    onClick={() => copyToClipboard(product.source_url, "url-main")}
                    title="Click pentru a copia linkul sursei"
                    style={{
                      padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                      backgroundColor: copiedKey === "url-main" ? "rgba(147,51,234,0.35)" : "rgba(147,51,234,0.15)",
                      color: "#a78bfa", border: "none", cursor: "pointer",
                    }}
                  >
                    {copiedKey === "url-main" ? "Copiat!" : product.source}
                  </button>
                ) : (
                  <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: "rgba(147,51,234,0.15)", color: "#a78bfa" }}>
                    {product.source}
                  </span>
                )
              )}
            </div>
            {product.category && (
              <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "0.5rem" }}>Categorie: {product.category}</p>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
              {product.current_price && (
                <span style={{ fontSize: "1.5rem", fontWeight: 700, color: "#4ade80" }}>
                  {product.current_price} {product.currency}
                </span>
              )}
              <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                <TrendIcon style={{ width: "16px", height: "16px", color: trendConfig[trend].color }} />
                <span style={{ fontSize: "0.8125rem", color: trendConfig[trend].color }}>{trendConfig[trend].label}</span>
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              onClick={handleRefreshPrice}
              disabled={refreshing || !product.sources || product.sources.length === 0}
              title={!product.sources || product.sources.length === 0 ? "Produsul nu are nicio sursa scrapeable" : `Interogheaza ${product.sources.length} sursa/surse`}
              style={{
                display: "flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 0.875rem",
                borderRadius: "0.5rem",
                backgroundColor: "rgba(34,197,94,0.15)", color: "#4ade80",
                border: "none",
                cursor: refreshing || !product.sources || product.sources.length === 0 ? "not-allowed" : "pointer",
                fontSize: "0.8125rem", fontWeight: 500,
                opacity: refreshing || !product.sources || product.sources.length === 0 ? 0.55 : 1,
              }}
            >
              <RefreshCw style={{ width: "14px", height: "14px", animation: refreshing ? "spin 1s linear infinite" : "none" }} />
              {refreshing ? "Se actualizeaza..." : `Refresh pret (${product.sources?.length || 0})`}
            </button>
            <button
              onClick={handleAddToWatchlist}
              title="Adauga in watchlist"
              style={{
                display: "flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 0.875rem",
                borderRadius: "0.5rem", backgroundColor: "rgba(147,51,234,0.15)", color: "#a78bfa",
                border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
              }}
            >
              <Eye style={{ width: "14px", height: "14px" }} /> Watchlist
            </button>
            <button
              onClick={() => setAlertForm({ ...alertForm, show: !alertForm.show })}
              title="Creeaza alerta"
              style={{
                display: "flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 0.875rem",
                borderRadius: "0.5rem", backgroundColor: "rgba(234,179,8,0.15)", color: "#facc15",
                border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
              }}
            >
              <Bell style={{ width: "14px", height: "14px" }} /> Alerta
            </button>
            {product.source_url && (
              <a
                href={product.source_url} target="_blank" rel="noopener noreferrer"
                style={{
                  display: "flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 0.875rem",
                  borderRadius: "0.5rem", backgroundColor: "rgba(59,130,246,0.15)", color: "#60a5fa",
                  textDecoration: "none", fontSize: "0.8125rem", fontWeight: 500,
                }}
              >
                <ExternalLink style={{ width: "14px", height: "14px" }} /> Sursa
              </a>
            )}
            <button
              onClick={handleDeleteProduct}
              title="Sterge produs din baza de date"
              style={{
                display: "flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 0.875rem",
                borderRadius: "0.5rem", backgroundColor: "rgba(248,113,113,0.15)", color: "#f87171",
                border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
              }}
            >
              <Trash2 style={{ width: "14px", height: "14px" }} /> Sterge
            </button>
          </div>
        </div>

        {refreshResults && refreshResults.length > 0 && (
          <div style={{
            marginTop: "0.75rem", padding: "0.75rem", borderRadius: "0.5rem",
            backgroundColor: "rgba(15,23,42,0.6)", border: "1px solid var(--border-color)",
            display: "flex", flexDirection: "column", gap: "0.375rem",
          }}>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontWeight: 500, marginBottom: "0.25rem" }}>
              Rezultat refresh per sursa
            </div>
            {refreshResults.map((r, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem" }}>
                <span style={{
                  padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                  backgroundColor: "rgba(147,51,234,0.15)", color: "#a78bfa", minWidth: "100px", textAlign: "center",
                }}>{r.source}</span>
                {r.success ? (
                  r.changed ? (
                    <span style={{ color: "#86efac" }}>{r.old_price ?? "?"} -&gt; <strong>{r.new_price}</strong> {r.currency}</span>
                  ) : (
                    <span style={{ color: "var(--text-secondary)" }}>neschimbat: {r.new_price} {r.currency}</span>
                  )
                ) : (
                  <span style={{ color: "#fca5a5" }}>{r.error || "esec"}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Alert form inline */}
        {alertForm.show && (
          <form onSubmit={handleCreateAlert} style={{
            display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap",
            marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--border-color)",
          }}>
            <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>Anunta-ma cand pretul</span>
            <select
              value={alertForm.alert_type}
              onChange={(e) => setAlertForm({ ...alertForm, alert_type: e.target.value })}
              style={{
                backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                borderRadius: "0.375rem", padding: "0.375rem 0.625rem", color: "var(--text-primary)",
                fontSize: "0.8125rem", outline: "none", cursor: "pointer",
              }}
            >
              <option value="price_drop">scade sub</option>
              <option value="price_rise">creste peste</option>
            </select>
            <input
              type="number"
              step="0.01"
              min="0"
              value={alertForm.target_price}
              onChange={(e) => setAlertForm({ ...alertForm, target_price: e.target.value })}
              required
              placeholder="ex: 25.00"
              style={{
                backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                borderRadius: "0.375rem", padding: "0.375rem 0.625rem", color: "var(--text-primary)",
                fontSize: "0.8125rem", width: "120px", outline: "none",
              }}
            />
            <select
              value={alertForm.currency}
              onChange={(e) => setAlertForm({ ...alertForm, currency: e.target.value })}
              style={{
                backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                borderRadius: "0.375rem", padding: "0.375rem 0.625rem", color: "var(--text-primary)",
                fontSize: "0.8125rem", outline: "none", cursor: "pointer",
              }}
            >
              <option value="EUR">EUR</option>
              <option value="RON">RON</option>
              <option value="USD">USD</option>
            </select>
            <button type="submit" style={{
              padding: "0.375rem 0.875rem", borderRadius: "0.375rem", backgroundColor: "#2563eb",
              color: "var(--text-primary)", border: "none", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500,
            }}>
              Creeaza alerta
            </button>
          </form>
        )}
        {alertMsg && (
          <p style={{ marginTop: "0.75rem", fontSize: "0.8125rem", color: alertMsg.includes("succes") ? "#4ade80" : "#f87171" }}>
            {alertMsg}
          </p>
        )}
      </div>

      {product.sources && product.sources.length > 0 && (
        <div style={{
          backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderRadius: "0.75rem", padding: "1.25rem", marginBottom: "1rem",
        }}>
          <h2 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.75rem" }}>
            Surse stocate ({product.sources.length})
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {product.sources.map((s) => {
              const isCheapest = s.source === product.source && s.source_url === product.source_url;
              return (
                <div key={s.id} style={{
                  display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.625rem 0.75rem",
                  backgroundColor: "var(--bg-dark)", borderRadius: "0.5rem",
                  border: isCheapest ? "1px solid rgba(34,197,94,0.4)" : "1px solid var(--border-color)",
                }}>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(s.source_url, `src-url-${s.id}`)}
                    title="Click pentru a copia linkul sursei"
                    style={{
                      padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                      backgroundColor: copiedKey === `src-url-${s.id}` ? "rgba(147,51,234,0.35)" : "rgba(147,51,234,0.15)",
                      color: "#a78bfa", minWidth: "100px", textAlign: "center",
                      border: "none", cursor: "pointer",
                    }}
                  >
                    {copiedKey === `src-url-${s.id}` ? "Copiat!" : s.source}
                  </button>
                  <span style={{ fontSize: "0.9375rem", fontWeight: 600, color: isCheapest ? "#4ade80" : "white" }}>
                    {s.current_price ?? "—"} {s.currency}
                  </span>
                  {isCheapest && (
                    <span style={{ fontSize: "0.6875rem", color: "#4ade80", fontWeight: 500 }}>cea mai mica</span>
                  )}
                  <span style={{ flex: 1 }} />
                  {s.last_checked_at && (
                    <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>
                      Verificat: {new Date(s.last_checked_at).toLocaleString("ro-RO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </span>
                  )}
                  <a
                    href={s.source_url} target="_blank" rel="noopener noreferrer"
                    style={{
                      display: "flex", alignItems: "center", gap: "0.25rem", color: "#60a5fa",
                      fontSize: "0.75rem", textDecoration: "none",
                    }}
                  >
                    <ExternalLink style={{ width: "12px", height: "12px" }} /> Vezi
                  </a>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Price stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem", marginBottom: "1rem" }}>
        <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem", textAlign: "center" }}>
          <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>Pret minim</p>
          <p style={{ fontSize: "1.25rem", fontWeight: 700, color: "#4ade80", margin: 0 }}>{lowest_price ?? "—"} {product.currency}</p>
        </div>
        <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem", textAlign: "center" }}>
          <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>Pret mediu</p>
          <p style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>{average_price ?? "—"} {product.currency}</p>
        </div>
        <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "0.75rem", padding: "1rem", textAlign: "center" }}>
          <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>Pret maxim</p>
          <p style={{ fontSize: "1.25rem", fontWeight: 700, color: "#f87171", margin: 0 }}>{highest_price ?? "—"} {product.currency}</p>
        </div>
      </div>

      {/* Price chart */}
      <div style={{
        backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
        borderRadius: "0.75rem", padding: "1.5rem",
      }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1.25rem" }}>
          Evolutia pretului
        </h2>
        {chartData.length > 1 ? (
          <div style={{ width: "100%", height: "300px" }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <defs>
                  <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(51,65,85,0.5)" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: "rgba(51,65,85,0.5)" }}
                />
                <YAxis
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: "rgba(51,65,85,0.5)" }}
                  domain={["dataMin - 1", "dataMax + 1"]}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--bg-card)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "0.5rem",
                    fontSize: "0.8125rem",
                  }}
                  labelStyle={{ color: "var(--text-secondary)" }}
                  itemStyle={{ color: "#3b82f6" }}
                  formatter={(value) => [`${value} ${product.currency}`, "Pret"]}
                  labelFormatter={(label, payload) => payload?.[0]?.payload?.fullDate || label}
                />
                <Area
                  type="monotone"
                  dataKey="price"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  fill="url(#priceGradient)"
                  dot={{ fill: "#3b82f6", r: 3 }}
                  activeDot={{ r: 5, fill: "#60a5fa" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : chartData.length === 1 ? (
          <div style={{ textAlign: "center", padding: "2rem 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
            <p>Un singur punct de pret inregistrat: <strong style={{ color: "var(--text-primary)" }}>{chartData[0].price} {product.currency}</strong> la {chartData[0].fullDate}</p>
            <p style={{ marginTop: "0.25rem", fontSize: "0.8125rem" }}>Graficul va fi disponibil dupa mai multe inregistrari.</p>
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "2rem 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
            Nu exista inregistrari de pret pentru acest produs.
          </div>
        )}
      </div>

      {/* Price history table with source */}
      {price_history && price_history.length > 0 && (
        <div style={{
          backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderRadius: "0.75rem", padding: "1.5rem", marginTop: "1rem",
        }}>
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
            Istoric preturi detaliat
          </h2>
          <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
            Fiecare inregistrare arata sursa de unde a fost preluat pretul, pentru a putea compara intre magazine.
          </p>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-color)" }}>
                  <th style={{ textAlign: "left", padding: "0.625rem 0.75rem", color: "var(--text-secondary)", fontWeight: 500 }}>Data</th>
                  <th style={{ textAlign: "left", padding: "0.625rem 0.75rem", color: "var(--text-secondary)", fontWeight: 500 }}>Pret</th>
                  <th style={{ textAlign: "left", padding: "0.625rem 0.75rem", color: "var(--text-secondary)", fontWeight: 500 }}>Moneda</th>
                  <th style={{ textAlign: "left", padding: "0.625rem 0.75rem", color: "var(--text-secondary)", fontWeight: 500 }}>Sursa</th>
                  <th style={{ textAlign: "left", padding: "0.625rem 0.75rem", color: "var(--text-secondary)", fontWeight: 500 }}>Diferenta</th>
                </tr>
              </thead>
              <tbody>
                {price_history.map((ph, idx) => {
                  // price_history vine deja ordonat desc (cele mai noi primele) din backend.
                  // "next" în array este înregistrarea mai veche.
                  const older = price_history[idx + 1];
                  let diff = null;
                  if (older && older.price) {
                    diff = ph.price - older.price;
                  }
                  const sourceStyle = SOURCE_COLORS[ph.source] || { bg: "rgba(148,163,184,0.15)", fg: "#cbd5e1" };
                  return (
                    <tr key={ph.id} style={{ borderBottom: "1px solid rgba(51,65,85,0.4)" }}>
                      <td style={{ padding: "0.625rem 0.75rem", color: "var(--text-primary)" }}>
                        {new Date(ph.recorded_at).toLocaleString("ro-RO", {
                          day: "2-digit", month: "short", year: "numeric",
                          hour: "2-digit", minute: "2-digit",
                        })}
                      </td>
                      <td style={{ padding: "0.625rem 0.75rem", color: "var(--text-primary)", fontWeight: 600 }}>
                        {ph.price.toFixed(2)}
                      </td>
                      <td style={{ padding: "0.625rem 0.75rem", color: "var(--text-secondary)" }}>
                        {ph.currency}
                      </td>
                      <td style={{ padding: "0.625rem 0.75rem" }}>
                        {ph.source ? (
                          <span style={{
                            padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                            backgroundColor: sourceStyle.bg, color: sourceStyle.fg,
                          }}>
                            {ph.source}
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-secondary)" }}>—</span>
                        )}
                      </td>
                      <td style={{ padding: "0.625rem 0.75rem" }}>
                        {diff === null ? (
                          <span style={{ color: "var(--text-secondary)" }}>—</span>
                        ) : diff === 0 ? (
                          <span style={{ color: "var(--text-secondary)" }}>fara schimbare</span>
                        ) : (
                          <span style={{ color: diff < 0 ? "#4ade80" : "#f87171", fontWeight: 500 }}>
                            {diff > 0 ? "+" : ""}{diff.toFixed(2)} {ph.currency}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
