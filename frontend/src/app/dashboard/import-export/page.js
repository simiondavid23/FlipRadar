"use client";
import { useState, useRef } from "react";
import { importExportAPI } from "@/lib/api";
import { Upload, Download, FileSpreadsheet, FileText, CheckCircle, AlertCircle, File } from "lucide-react";

export default function ImportExportPage() {
  const [importResult, setImportResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState("");
  const fileRef = useRef(null);

  const handleImport = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setLoading(true);
    setImportResult(null);
    try {
      let res;
      if (file.name.endsWith(".csv") || file.name.endsWith(".txt")) {
        res = await importExportAPI.importCSV(file);
      } else if (file.name.endsWith(".xlsx") || file.name.endsWith(".xls")) {
        res = await importExportAPI.importExcel(file);
      } else {
        setImportResult({ error: "Format nesupportat. Foloseste CSV sau Excel (.xlsx)." });
        setLoading(false);
        return;
      }
      setImportResult(res.data);
    } catch (e) {
      setImportResult({ error: e.response?.data?.detail || "Eroare la import" });
    } finally {
      setLoading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleExport = async (type) => {
    setExportLoading(type);
    try {
      let res;
      if (type === "products") res = await importExportAPI.exportProducts();
      else if (type === "watchlist") res = await importExportAPI.exportWatchlist();
      else res = await importExportAPI.downloadTemplate();

      const blob = new Blob([res.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = type === "products" ? "flipradar_products.xlsx" : type === "watchlist" ? "flipradar_watchlist.xlsx" : "flipradar_template.xlsx";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch { alert("Eroare la export"); }
    finally { setExportLoading(""); }
  };

  const cardStyle = { backgroundColor: "#1e293b", border: "1px solid #334155" };

  return (
    <div>
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.875rem", fontWeight: 700, color: "white", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <FileSpreadsheet style={{ width: "2rem", height: "2rem", color: "#22c55e" }} />
          Import / Export
        </h1>
        <p style={{ color: "#94a3b8", marginTop: "0.5rem" }}>Importa produse din Excel/CSV sau exporta datele tale</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem" }}>
        {/* Import Section */}
        <div style={{ ...cardStyle, borderRadius: "1rem", padding: "1.5rem" }}>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 600, color: "white", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Upload style={{ width: "1.25rem", height: "1.25rem", color: "#3b82f6" }} /> Import Produse
          </h2>
          <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: "1rem" }}>
            Incarca un fisier CSV sau Excel cu produse. Coloanele acceptate: name, asin, ean, category, price, currency, source, source_url
          </p>

          <div style={{ border: "2px dashed #334155", borderRadius: "0.75rem", padding: "2rem", textAlign: "center", marginBottom: "1rem" }}>
            <File style={{ width: "2.5rem", height: "2.5rem", margin: "0 auto 0.75rem", color: "#475569" }} />
            <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: "0.75rem" }}>Trage un fisier aici sau click pentru a selecta</p>
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.txt" onChange={handleImport}
              style={{ display: "block", margin: "0 auto", fontSize: "0.875rem", color: "#94a3b8" }} />
          </div>

          {loading && <p style={{ color: "#3b82f6", fontSize: "0.875rem" }}>Se importa...</p>}

          {importResult && !importResult.error && (
            <div style={{ padding: "1rem", borderRadius: "0.5rem", backgroundColor: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                <CheckCircle style={{ width: "1.25rem", height: "1.25rem", color: "#22c55e" }} />
                <span style={{ color: "#22c55e", fontWeight: 600 }}>Import finalizat!</span>
              </div>
              <p style={{ color: "#94a3b8", fontSize: "0.875rem" }}>
                {importResult.imported} produse importate, {importResult.skipped} omise (duplicate)
              </p>
            </div>
          )}

          {importResult?.error && (
            <div style={{ padding: "1rem", borderRadius: "0.5rem", backgroundColor: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <AlertCircle style={{ width: "1.25rem", height: "1.25rem", color: "#ef4444" }} />
                <span style={{ color: "#ef4444", fontSize: "0.875rem" }}>{importResult.error}</span>
              </div>
            </div>
          )}

          <button onClick={() => handleExport("template")} disabled={exportLoading === "template"}
            style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 1rem",
              borderRadius: "0.5rem", border: "1px solid #334155", backgroundColor: "transparent", color: "#94a3b8",
              cursor: "pointer", fontSize: "0.8125rem" }}>
            <Download style={{ width: "0.875rem", height: "0.875rem" }} />
            Descarca template Excel
          </button>
        </div>

        {/* Export Section */}
        <div style={{ ...cardStyle, borderRadius: "1rem", padding: "1.5rem" }}>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 600, color: "white", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Download style={{ width: "1.25rem", height: "1.25rem", color: "#22c55e" }} /> Export Date
          </h2>
          <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
            Exporta produsele sau watchlist-ul tau in format Excel.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <button onClick={() => handleExport("products")} disabled={!!exportLoading}
              style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "1rem", borderRadius: "0.75rem",
                border: "1px solid #334155", backgroundColor: "transparent", color: "white", cursor: "pointer", textAlign: "left" }}>
              <FileSpreadsheet style={{ width: "2rem", height: "2rem", color: "#22c55e" }} />
              <div>
                <p style={{ fontWeight: 600 }}>Export Produse</p>
                <p style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: "0.125rem" }}>Toate produsele din baza de date</p>
              </div>
            </button>

            <button onClick={() => handleExport("watchlist")} disabled={!!exportLoading}
              style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "1rem", borderRadius: "0.75rem",
                border: "1px solid #334155", backgroundColor: "transparent", color: "white", cursor: "pointer", textAlign: "left" }}>
              <FileText style={{ width: "2rem", height: "2rem", color: "#a78bfa" }} />
              <div>
                <p style={{ fontWeight: 600 }}>Export Watchlist</p>
                <p style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: "0.125rem" }}>Produsele din watchlist-ul tau</p>
              </div>
            </button>
          </div>

          {exportLoading && <p style={{ color: "#22c55e", fontSize: "0.875rem", marginTop: "1rem" }}>Se genereaza fisierul...</p>}
        </div>
      </div>
    </div>
  );
}
