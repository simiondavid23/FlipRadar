"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { inventoryAPI } from "@/lib/api";
import FeedErrorBanner from "@/components/shared/FeedErrorBanner";
import TopBar from "@/components/shared/TopBar";
import PageHeading, { Hl } from "@/components/shared/PageHeading";
import KpiCard from "@/components/shared/KpiCard";
import { inputStyle, modalOverlayStyle, modalPanelStyle } from "@/lib/uiStyles";
import { Boxes, Plus, Trash2, Pencil, Package, Euro, Calculator, X, TrendingUp, TrendingDown, Upload, FileDown } from "lucide-react";

const labelStyle = {
  display: "block",
  fontFamily: "var(--font-mono)",
  fontSize: "8.5px",
  letterSpacing: ".15em",
  textTransform: "uppercase",
  color: "var(--text-mono)",
  marginBottom: "6px",
};

const gridCols = {
  display: "grid",
  gridTemplateColumns: "2fr 1fr 80px 120px 100px 110px",
  gap: "10px",
  alignItems: "center",
};

const headerColStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: "8px",
  letterSpacing: ".15em",
  color: "var(--text-mono)",
  textTransform: "uppercase",
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
  purchased_at: "",
};

// Data locala YYYY-MM-DD fara conversie UTC (toISOString ar da ziua gresita dupa miezul noptii).
function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function InventoryPage() {
  const router = useRouter();
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");
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
    setForm({ ...emptyForm, purchased_at: todayIso() });
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
      purchased_at: (item.purchased_at || "").slice(0, 10),
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
        category: form.category.trim() || null,
        sku: form.sku.trim() || null,
        source: form.source.trim() || null,
        notes: form.notes.trim() || null,
        purchased_at: form.purchased_at || null,
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

  // GE-6c: filtrare client-side DOAR pe lista afisata (statisticile raman pe items complet).
  const q = search.trim().toLowerCase();
  const visibleItems = q
    ? items.filter((it) =>
        [it.name, it.category, it.sku, it.source].some((v) =>
          (v || "").toLowerCase().includes(q)
        )
      )
    : items;

  return (
    <div>
      <TopBar path={["GESTIUNE", "INVENTAR"]}>
        <button onClick={openCreate} className="btn-cyan">
          <Plus style={{ width: "13px", height: "13px" }} strokeWidth={2.2} /> Adaugă produs
        </button>
      </TopBar>

      <PageHeading
        icon={Boxes}
        title="Inventar"
        subtitle={<>Evidența produselor pe care le ai pe stoc — <Hl>{stats?.total_items ?? 0} articole</Hl>, {stats?.total_units ?? 0} unități.</>}
      >
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <button onClick={handleDownloadTemplate} title="Descarca template Excel pentru import" className="btn-neutral">
            <FileDown style={{ width: "13px", height: "13px" }} strokeWidth={1.8} /> Template Excel
          </button>
          <label
            title="Importa articole dintr-un fisier Excel"
            className="btn-green"
            style={{ cursor: importing ? "wait" : "pointer", opacity: importing ? 0.6 : 1 }}
          >
            <Upload style={{ width: "13px", height: "13px" }} strokeWidth={1.8} /> {importing ? "Se importă…" : "Importă Excel"}
            <input type="file" accept=".xlsx,.xls" onChange={handleImportExcel} disabled={importing} style={{ display: "none" }} />
          </label>
        </div>
      </PageHeading>

      {importMsg && (
        <div style={{
          marginTop: "14px", padding: "11px 14px", borderRadius: "12px", fontSize: "12.5px",
          background: importMsg.kind === "success" ? "rgba(74,222,128,0.09)" : importMsg.kind === "error" ? "rgba(248,113,113,0.09)" : "rgba(251,146,60,0.09)",
          border: `1px solid ${importMsg.kind === "success" ? "rgba(74,222,128,0.3)" : importMsg.kind === "error" ? "rgba(248,113,113,0.3)" : "rgba(251,146,60,0.3)"}`,
          color: importMsg.kind === "success" ? "#4ade80" : importMsg.kind === "error" ? "#f87171" : "#fb923c",
          display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px",
        }}>
          <span>{importMsg.text}</span>
          <button onClick={() => setImportMsg(null)} style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", padding: "4px", display: "flex" }}>
            <X style={{ width: "13px", height: "13px" }} />
          </button>
        </div>
      )}

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(225px,1fr))", gap: "14px", marginTop: "16px" }}>
        <KpiCard
          idx="01"
          icon={Package}
          label="Articole"
          value={stats?.total_items ?? "—"}
          chip={`${stats?.total_units ?? 0} unități`}
          chipTone="cyan"
          note="totale pe stoc"
        />
        <KpiCard
          idx="02"
          icon={Euro}
          label="Valoare totală"
          value={(stats?.total_value_eur ?? 0).toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          unit="EUR"
          note="RON convertit la cursul BNR"
        />
      </div>

      {/* Form modal */}
      {showForm && (
        <div className="glass-panel" style={{ padding: "20px", marginTop: "14px" }}>
          <h2 style={{ color: "var(--text-primary)", fontWeight: 600, fontSize: "15px", marginBottom: "14px" }}>
            {editingId ? "Editeaza articol" : "Adauga articol nou"}
          </h2>
          <form onSubmit={handleSubmit}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <div>
                <label style={labelStyle}>Nume *</label>
                <input required style={inputStyle} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ex: Nurofen 200mg" />
              </div>
              <div>
                <label style={labelStyle}>Categorie</label>
                <input style={inputStyle} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Ex: Medicamente" />
              </div>
              <div>
                <label style={labelStyle}>SKU / Cod produs</label>
                <input style={inputStyle} value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Cantitate *</label>
                <input required type="number" min="1" style={inputStyle} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Pret achizitie *</label>
                <input required type="number" step="0.01" min="0" style={inputStyle} value={form.purchase_price} onChange={(e) => setForm({ ...form, purchase_price: e.target.value })} placeholder="0.00" />
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
                <label style={labelStyle}>Data achizitiei</label>
                <input type="date" max={todayIso()} style={inputStyle} value={form.purchased_at} onChange={(e) => setForm({ ...form, purchased_at: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Sursa / Magazin</label>
                <input style={inputStyle} value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder="Ex: altex.ro" />
              </div>
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label style={labelStyle}>Note</label>
              <textarea style={{ ...inputStyle, minHeight: "72px", resize: "vertical" }} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Detalii optionale" />
            </div>
            {error && <p style={{ color: "#f87171", fontSize: "12.5px", marginBottom: "12px" }}>{error}</p>}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="submit" className="btn-green">
                {editingId ? "Salveaza modificarile" : "Adauga"}
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
        placeholder="Caută după nume, categorie, SKU sau sursă…"
        value={search} onChange={(e) => setSearch(e.target.value)} />

      {/* List */}
      {loading ? (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "14px" }}>
          <div style={{ width: "2.25rem", height: "2.25rem", border: "3px solid rgba(34,211,238,.4)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite", margin: "0 auto" }} />
        </div>
      ) : items.length === 0 ? (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "14px" }}>
          <Boxes style={{ width: "2.5rem", height: "2.5rem", color: "var(--text-mono)", margin: "0 auto 14px", display: "block" }} strokeWidth={1.5} />
          <p style={{ color: "var(--text-primary)", marginBottom: "6px", fontSize: "13px" }}>Inventarul tau este gol</p>
          <p style={{ color: "var(--text-dim)", fontSize: "12.5px" }}>Adauga primele produse pentru a urmari stocul si valoarea.</p>
        </div>
      ) : visibleItems.length === 0 ? (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", marginTop: "14px" }}>
          <Boxes style={{ width: "2.5rem", height: "2.5rem", color: "var(--text-mono)", margin: "0 auto 14px", display: "block" }} strokeWidth={1.5} />
          <p style={{ color: "var(--text-dim)", fontSize: "12.5px" }}>Niciun rezultat pentru cautarea curenta.</p>
        </div>
      ) : (
        <div className="glass-panel" style={{ overflow: "hidden", marginTop: "14px" }}>
          <div style={{ ...gridCols, padding: "10px 16px", borderBottom: "1px solid rgba(94,140,255,.1)", background: "rgba(4,9,18,.5)" }}>
            {["Produs", "Categorie", "Cant.", "Pret unitar", "Valoare", ""].map((h) => (
              <span key={h || "actions"} style={headerColStyle}>{h}</span>
            ))}
          </div>
          {visibleItems.map((item, idx) => (
            <div key={item.id}
              style={{
                ...gridCols,
                padding: "12px 16px",
                borderBottom: idx === visibleItems.length - 1 ? "none" : "1px solid rgba(94,140,255,.07)",
                alignItems: "center",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", flexWrap: "wrap" }}>
                  <span style={{ color: "var(--text-primary)", fontWeight: 600, fontSize: "13px" }}>{item.name}</span>
                  {item.source && (
                    <span style={{ fontFamily: "var(--font-mono)", padding: "2px 7px", borderRadius: "6px", fontSize: "8.5px", letterSpacing: ".08em", textTransform: "uppercase", background: "rgba(236,72,153,0.14)", border: "1px solid rgba(236,72,153,0.4)", color: "#f9a8d4" }}>{item.source}</span>
                  )}
                </div>
                {(item.sku || item.notes) && (
                  <p style={{ fontSize: "10.5px", color: "var(--text-muted)", marginTop: "3px" }}>
                    {item.sku || "—"}{item.notes ? ` · ${item.notes}` : ""}
                  </p>
                )}
              </div>
              <span style={{ fontSize: "11.5px", color: "var(--text-dim)" }}>{item.category || "—"}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: 700, color: "var(--text-primary)" }}>{item.quantity}</span>
              <span style={{ fontSize: "12px", color: "var(--text-dim)" }}>
                {(item.purchase_price?.toFixed?.(2) ?? item.purchase_price)} {item.currency}
              </span>
              <span style={{ fontSize: "12.5px", fontWeight: 700, color: "#4ade80" }}>
                {((item.purchase_price || 0) * (item.quantity || 0)).toFixed(2)} {item.currency}
              </span>
              <div style={{ display: "flex", gap: "0.25rem", justifyContent: "flex-end" }}>
                <button onClick={() => openCalc(item)} title="Calculeaza profit"
                  style={{ padding: "5px", borderRadius: "7px", border: "none", background: "transparent", color: "#7ee7f8", cursor: "pointer", display: "flex", opacity: .85 }}>
                  <Calculator style={{ width: "0.875rem", height: "0.875rem" }} />
                </button>
                <button onClick={() => openEdit(item)} title="Editeaza"
                  style={{ padding: "5px", borderRadius: "7px", border: "none", background: "transparent", color: "var(--text-dim)", cursor: "pointer", display: "flex", opacity: .85 }}>
                  <Pencil style={{ width: "0.875rem", height: "0.875rem" }} />
                </button>
                <button onClick={() => handleDelete(item.id)} title="Sterge"
                  style={{ padding: "5px", borderRadius: "7px", border: "none", background: "transparent", color: "#f87171", cursor: "pointer", display: "flex", opacity: .85 }}>
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
          style={modalOverlayStyle}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{ ...modalPanelStyle, maxWidth: "560px", padding: "22px" }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Calculator style={{ width: "17px", height: "17px", color: "#22d3ee" }} strokeWidth={1.8} />
                <h2 style={{ color: "var(--text-primary)", fontWeight: 600, fontSize: "16px", margin: 0 }}>
                  Calculator profit
                </h2>
              </div>
              <button onClick={closeCalc} className="btn-icon" aria-label="Închide">
                <X style={{ width: "15px", height: "15px" }} strokeWidth={1.8} />
              </button>
            </div>

            <div className="glass-chip" style={{ marginBottom: "14px", padding: "12px", borderRadius: "12px" }}>
              <p style={{ fontSize: "13px", color: "var(--text-primary)", fontWeight: 600, marginBottom: "4px" }}>{calcItem.name}</p>
              <p style={{ fontSize: "11.5px", color: "var(--text-dim)" }}>
                Pret achizitie: <span style={{ color: "var(--text-primary)" }}>{Number(calcItem.purchase_price).toFixed(2)} {calcItem.currency}</span>
                {" · "}
                Stoc: <span style={{ color: "var(--text-primary)" }}>{calcItem.quantity}</span>
              </p>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <div>
                <label style={labelStyle}>Pret vanzare ({calcItem.currency}) *</label>
                <input type="number" step="0.01" min="0"
                  value={calcForm.sell_price}
                  onChange={(e) => setCalcForm({ ...calcForm, sell_price: e.target.value })}
                  placeholder="0.00"
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Cantitate *</label>
                <input type="number" min="1" max={calcItem.quantity}
                  value={calcForm.qty}
                  onChange={(e) => setCalcForm({ ...calcForm, qty: e.target.value })}
                  style={inputStyle}
                />
              </div>
            </div>

            <div style={{ marginBottom: "0.75rem" }}>
              <p style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", color: "var(--text-mono)", textTransform: "uppercase", letterSpacing: ".15em", marginBottom: "8px" }}>
                Costuri suplimentare (optional)
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.5rem" }}>
                <div>
                  <label style={labelStyle}>Transport</label>
                  <input type="number" step="0.01" min="0"
                    value={calcForm.transport}
                    onChange={(e) => setCalcForm({ ...calcForm, transport: e.target.value })}
                    placeholder="0.00"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Taxe</label>
                  <input type="number" step="0.01" min="0"
                    value={calcForm.taxe}
                    onChange={(e) => setCalcForm({ ...calcForm, taxe: e.target.value })}
                    placeholder="0.00"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Comision platforma</label>
                  <input type="number" step="0.01" min="0"
                    value={calcForm.comision}
                    onChange={(e) => setCalcForm({ ...calcForm, comision: e.target.value })}
                    placeholder="0.00"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Alte cheltuieli</label>
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
              <div style={{ padding: "12px", borderRadius: "12px", background: "rgba(4,9,18,.45)", border: "1px solid rgba(94,140,255,.13)" }}>
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", color: "var(--text-mono)", textTransform: "uppercase", letterSpacing: ".15em", marginBottom: "4px" }}>Venit total</p>
                <p style={{ fontSize: "15px", fontWeight: 600, color: "var(--text-primary)" }}>
                  {calcResult.totalRevenue.toFixed(2)} {calcItem.currency}
                </p>
              </div>
              <div style={{ padding: "12px", borderRadius: "12px", background: "rgba(4,9,18,.45)", border: "1px solid rgba(94,140,255,.13)" }}>
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", color: "var(--text-mono)", textTransform: "uppercase", letterSpacing: ".15em", marginBottom: "4px" }}>Cost total</p>
                <p style={{ fontSize: "15px", fontWeight: 600, color: "var(--text-primary)" }}>
                  {calcResult.totalCost.toFixed(2)} {calcItem.currency}
                </p>
              </div>
            </div>

            <div style={{
              padding: "14px", borderRadius: "12px",
              background: calcResult.profit >= 0 ? "rgba(74,222,128,0.09)" : "rgba(248,113,113,0.09)",
              border: `1px solid ${calcResult.profit >= 0 ? "rgba(74,222,128,0.3)" : "rgba(248,113,113,0.3)"}`,
              marginBottom: "1rem",
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                  {calcResult.profit >= 0
                    ? <TrendingUp style={{ width: "1rem", height: "1rem", color: "#4ade80" }} />
                    : <TrendingDown style={{ width: "1rem", height: "1rem", color: "#f87171" }} />}
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", color: calcResult.profit >= 0 ? "#4ade80" : "#f87171", textTransform: "uppercase", letterSpacing: ".15em" }}>
                    Profit estimat
                  </p>
                </div>
                <p style={{ fontSize: "22px", fontWeight: 700, letterSpacing: "-.5px", color: calcResult.profit >= 0 ? "#4ade80" : "#f87171" }}>
                  {calcResult.profit >= 0 ? "+" : ""}{calcResult.profit.toFixed(2)} {calcItem.currency}
                </p>
              </div>
              <div style={{ display: "flex", gap: "16px", fontSize: "11.5px", color: "var(--text-dim)" }}>
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
              className="btn-green"
              style={{ width: "100%", justifyContent: "center" }}
            >
              Inregistreaza vanzarea
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
