"use client";
import { useEffect, useState } from "react";
import { salesAPI, inventoryAPI } from "@/lib/api";
import FeedErrorBanner from "@/components/shared/FeedErrorBanner";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import KpiCard from "@/components/shared/KpiCard";
import { inputStyle } from "@/lib/uiStyles";
import { Receipt, Plus, Trash2, Pencil, TrendingUp, Coins, Euro, FileDown, Boxes } from "lucide-react";

const labelStyle = {
  display: "block",
  fontFamily: "var(--font-mono)",
  fontSize: "8.5px",
  letterSpacing: ".15em",
  textTransform: "uppercase",
  color: "var(--text-mono)",
  marginBottom: "6px",
};

const emptyForm = {
  product_name: "",
  quantity: 1,
  sale_price: "",
  currency: "RON",
  cost_price: "",
  extra_costs: "",
  platform: "",
  buyer: "",
  category: "",
  notes: "",
  sold_at: "",
  inventory_item_id: "",
};

function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function formatRoDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  if (!y || !m || !d) return "—";
  return `${d}.${m}.${y}`;
}

export default function SalesPage() {
  const [sales, setSales] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [inventoryItems, setInventoryItems] = useState([]);
  const [search, setSearch] = useState("");

  const loadAll = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [salesRes, statsRes, invRes] = await Promise.all([
        salesAPI.getSales(),
        salesAPI.getStats(),
        inventoryAPI.getItems().catch(() => ({ data: [] })),
      ]);
      setSales(salesRes.data);
      setStats(statsRes.data);
      setInventoryItems(invRes.data || []);
    } catch (e) {
      console.error(e);
      setLoadError("Nu am putut încărca datele. Reîncearcă.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();

    // FlipRadar — GE-4b: deep-link din calculatorul de inventar (?inv=&qty=&pret=&extra=).
    // Citire one-shot din window.location (pattern GE-2); fetch propriu de inventar ca sa nu
    // depindem de ordinea incarcarii state-ului.
    try {
      const sp = new URLSearchParams(window.location.search);
      const invId = parseInt(sp.get("inv"));
      if (invId > 0) {
        const qtyP = parseInt(sp.get("qty")) || 1;
        const pretP = sp.get("pret") || "";
        const extraP = sp.get("extra") || "";
        inventoryAPI.getItems()
          .then((res) => {
            const item = (res.data || []).find((it) => it.id === invId);
            if (item) {
              setForm({
                ...emptyForm,
                sold_at: todayIso(),
                inventory_item_id: String(item.id),
                product_name: item.name,
                cost_price: String(item.purchase_price ?? ""),
                currency: item.currency || "RON",
                category: item.category || "",
                quantity: Math.min(qtyP, item.quantity),
                sale_price: pretP,
                extra_costs: extraP,
              });
            } else {
              // Articolul a fost sters intre timp: formular fara legatura, cu ce avem.
              setForm({ ...emptyForm, sold_at: todayIso(), quantity: qtyP,
                        sale_price: pretP, extra_costs: extraP });
            }
            setEditingId(null);
            setError("");
            setShowForm(true);
          })
          .catch(() => {});
      }
    } catch { /* URL invalid — ignoram */ }
  }, []);

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...emptyForm, sold_at: todayIso() });
    setError("");
    setShowForm(true);
  };

  const openEdit = (sale) => {
    setEditingId(sale.id);
    setForm({
      product_name: sale.product_name || "",
      quantity: sale.quantity || 1,
      sale_price: sale.sale_price ?? "",
      currency: sale.currency || "RON",
      cost_price: sale.cost_price ?? "",
      extra_costs: sale.extra_costs != null ? String(sale.extra_costs) : "",
      platform: sale.platform || "",
      buyer: sale.buyer || "",
      category: sale.category || "",
      notes: sale.notes || "",
      sold_at: (sale.sold_at || "").slice(0, 10),
      inventory_item_id: "",
    });
    setError("");
    setShowForm(true);
  };

  const selectFromInventory = (id) => {
    if (!id) {
      setForm((prev) => ({ ...prev, inventory_item_id: "" }));
      return;
    }
    const item = inventoryItems.find((it) => it.id === Number(id));
    if (!item) return;
    setForm((prev) => ({
      ...prev,
      inventory_item_id: String(item.id),
      product_name: item.name,
      cost_price: String(item.purchase_price ?? ""),
      currency: item.currency || prev.currency,
      category: item.category || "",
      quantity: prev.quantity > item.quantity ? item.quantity : prev.quantity,
    }));
  };

  // Cand selectam un articol din inventar, restrictionam cantitatea maxima
  // si gasim usor articolul curent (pentru afisarea stocului disponibil).
  const selectedInventoryItem = form.inventory_item_id
    ? inventoryItems.find((it) => it.id === Number(form.inventory_item_id))
    : null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const payload = {
        ...form,
        quantity: parseInt(form.quantity) || 1,
        sale_price: parseFloat(form.sale_price) || 0,
        cost_price: form.cost_price === "" ? null : parseFloat(form.cost_price),
        extra_costs: form.extra_costs === "" ? null : parseFloat(form.extra_costs),
        sold_at: form.sold_at,
        inventory_item_id: form.inventory_item_id ? Number(form.inventory_item_id) : null,
      };
      if (editingId) {
        // La edit nu permitem schimbarea legaturii cu inventarul.
        delete payload.inventory_item_id;
        // GE-3: golirea campului Categorie sterge intentionat categoria (NULL in DB).
        payload.category = (form.category || "").trim() || null;
        await salesAPI.updateSale(editingId, payload);
      } else {
        // GE-3: trimitem category DOAR daca userul a completat-o; altfel o eliminam, ca
        // setdefault-ul din backend sa poata copia categoria din inventar (category=""
        // ar trece de exclude_none si ar bloca copierea).
        const cat = (form.category || "").trim();
        if (cat) payload.category = cat;
        else delete payload.category;
        await salesAPI.createSale(payload);
      }
      setShowForm(false);
      setForm(emptyForm);
      setEditingId(null);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Eroare la salvare");
    }
  };

  const handleDelete = async (sale) => {
    let msg = "Sigur vrei sa stergi aceasta vanzare?";
    if (sale.inventory_item_id) {
      msg += " Stocul (" + sale.quantity + " buc.) va fi restituit in inventar.";
    }
    if (!confirm(msg)) return;
    try {
      await salesAPI.deleteSale(sale.id);
      await loadAll();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la stergere");
    }
  };

  const handleExportPDF = async () => {
    try {
      const res = await salesAPI.exportPDF();
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      const today = new Date().toISOString().slice(0, 10).replaceAll("-", "");
      a.download = `vanzari_${today}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la export PDF");
    }
  };

  // GE-6c: filtrare client-side DOAR pe lista afisata (statisticile vin din /api/sales/stats).
  const q = search.trim().toLowerCase();
  const visibleSales = q
    ? sales.filter((s) =>
        [s.product_name, s.platform, s.buyer, s.category].some((v) =>
          (v || "").toLowerCase().includes(q)
        )
      )
    : sales;

  return (
    <div>
      <TopBar path={["GESTIUNE", "REGISTRU VÂNZĂRI"]}>
        <button onClick={openCreate} className="btn-cyan">
          <Plus style={{ width: "13px", height: "13px" }} strokeWidth={2.2} /> Adaugă vânzare
        </button>
      </TopBar>

      <PageHeading
        icon={Receipt}
        title="Registru Vânzări"
        subtitle={<>Înregistrează și monitorizează vânzările efectuate — <Hl>{stats?.total_sales ?? 0} vânzări</Hl>, {stats?.total_units_sold ?? 0} unități.</>}
      >
        <button onClick={handleExportPDF} className="btn-neutral">
          <FileDown style={{ width: "13px", height: "13px" }} strokeWidth={1.8} /> Export PDF
        </button>
      </PageHeading>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(225px,1fr))", gap: "14px", marginTop: "16px" }}>
        <KpiCard
          idx="01"
          icon={TrendingUp}
          label="Vânzări"
          value={stats?.total_sales ?? "—"}
          chip={`${stats?.total_units_sold ?? 0} unități`}
          chipTone="cyan"
          note="vândute"
        />
        <KpiCard
          idx="02"
          icon={Euro}
          label="Venit total"
          value={(stats?.total_revenue_eur ?? 0).toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          unit="EUR"
          note="toate vânzările"
        />
        <KpiCard
          idx="03"
          icon={Coins}
          label="Profit estimat"
          value={(stats?.total_profit_eur ?? 0).toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          unit="EUR"
          chip={stats?.sales_without_cost > 0 ? `${stats.sales_without_cost} fără cost` : null}
          chipTone="warn"
          note="venit minus cost declarat"
        />
      </div>

      {/* Form modal */}
      {showForm && (
        <div className="glass-panel" style={{ padding: "20px", marginTop: "14px" }}>
          <h2 style={{ color: "var(--text-primary)", fontWeight: 600, fontSize: "15px", marginBottom: "14px" }}>
            {editingId ? "Editeaza vanzare" : "Inregistreaza vanzare noua"}
          </h2>
          <form onSubmit={handleSubmit}>
            {!editingId && inventoryItems.length > 0 && (
              <div style={{ marginBottom: "14px", padding: "12px", borderRadius: "12px", background: "rgba(74,222,128,0.06)", border: "1px solid rgba(74,222,128,0.24)" }}>
                <label style={{ color: "#4ade80", fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: ".15em", textTransform: "uppercase", display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                  <Boxes style={{ width: "0.875rem", height: "0.875rem" }} />
                  Preia produs din inventar (optional)
                </label>
                <select
                  value={form.inventory_item_id}
                  onChange={(e) => selectFromInventory(e.target.value)}
                  style={inputStyle}
                >
                  <option value="">— Vanzare independenta (introduci manual) —</option>
                  {inventoryItems.map((it) => (
                    <option key={it.id} value={it.id}>
                      {it.name} (stoc: {it.quantity}, cost: {Number(it.purchase_price).toFixed(2)} {it.currency})
                    </option>
                  ))}
                </select>
                {selectedInventoryItem && (
                  <p style={{ color: "var(--text-dim)", fontSize: "10.5px", marginTop: "6px" }}>
                    Stoc disponibil: <strong style={{ color: "#4ade80" }}>{selectedInventoryItem.quantity}</strong> · Pretul de cost si moneda au fost completate automat. Stocul se va scadea cu cantitatea vanduta.
                  </p>
                )}
              </div>
            )}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <div>
                <label style={labelStyle}>Produs vandut *</label>
                <input required style={inputStyle} value={form.product_name} onChange={(e) => setForm({ ...form, product_name: e.target.value })} placeholder="Ex: iPhone 14" disabled={!!selectedInventoryItem} title={selectedInventoryItem ? "Numele este preluat din inventar" : ""} />
              </div>
              <div>
                <label style={labelStyle}>
                  Cantitate * {selectedInventoryItem ? <span style={{ color: "var(--text-muted)" }}>(max {selectedInventoryItem.quantity})</span> : null}
                </label>
                <input required type="number" min="1" max={selectedInventoryItem?.quantity || undefined} style={inputStyle} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Pret vanzare *</label>
                <input required type="number" step="0.01" min="0" style={inputStyle} value={form.sale_price} onChange={(e) => setForm({ ...form, sale_price: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Moneda *</label>
                <select style={inputStyle} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                  <option value="RON">RON</option>
                  <option value="EUR">EUR</option>
                  <option value="USD">USD</option>
                </select>
              </div>
              <div>
                <label style={labelStyle}>Pret achizitie (optional)</label>
                <input type="number" step="0.01" min="0" style={inputStyle} value={form.cost_price} onChange={(e) => setForm({ ...form, cost_price: e.target.value })} placeholder="pentru calcul profit" />
              </div>
              <div>
                <label style={labelStyle}>Platforma vanzare</label>
                <input style={inputStyle} value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })} placeholder="eMAG, OLX, Okazii, magazin propriu..." />
              </div>
              <div>
                <label style={labelStyle}>Data vanzarii *</label>
                <input required type="date" max={todayIso()} style={inputStyle} value={form.sold_at} onChange={(e) => setForm({ ...form, sold_at: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Cumparator</label>
                <input style={inputStyle} value={form.buyer} onChange={(e) => setForm({ ...form, buyer: e.target.value })} placeholder="Nume sau email (optional)" />
              </div>
              <div>
                <label style={labelStyle}>Categorie</label>
                <input type="text" style={inputStyle} value={form.category} placeholder="ex: Electronice" onChange={(e) => setForm({ ...form, category: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Costuri suplimentare</label>
                <input type="number" step="0.01" min="0" style={inputStyle} value={form.extra_costs} placeholder="transport, taxe, comision" onChange={(e) => setForm({ ...form, extra_costs: e.target.value })} />
              </div>
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label style={labelStyle}>Note</label>
              <textarea style={{ ...inputStyle, minHeight: "72px", resize: "vertical" }} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            {error && <p style={{ color: "#f87171", fontSize: "12.5px", marginBottom: "12px" }}>{error}</p>}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="submit" className="btn-green">
                {editingId ? "Salveaza modificarile" : "Adauga vanzare"}
              </button>
              <button type="button" onClick={() => { setShowForm(false); setEditingId(null); }} className="btn-neutral">
                Anuleaza
              </button>
            </div>
          </form>
        </div>
      )}

      <FeedErrorBanner message={loadError} onRetry={loadAll} />

      <input type="text" style={{ ...inputStyle, marginTop: "14px" }}
        placeholder="Caută după produs, platformă, cumpărător sau categorie…"
        value={search} onChange={(e) => setSearch(e.target.value)} />

      {/* List */}
      {loading ? (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "14px" }}>
          <div style={{ width: "2.25rem", height: "2.25rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite", margin: "0 auto" }} />
        </div>
      ) : sales.length === 0 ? (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "14px" }}>
          <Receipt style={{ width: "2.5rem", height: "2.5rem", color: "var(--text-mono)", margin: "0 auto 14px", display: "block" }} strokeWidth={1.5} />
          <p style={{ color: "var(--text-primary)", marginBottom: "6px", fontSize: "13px" }}>Nicio vanzare inregistrata</p>
          <p style={{ color: "var(--text-dim)", fontSize: "12.5px" }}>Adauga prima vanzare pentru a monitoriza performanta ta.</p>
        </div>
      ) : visibleSales.length === 0 ? (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "14px" }}>
          <Receipt style={{ width: "2.5rem", height: "2.5rem", color: "var(--text-mono)", margin: "0 auto 14px", display: "block" }} strokeWidth={1.5} />
          <p style={{ color: "var(--text-dim)", fontSize: "12.5px" }}>Niciun rezultat pentru cautarea curenta.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "14px" }}>
          {visibleSales.map((sale) => {
            const lineRevenue = (sale.sale_price || 0) * (sale.quantity || 0);
            const lineProfit = sale.cost_price != null ? ((sale.sale_price || 0) - sale.cost_price) * (sale.quantity || 0) - (sale.extra_costs || 0) : null;
            return (
              <div key={sale.id} className="glass-panel lift-hover" style={{ padding: "14px 18px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "16px", flexWrap: "wrap" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                    <h3 style={{ color: "var(--text-primary)", fontWeight: 600, fontSize: "14px", margin: 0 }}>{sale.product_name}</h3>
                    {sale.platform && (
                      <span style={{ fontFamily: "var(--font-mono)", padding: "2.5px 7px", borderRadius: "7px", fontSize: "8.5px", letterSpacing: ".08em", textTransform: "uppercase", background: "rgba(147,51,234,0.14)", border: "1px solid rgba(147,51,234,0.4)", color: "#c4b5fd" }}>{sale.platform}</span>
                    )}
                  </div>
                  <div style={{ color: "var(--text-dim)", fontSize: "11.5px", marginTop: "5px" }}>
                    {formatRoDate(sale.sold_at)} · {sale.quantity} x {sale.sale_price?.toFixed?.(2) ?? sale.sale_price} {sale.currency}
                    {sale.buyer ? ` · ${sale.buyer}` : ""}
                    {sale.category ? ` · ${sale.category}` : ""}
                  </div>
                  {sale.notes && (
                    <p style={{ color: "var(--text-muted)", fontSize: "11.5px", marginTop: "6px" }}>{sale.notes}</p>
                  )}
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ color: "#ffffff", fontWeight: 700, fontSize: "18px", letterSpacing: "-.4px" }}>
                    {lineRevenue.toFixed(2)} {sale.currency}
                  </div>
                  {lineProfit != null && (
                    <div style={{ color: lineProfit >= 0 ? "#4ade80" : "#f87171", fontSize: "11.5px", marginTop: "3px" }}>
                      profit: {lineProfit.toFixed(2)} {sale.currency}
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", gap: "0.375rem" }}>
                  <button onClick={() => openEdit(sale)} title="Editeaza" className="btn-icon">
                    <Pencil style={{ width: "13px", height: "13px" }} strokeWidth={1.8} />
                  </button>
                  <button onClick={() => handleDelete(sale)} title="Sterge" className="btn-icon danger">
                    <Trash2 style={{ width: "13px", height: "13px" }} strokeWidth={1.8} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
