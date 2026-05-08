"use client";
import { useEffect, useState } from "react";
import { salesAPI, inventoryAPI } from "@/lib/api";
import { Receipt, Plus, Trash2, Pencil, TrendingUp, Coins, Euro, FileDown, Boxes } from "lucide-react";

const inputStyle = {
  backgroundColor: "#0f172a",
  border: "1px solid #334155",
  borderRadius: "0.5rem",
  color: "white",
  padding: "0.625rem 0.875rem",
  fontSize: "0.875rem",
  width: "100%",
  outline: "none",
};

const cardStyle = { backgroundColor: "#1e293b", border: "1px solid #334155" };

const emptyForm = {
  product_name: "",
  quantity: 1,
  sale_price: "",
  currency: "RON",
  cost_price: "",
  platform: "",
  buyer: "",
  notes: "",
  inventory_item_id: "",
};

export default function SalesPage() {
  const [sales, setSales] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [inventoryItems, setInventoryItems] = useState([]);

  const loadAll = async () => {
    setLoading(true);
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
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
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
      platform: sale.platform || "",
      buyer: sale.buyer || "",
      notes: sale.notes || "",
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
        inventory_item_id: form.inventory_item_id ? Number(form.inventory_item_id) : null,
      };
      if (editingId) {
        // La edit nu permitem schimbarea legaturii cu inventarul.
        delete payload.inventory_item_id;
        await salesAPI.updateSale(editingId, payload);
      } else {
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

  const handleDelete = async (id) => {
    if (!confirm("Sigur vrei sa stergi aceasta vanzare?")) return;
    try {
      await salesAPI.deleteSale(id);
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

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.875rem", fontWeight: 700, color: "white", display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <Receipt style={{ width: "2rem", height: "2rem", color: "#a78bfa" }} />
            Vanzari
          </h1>
          <p style={{ color: "#94a3b8", marginTop: "0.5rem" }}>Inregistreaza si monitorizeaza vanzarile efectuate</p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button onClick={handleExportPDF}
            style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.625rem 1rem", borderRadius: "0.5rem", backgroundColor: "transparent", color: "white", fontWeight: 500, border: "1px solid #334155", cursor: "pointer" }}>
            <FileDown style={{ width: "1rem", height: "1rem" }} /> Export PDF
          </button>
          <button onClick={openCreate}
            style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.625rem 1rem", borderRadius: "0.5rem", backgroundColor: "#9333ea", color: "white", fontWeight: 500, border: "none", cursor: "pointer" }}>
            <Plus style={{ width: "1rem", height: "1rem" }} /> Adauga vanzare
          </button>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.75rem" }}>
            <TrendingUp style={{ width: "1.125rem", height: "1.125rem", color: "#60a5fa" }} />
            <p style={{ color: "#94a3b8", fontSize: "0.875rem" }}>Vanzari</p>
          </div>
          <p style={{ fontSize: "1.75rem", fontWeight: 700, color: "white" }}>
            {stats?.total_sales ?? "-"}
          </p>
          <p style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.25rem" }}>
            {stats?.total_units_sold ?? 0} unitati vandute
          </p>
        </div>
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.75rem" }}>
            <Euro style={{ width: "1.125rem", height: "1.125rem", color: "#facc15" }} />
            <p style={{ color: "#94a3b8", fontSize: "0.875rem" }}>Venit total</p>
          </div>
          <p style={{ fontSize: "1.75rem", fontWeight: 700, color: "#4ade80" }}>
            {(stats?.total_revenue_eur ?? 0).toLocaleString("ro-RO", { minimumFractionDigits: 2 })} EUR
          </p>
        </div>
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.75rem" }}>
            <Coins style={{ width: "1.125rem", height: "1.125rem", color: "#a78bfa" }} />
            <p style={{ color: "#94a3b8", fontSize: "0.875rem" }}>Profit estimat</p>
          </div>
          <p style={{ fontSize: "1.75rem", fontWeight: 700, color: "#a78bfa" }}>
            {(stats?.total_profit_eur ?? 0).toLocaleString("ro-RO", { minimumFractionDigits: 2 })} EUR
          </p>
          <p style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.25rem" }}>Venit minus cost declarat</p>
        </div>
      </div>

      {/* Form modal */}
      {showForm && (
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1.5rem", marginBottom: "1.5rem" }}>
          <h2 style={{ color: "white", fontWeight: 600, marginBottom: "1rem" }}>
            {editingId ? "Editeaza vanzare" : "Inregistreaza vanzare noua"}
          </h2>
          <form onSubmit={handleSubmit}>
            {!editingId && inventoryItems.length > 0 && (
              <div style={{ marginBottom: "0.875rem", padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "rgba(34,197,94,0.06)", border: "1px solid rgba(34,197,94,0.2)" }}>
                <label style={{ color: "#4ade80", fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.375rem", marginBottom: "0.375rem", fontWeight: 600 }}>
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
                  <p style={{ color: "#94a3b8", fontSize: "0.6875rem", marginTop: "0.375rem" }}>
                    Stoc disponibil: <strong style={{ color: "#4ade80" }}>{selectedInventoryItem.quantity}</strong> · Pretul de cost si moneda au fost completate automat. Stocul se va scadea cu cantitatea vanduta.
                  </p>
                )}
              </div>
            )}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <div>
                <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Produs vandut *</label>
                <input required style={inputStyle} value={form.product_name} onChange={(e) => setForm({ ...form, product_name: e.target.value })} placeholder="Ex: iPhone 14" disabled={!!selectedInventoryItem} title={selectedInventoryItem ? "Numele este preluat din inventar" : ""} />
              </div>
              <div>
                <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>
                  Cantitate * {selectedInventoryItem ? <span style={{ color: "#64748b" }}>(max {selectedInventoryItem.quantity})</span> : null}
                </label>
                <input required type="number" min="1" max={selectedInventoryItem?.quantity || undefined} style={inputStyle} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
              </div>
              <div>
                <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Pret vanzare *</label>
                <input required type="number" step="0.01" min="0" style={inputStyle} value={form.sale_price} onChange={(e) => setForm({ ...form, sale_price: e.target.value })} />
              </div>
              <div>
                <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Moneda *</label>
                <select style={inputStyle} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                  <option value="RON">RON</option>
                  <option value="EUR">EUR</option>
                  <option value="USD">USD</option>
                </select>
              </div>
              <div>
                <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Pret achizitie (optional)</label>
                <input type="number" step="0.01" min="0" style={inputStyle} value={form.cost_price} onChange={(e) => setForm({ ...form, cost_price: e.target.value })} placeholder="pentru calcul profit" />
              </div>
              <div>
                <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Platforma vanzare</label>
                <input style={inputStyle} value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })} placeholder="eMAG, OLX, Okazii, magazin propriu..." />
              </div>
              <div style={{ gridColumn: "span 2" }}>
                <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Cumparator</label>
                <input style={inputStyle} value={form.buyer} onChange={(e) => setForm({ ...form, buyer: e.target.value })} placeholder="Nume sau email (optional)" />
              </div>
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Note</label>
              <textarea style={{ ...inputStyle, minHeight: "72px", resize: "vertical" }} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            {error && <p style={{ color: "#f87171", fontSize: "0.875rem", marginBottom: "0.75rem" }}>{error}</p>}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="submit" style={{ padding: "0.625rem 1rem", borderRadius: "0.5rem", backgroundColor: "#9333ea", color: "white", fontWeight: 500, border: "none", cursor: "pointer" }}>
                {editingId ? "Salveaza modificarile" : "Adauga vanzare"}
              </button>
              <button type="button" onClick={() => { setShowForm(false); setEditingId(null); }}
                style={{ padding: "0.625rem 1rem", borderRadius: "0.5rem", backgroundColor: "transparent", color: "#94a3b8", border: "1px solid #334155", cursor: "pointer" }}>
                Anuleaza
              </button>
            </div>
          </form>
        </div>
      )}

      {/* List */}
      {loading ? (
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "3rem", textAlign: "center" }}>
          <div style={{ width: "2.25rem", height: "2.25rem", border: "4px solid #9333ea", borderTop: "4px solid transparent", borderRadius: "50%", animation: "spin 1s linear infinite", margin: "0 auto" }} />
        </div>
      ) : sales.length === 0 ? (
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "3rem", textAlign: "center" }}>
          <Receipt style={{ width: "3.5rem", height: "3.5rem", color: "#475569", margin: "0 auto 1rem" }} />
          <p style={{ color: "white", marginBottom: "0.5rem" }}>Nicio vanzare inregistrata</p>
          <p style={{ color: "#94a3b8", fontSize: "0.875rem" }}>Adauga prima vanzare pentru a monitoriza performanta ta.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {sales.map((sale) => {
            const lineRevenue = (sale.sale_price || 0) * (sale.quantity || 0);
            const lineProfit = sale.cost_price != null ? ((sale.sale_price || 0) - sale.cost_price) * (sale.quantity || 0) : null;
            return (
              <div key={sale.id} style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1rem 1.25rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                    <h3 style={{ color: "white", fontWeight: 600, fontSize: "1rem" }}>{sale.product_name}</h3>
                    {sale.platform && (
                      <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: "rgba(147,51,234,0.15)", color: "#c4b5fd" }}>{sale.platform}</span>
                    )}
                  </div>
                  <div style={{ color: "#94a3b8", fontSize: "0.8125rem", marginTop: "0.25rem" }}>
                    {sale.quantity} x {sale.sale_price?.toFixed?.(2) ?? sale.sale_price} {sale.currency}
                    {sale.buyer ? ` · ${sale.buyer}` : ""}
                  </div>
                  {sale.notes && (
                    <p style={{ color: "#cbd5e1", fontSize: "0.8125rem", marginTop: "0.375rem" }}>{sale.notes}</p>
                  )}
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ color: "#4ade80", fontWeight: 700, fontSize: "1.125rem" }}>
                    {lineRevenue.toFixed(2)} {sale.currency}
                  </div>
                  {lineProfit != null && (
                    <div style={{ color: lineProfit >= 0 ? "#a78bfa" : "#f87171", fontSize: "0.75rem" }}>
                      profit: {lineProfit.toFixed(2)} {sale.currency}
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", gap: "0.375rem" }}>
                  <button onClick={() => openEdit(sale)} title="Editeaza"
                    style={{ padding: "0.5rem", borderRadius: "0.5rem", border: "none", backgroundColor: "transparent", color: "#94a3b8", cursor: "pointer" }}>
                    <Pencil style={{ width: "1.125rem", height: "1.125rem" }} />
                  </button>
                  <button onClick={() => handleDelete(sale.id)} title="Sterge"
                    style={{ padding: "0.5rem", borderRadius: "0.5rem", border: "none", backgroundColor: "transparent", color: "#f87171", cursor: "pointer" }}>
                    <Trash2 style={{ width: "1.125rem", height: "1.125rem" }} />
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
