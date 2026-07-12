"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { inventoryAPI } from "@/lib/api";
import FeedErrorBanner from "@/components/shared/FeedErrorBanner";
import { Boxes, Plus, Trash2, Pencil, Package, Euro, Calculator, X, TrendingUp, TrendingDown, Upload, FileDown } from "lucide-react";

const inputStyle = {
  backgroundColor: "var(--bg-dark)",
  border: "1px solid var(--border-color)",
  borderRadius: "0.5rem",
  color: "var(--text-primary)",
  padding: "0.625rem 0.875rem",
  fontSize: "0.875rem",
  width: "100%",
  outline: "none",
};

const cardStyle = { backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)" };

const gridCols = {
  display: "grid",
  gridTemplateColumns: "2fr 1fr 80px 120px 100px 110px",
  gap: "0.75rem",
  alignItems: "center",
};

const headerColStyle = {
  fontSize: "0.6875rem",
  fontWeight: 600,
  color: "var(--text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const emptyForm = {
  name: "",
  category: "",
  sku: "",
  quantity: 1,
  purchase_price: "",
  currency: "RON",
  source: "",
  notes: "",
};

export default function InventoryPage() {
  const router = useRouter();
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [calcItem, setCalcItem] = useState(null);
  const [calcForm, setCalcForm] = useState({
    sell_price: "",
    qty: 1,
    transport: "",
    taxe: "",
    comision: "",
    alte_cheltuieli: "",
  });
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState(null);

  const loadAll = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [itemsRes, statsRes] = await Promise.all([
        inventoryAPI.getItems(),
        inventoryAPI.getStats(),
      ]);
      setItems(itemsRes.data);
      setStats(statsRes.data);
    } catch (e) {
      console.error(e);
      setLoadError("Nu am putut încărca datele. Reîncearcă.");
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

  const openEdit = (item) => {
    setEditingId(item.id);
    setForm({
      name: item.name || "",
      category: item.category || "",
      sku: item.sku || "",
      quantity: item.quantity || 1,
      purchase_price: item.purchase_price ?? "",
      currency: item.currency || "RON",
      source: item.source || "",
      notes: item.notes || "",
    });
    setError("");
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const payload = {
        ...form,
        quantity: parseInt(form.quantity) || 1,
        purchase_price: parseFloat(form.purchase_price) || 0,
      };
      if (editingId) {
        await inventoryAPI.updateItem(editingId, payload);
      } else {
        await inventoryAPI.createItem(payload);
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
    if (!confirm("Sigur vrei sa stergi acest articol din inventar?")) return;
    try {
      await inventoryAPI.deleteItem(id);
      await loadAll();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la stergere");
    }
  };

  const handleDownloadTemplate = async () => {
    try {
      const res = await inventoryAPI.downloadTemplate();
      const blob = new Blob([res.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "template_inventar.xlsx";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la descarcarea template-ului");
    }
  };

  const handleImportExcel = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // reset input ca user-ul sa poata reincarca acelasi fisier
    if (!file) return;
    setImporting(true);
    setImportMsg(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await inventoryAPI.importExcel(formData);
      setImportMsg({
        kind: res.data.imported > 0 ? "success" : "warning",
        text: `Importat: ${res.data.imported} · Sarit: ${res.data.skipped}` +
          (res.data.errors?.length ? ` · Erori: ${res.data.errors.join("; ")}` : ""),
      });
      await loadAll();
    } catch (err) {
      setImportMsg({ kind: "error", text: err.response?.data?.detail || "Eroare la import" });
    } finally {
      setImporting(false);
    }
  };

  const openCalc = (item) => {
    setCalcItem(item);
    setCalcForm({
      sell_price: "",
      qty: item.quantity || 1,
      transport: "",
      taxe: "",
      comision: "",
      alte_cheltuieli: "",
    });
  };

  const closeCalc = () => {
    setCalcItem(null);
  };

  // Calcule profit pe articol curent (live, fara backend).
  const calcResult = (() => {
    if (!calcItem) return null;
    const buy = Number(calcItem.purchase_price) || 0;
    const sell = parseFloat(calcForm.sell_price) || 0;
    const qty = parseInt(calcForm.qty) || 0;
    const transport = parseFloat(calcForm.transport) || 0;
    const taxe = parseFloat(calcForm.taxe) || 0;
    const comision = parseFloat(calcForm.comision) || 0;
    const alte = parseFloat(calcForm.alte_cheltuieli) || 0;
    const extraTotal = transport + taxe + comision + alte;
    const totalCost = buy * qty + extraTotal;
    const totalRevenue = sell * qty;
    const profit = totalRevenue - totalCost;
    const roi = totalCost > 0 ? (profit / totalCost) * 100 : 0;
    const margin = totalRevenue > 0 ? (profit / totalRevenue) * 100 : 0;
    return { totalCost, totalRevenue, profit, roi, margin, extraTotal };
  })();

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.875rem", fontWeight: 700, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <Boxes style={{ width: "2rem", height: "2rem", color: "#22c55e" }} />
            Inventar
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>Evidenta produselor pe care le ai pe stoc</p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button onClick={handleDownloadTemplate}
            title="Descarca template Excel pentru import"
            style={{ display: "flex", alignItems: "center", gap: "0.375rem", padding: "0.625rem 0.875rem", borderRadius: "0.5rem", backgroundColor: "transparent", color: "var(--text-secondary)", fontWeight: 500, border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.8125rem" }}>
            <FileDown style={{ width: "0.875rem", height: "0.875rem" }} /> Template Excel
          </button>
          <label
            title="Importa articole dintr-un fisier Excel"
            style={{ display: "flex", alignItems: "center", gap: "0.375rem", padding: "0.625rem 0.875rem", borderRadius: "0.5rem", backgroundColor: "#3b82f6", color: "var(--text-primary)", fontWeight: 500, border: "none", cursor: importing ? "wait" : "pointer", fontSize: "0.8125rem", opacity: importing ? 0.6 : 1 }}>
            <Upload style={{ width: "0.875rem", height: "0.875rem" }} /> {importing ? "Se importa..." : "Importa Excel"}
            <input type="file" accept=".xlsx,.xls" onChange={handleImportExcel} disabled={importing} style={{ display: "none" }} />
          </label>
          <button onClick={openCreate}
            style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.625rem 1rem", borderRadius: "0.5rem", backgroundColor: "#22c55e", color: "var(--text-primary)", fontWeight: 500, border: "none", cursor: "pointer" }}>
            <Plus style={{ width: "1rem", height: "1rem" }} /> Adauga produs
          </button>
        </div>
      </div>

      {importMsg && (
        <div style={{
          marginBottom: "1rem", padding: "0.75rem 1rem", borderRadius: "0.5rem", fontSize: "0.875rem",
          backgroundColor: importMsg.kind === "success" ? "rgba(34,197,94,0.1)" : importMsg.kind === "error" ? "rgba(239,68,68,0.1)" : "rgba(251,146,60,0.1)",
          border: `1px solid ${importMsg.kind === "success" ? "rgba(34,197,94,0.3)" : importMsg.kind === "error" ? "rgba(239,68,68,0.3)" : "rgba(251,146,60,0.3)"}`,
          color: importMsg.kind === "success" ? "#4ade80" : importMsg.kind === "error" ? "#f87171" : "#fb923c",
          display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem",
        }}>
          <span>{importMsg.text}</span>
          <button onClick={() => setImportMsg(null)} style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", padding: "0.25rem", display: "flex" }}>
            <X style={{ width: "0.875rem", height: "0.875rem" }} />
          </button>
        </div>
      )}

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.75rem" }}>
            <Package style={{ width: "1.125rem", height: "1.125rem", color: "#60a5fa" }} />
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>Articole</p>
          </div>
          <p style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)" }}>
            {stats?.total_items ?? "-"}
          </p>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            {stats?.total_units ?? 0} unitati totale
          </p>
        </div>
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.75rem" }}>
            <Euro style={{ width: "1.125rem", height: "1.125rem", color: "#a78bfa" }} />
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>Valoare totala</p>
          </div>
          <p style={{ fontSize: "1.75rem", fontWeight: 700, color: "#a78bfa" }}>
            {(stats?.total_value_eur ?? 0).toLocaleString("ro-RO", { minimumFractionDigits: 2 })} EUR
          </p>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Valorile in RON sunt convertite automat la cursul BNR.</p>
        </div>
      </div>

      {/* Form modal */}
      {showForm && (
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "1.5rem", marginBottom: "1.5rem" }}>
          <h2 style={{ color: "var(--text-primary)", fontWeight: 600, marginBottom: "1rem" }}>
            {editingId ? "Editeaza articol" : "Adauga articol nou"}
          </h2>
          <form onSubmit={handleSubmit}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <div>
                <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Nume *</label>
                <input required style={inputStyle} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ex: Nurofen 200mg" />
              </div>
              <div>
                <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Categorie</label>
                <input style={inputStyle} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Ex: Medicamente" />
              </div>
              <div>
                <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>SKU / Cod produs</label>
                <input style={inputStyle} value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
              </div>
              <div>
                <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Cantitate *</label>
                <input required type="number" min="1" style={inputStyle} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
              </div>
              <div>
                <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Pret achizitie *</label>
                <input required type="number" step="0.01" min="0" style={inputStyle} value={form.purchase_price} onChange={(e) => setForm({ ...form, purchase_price: e.target.value })} placeholder="0.00" />
              </div>
              <div>
                <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Moneda *</label>
                <select style={inputStyle} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                  <option value="RON">RON</option>
                  <option value="EUR">EUR</option>
                  <option value="USD">USD</option>
                </select>
              </div>
              <div>
                <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Sursa / Magazin</label>
                <input style={inputStyle} value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder="Ex: altex.ro" />
              </div>
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Note</label>
              <textarea style={{ ...inputStyle, minHeight: "72px", resize: "vertical" }} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Detalii optionale" />
            </div>
            {error && <p style={{ color: "#f87171", fontSize: "0.875rem", marginBottom: "0.75rem" }}>{error}</p>}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="submit" style={{ padding: "0.625rem 1rem", borderRadius: "0.5rem", backgroundColor: "#22c55e", color: "var(--text-primary)", fontWeight: 500, border: "none", cursor: "pointer" }}>
                {editingId ? "Salveaza modificarile" : "Adauga"}
              </button>
              <button type="button" onClick={() => { setShowForm(false); setEditingId(null); }}
                style={{ padding: "0.625rem 1rem", borderRadius: "0.5rem", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer" }}>
                Anuleaza
              </button>
            </div>
          </form>
        </div>
      )}

      <FeedErrorBanner message={loadError} onRetry={loadAll} />

      {/* List */}
      {loading ? (
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "3rem", textAlign: "center" }}>
          <div style={{ width: "2.25rem", height: "2.25rem", border: "4px solid #22c55e", borderTop: "4px solid transparent", borderRadius: "50%", animation: "spin 1s linear infinite", margin: "0 auto" }} />
        </div>
      ) : items.length === 0 ? (
        <div style={{ ...cardStyle, borderRadius: "0.75rem", padding: "3rem", textAlign: "center" }}>
          <Boxes style={{ width: "3.5rem", height: "3.5rem", color: "var(--text-secondary)", margin: "0 auto 1rem" }} />
          <p style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>Inventarul tau este gol</p>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>Adauga primele produse pentru a urmari stocul si valoarea.</p>
        </div>
      ) : (
        <div style={{ ...cardStyle, borderRadius: "0.875rem", overflow: "hidden" }}>
          <div style={{ ...gridCols, padding: "0.75rem 1rem", borderBottom: "1px solid var(--border-color)" }}>
            {["Produs", "Categorie", "Cant.", "Pret unitar", "Valoare", ""].map((h) => (
              <span key={h || "actions"} style={headerColStyle}>{h}</span>
            ))}
          </div>
          {items.map((item, idx) => (
            <div key={item.id}
              style={{
                ...gridCols,
                padding: "0.875rem 1rem",
                borderBottom: idx === items.length - 1 ? "none" : "1px solid rgba(51,65,85,0.5)",
                alignItems: "center",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", flexWrap: "wrap" }}>
                  <span style={{ color: "var(--text-primary)", fontWeight: 500, fontSize: "0.875rem" }}>{item.name}</span>
                  {item.source && (
                    <span style={{ padding: "0.0625rem 0.375rem", borderRadius: "0.25rem", fontSize: "0.625rem", backgroundColor: "rgba(236,72,153,0.15)", color: "#f472b6" }}>{item.source}</span>
                  )}
                </div>
                {(item.sku || item.notes) && (
                  <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
                    {item.sku || "—"}{item.notes ? ` · ${item.notes}` : ""}
                  </p>
                )}
              </div>
              <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{item.category || "—"}</span>
              <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>{item.quantity}</span>
              <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                {(item.purchase_price?.toFixed?.(2) ?? item.purchase_price)} {item.currency}
              </span>
              <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "#4ade80" }}>
                {((item.purchase_price || 0) * (item.quantity || 0)).toFixed(2)} {item.currency}
              </span>
              <div style={{ display: "flex", gap: "0.25rem", justifyContent: "flex-end" }}>
                <button onClick={() => openCalc(item)} title="Calculeaza profit"
                  style={{ padding: "0.375rem", borderRadius: "0.375rem", border: "none", backgroundColor: "transparent", color: "#60a5fa", cursor: "pointer", display: "flex" }}>
                  <Calculator style={{ width: "0.875rem", height: "0.875rem" }} />
                </button>
                <button onClick={() => openEdit(item)} title="Editeaza"
                  style={{ padding: "0.375rem", borderRadius: "0.375rem", border: "none", backgroundColor: "transparent", color: "var(--text-secondary)", cursor: "pointer", display: "flex" }}>
                  <Pencil style={{ width: "0.875rem", height: "0.875rem" }} />
                </button>
                <button onClick={() => handleDelete(item.id)} title="Sterge"
                  style={{ padding: "0.375rem", borderRadius: "0.375rem", border: "none", backgroundColor: "transparent", color: "#f87171", cursor: "pointer", display: "flex" }}>
                  <Trash2 style={{ width: "0.875rem", height: "0.875rem" }} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {calcItem && (
        <div
          onClick={closeCalc}
          style={{
            position: "fixed", inset: 0, zIndex: 100,
            backgroundColor: "rgba(0,0,0,0.6)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "1rem",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              ...cardStyle,
              borderRadius: "0.875rem",
              padding: "1.5rem",
              maxWidth: "560px",
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Calculator style={{ width: "1.25rem", height: "1.25rem", color: "#60a5fa" }} />
                <h2 style={{ color: "var(--text-primary)", fontWeight: 600, fontSize: "1.0625rem", margin: 0 }}>
                  Calculator profit
                </h2>
              </div>
              <button onClick={closeCalc}
                style={{ padding: "0.375rem", borderRadius: "0.375rem", border: "none", backgroundColor: "transparent", color: "var(--text-secondary)", cursor: "pointer", display: "flex" }}>
                <X style={{ width: "1rem", height: "1rem" }} />
              </button>
            </div>

            <div style={{ marginBottom: "1rem", padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "rgba(96,165,250,0.08)", border: "1px solid rgba(96,165,250,0.2)" }}>
              <p style={{ fontSize: "0.875rem", color: "var(--text-primary)", fontWeight: 500, marginBottom: "0.25rem" }}>{calcItem.name}</p>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                Pret achizitie: <span style={{ color: "var(--text-primary)" }}>{Number(calcItem.purchase_price).toFixed(2)} {calcItem.currency}</span>
                {" · "}
                Stoc: <span style={{ color: "var(--text-primary)" }}>{calcItem.quantity}</span>
              </p>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <div>
                <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Pret vanzare ({calcItem.currency}) *</label>
                <input type="number" step="0.01" min="0"
                  value={calcForm.sell_price}
                  onChange={(e) => setCalcForm({ ...calcForm, sell_price: e.target.value })}
                  placeholder="0.00"
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Cantitate *</label>
                <input type="number" min="1" max={calcItem.quantity}
                  value={calcForm.qty}
                  onChange={(e) => setCalcForm({ ...calcForm, qty: e.target.value })}
                  style={inputStyle}
                />
              </div>
            </div>

            <div style={{ marginBottom: "0.75rem" }}>
              <p style={{ fontSize: "0.6875rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.5rem", fontWeight: 600 }}>
                Costuri suplimentare (optional)
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.5rem" }}>
                <div>
                  <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Transport</label>
                  <input type="number" step="0.01" min="0"
                    value={calcForm.transport}
                    onChange={(e) => setCalcForm({ ...calcForm, transport: e.target.value })}
                    placeholder="0.00"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Taxe</label>
                  <input type="number" step="0.01" min="0"
                    value={calcForm.taxe}
                    onChange={(e) => setCalcForm({ ...calcForm, taxe: e.target.value })}
                    placeholder="0.00"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Comision platforma</label>
                  <input type="number" step="0.01" min="0"
                    value={calcForm.comision}
                    onChange={(e) => setCalcForm({ ...calcForm, comision: e.target.value })}
                    placeholder="0.00"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={{ color: "var(--text-secondary)", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Alte cheltuieli</label>
                  <input type="number" step="0.01" min="0"
                    value={calcForm.alte_cheltuieli}
                    onChange={(e) => setCalcForm({ ...calcForm, alte_cheltuieli: e.target.value })}
                    placeholder="0.00"
                    style={inputStyle}
                  />
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.5rem", marginBottom: "1rem" }}>
              <div style={{ padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)" }}>
                <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.25rem" }}>Venit total</p>
                <p style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  {calcResult.totalRevenue.toFixed(2)} {calcItem.currency}
                </p>
              </div>
              <div style={{ padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)" }}>
                <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.25rem" }}>Cost total</p>
                <p style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  {calcResult.totalCost.toFixed(2)} {calcItem.currency}
                </p>
              </div>
            </div>

            <div style={{
              padding: "1rem", borderRadius: "0.5rem",
              backgroundColor: calcResult.profit >= 0 ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
              border: `1px solid ${calcResult.profit >= 0 ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
              marginBottom: "1rem",
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                  {calcResult.profit >= 0
                    ? <TrendingUp style={{ width: "1rem", height: "1rem", color: "#4ade80" }} />
                    : <TrendingDown style={{ width: "1rem", height: "1rem", color: "#f87171" }} />}
                  <p style={{ fontSize: "0.6875rem", color: calcResult.profit >= 0 ? "#4ade80" : "#f87171", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
                    Profit estimat
                  </p>
                </div>
                <p style={{ fontSize: "1.5rem", fontWeight: 700, color: calcResult.profit >= 0 ? "#4ade80" : "#f87171" }}>
                  {calcResult.profit >= 0 ? "+" : ""}{calcResult.profit.toFixed(2)} {calcItem.currency}
                </p>
              </div>
              <div style={{ display: "flex", gap: "1rem", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                <span>ROI: <strong style={{ color: calcResult.profit >= 0 ? "#4ade80" : "#f87171" }}>{calcResult.roi.toFixed(1)}%</strong></span>
                <span>Marja: <strong style={{ color: calcResult.profit >= 0 ? "#4ade80" : "#f87171" }}>{calcResult.margin.toFixed(1)}%</strong></span>
              </div>
            </div>

            <button
              onClick={() => {
                const params = new URLSearchParams({ inv: String(calcItem.id) });
                const q = parseInt(calcForm.qty); if (q > 0) params.set("qty", String(q));
                const p = parseFloat(calcForm.sell_price); if (p > 0) params.set("pret", String(p));
                if (calcResult && calcResult.extraTotal > 0) params.set("extra", String(calcResult.extraTotal));
                router.push(`/dashboard/sales?${params.toString()}`);
              }}
              style={{
                display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem",
                width: "100%", padding: "0.625rem 1rem", borderRadius: "0.5rem",
                backgroundColor: "#22c55e", color: "var(--text-primary)", fontWeight: 500,
                border: "none", cursor: "pointer",
              }}
            >
              Inregistreaza vanzarea
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
