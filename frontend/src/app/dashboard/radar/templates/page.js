"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { radarAPI } from "@/lib/api";
import { MessageSquare, Plus, Pencil, Trash2, X, Save } from "lucide-react";

const PLATFORM_OPTIONS = [
  { value: "all", label: "Toate platformele" },
  { value: "olx", label: "OLX" },
  { value: "vinted", label: "Vinted" },
  { value: "okazii", label: "Okazii" },
  { value: "facebook", label: "Facebook" },
];

const PLACEHOLDERS = ["{titlu}", "{pret_cerut}", "{pret_oferit}", "{platforma}"];

const EMPTY_FORM = { name: "", platform: "all", template_text: "", is_default: false };

export default function TemplatesPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const textareaRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await radarAPI.getTemplates();
      setItems(r.data || []);
    } catch (e) {
      console.error("[Templates]", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  };

  const openEdit = (t) => {
    setEditingId(t.id);
    setForm({
      name: t.name,
      platform: t.platform,
      template_text: t.template_text,
      is_default: t.is_default,
    });
    setShowForm(true);
  };

  const submit = async (e) => {
    e?.preventDefault();
    if (!form.name.trim() || !form.template_text.trim()) {
      alert("Numele și textul sunt obligatorii.");
      return;
    }
    try {
      if (editingId) {
        await radarAPI.updateTemplate(editingId, form);
      } else {
        await radarAPI.createTemplate(form);
      }
      setShowForm(false);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la salvare.");
    }
  };

  const remove = async (id) => {
    if (!confirm("Ștergi acest șablon?")) return;
    try {
      await radarAPI.deleteTemplate(id);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Eroare la ștergere.");
    }
  };

  const insertPlaceholder = (ph) => {
    const ta = textareaRef.current;
    if (!ta) {
      setForm({ ...form, template_text: form.template_text + ph });
      return;
    }
    const start = ta.selectionStart || 0;
    const end = ta.selectionEnd || 0;
    const before = form.template_text.slice(0, start);
    const after = form.template_text.slice(end);
    const newText = before + ph + after;
    setForm({ ...form, template_text: newText });
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + ph.length;
      ta.setSelectionRange(pos, pos);
    });
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "3px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  const inputStyle = {
    width: "100%", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
    borderRadius: "0.5rem", padding: "0.5rem 0.75rem", color: "var(--text-primary)",
    fontSize: "0.875rem", outline: "none",
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <MessageSquare style={{ width: "22px", height: "22px", color: "#2563eb" }} />
            Șabloane Mesaje
          </h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            Mesaje pre-formulate pe care le poți copia rapid când contactezi vânzătorul ({items.length} șabloane)
          </p>
        </div>
        <button
          onClick={openCreate}
          style={{
            display: "inline-flex", alignItems: "center", gap: "0.5rem",
            padding: "0.5rem 0.875rem", backgroundColor: "var(--blue-primary)",
            color: "white", border: "none", borderRadius: "0.5rem",
            fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer",
          }}
        >
          <Plus style={{ width: "16px", height: "16px" }} />
          Șablon nou
        </button>
      </div>

      {items.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "2.5rem",
          backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderRadius: "0.75rem", color: "var(--text-secondary)",
        }}>
          Nu ai niciun șablon. Creează unul cu butonul de mai sus.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "0.875rem" }}>
          {items.map((t) => (
            <div key={t.id} style={{
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "0.75rem", padding: "1rem",
              display: "flex", flexDirection: "column", gap: "0.5rem",
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
                <h3 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>{t.name}</h3>
                <span style={{
                  padding: "0.125rem 0.5rem",
                  backgroundColor: "rgba(37,99,235,0.15)",
                  color: "#60a5fa", border: "1px solid rgba(37,99,235,0.3)",
                  borderRadius: "0.375rem", fontSize: "0.7rem", fontWeight: 600,
                  textTransform: "uppercase",
                }}>{t.platform}</span>
              </div>
              <p style={{
                margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)",
                lineHeight: 1.5, whiteSpace: "pre-wrap",
                display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden",
              }}>
                {t.template_text}
              </p>
              <div style={{ display: "flex", gap: "0.375rem", marginTop: "auto" }}>
                <button onClick={() => openEdit(t)} style={smallBtn("#60a5fa")}>
                  <Pencil style={{ width: "12px", height: "12px", marginRight: "0.25rem", display: "inline" }} />
                  Editează
                </button>
                <button onClick={() => remove(t.id)} style={smallBtn("#f87171")}>
                  <Trash2 style={{ width: "12px", height: "12px", marginRight: "0.25rem", display: "inline" }} />
                  Șterge
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Form modal */}
      {showForm && (
        <div
          onClick={() => setShowForm(false)}
          style={{
            position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 100, padding: "1.5rem",
          }}
        >
          <form
            onClick={(e) => e.stopPropagation()}
            onSubmit={submit}
            style={{
              backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
              borderRadius: "0.875rem", maxWidth: "560px", width: "100%",
              maxHeight: "90vh", overflowY: "auto", padding: "1.25rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
              <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>
                {editingId ? "Editează șablon" : "Șablon nou"}
              </h2>
              <button type="button" onClick={() => setShowForm(false)} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}>
                <X style={{ width: "20px", height: "20px" }} />
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <label>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>Nume</div>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  style={inputStyle}
                  placeholder="ex: Interes general OLX"
                  required
                />
              </label>
              <label>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>Platformă</div>
                <select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })} style={inputStyle}>
                  {PLATFORM_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </label>
              <label>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem", fontWeight: 500 }}>Text șablon</div>
                <textarea
                  ref={textareaRef}
                  value={form.template_text}
                  onChange={(e) => setForm({ ...form, template_text: e.target.value })}
                  rows={6}
                  style={{ ...inputStyle, resize: "vertical", fontFamily: "inherit" }}
                  placeholder="Bună ziua, sunt interesat de {titlu}..."
                  required
                />
              </label>
              <div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: "0.375rem" }}>
                  Click pe un placeholder pentru a-l insera la poziția cursorului:
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                  {PLACEHOLDERS.map((ph) => (
                    <button
                      key={ph}
                      type="button"
                      onClick={() => insertPlaceholder(ph)}
                      style={{
                        padding: "0.25rem 0.5rem",
                        backgroundColor: "var(--bg-dark)",
                        border: "1px solid var(--border-color)",
                        borderRadius: "0.375rem",
                        color: "var(--blue-light)",
                        fontFamily: "monospace",
                        fontSize: "0.75rem",
                        cursor: "pointer",
                      }}
                    >
                      {ph}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button type="button" onClick={() => setShowForm(false)} style={{ padding: "0.5rem 0.875rem", backgroundColor: "var(--bg-dark)", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", fontSize: "0.8125rem", cursor: "pointer" }}>
                Anulează
              </button>
              <button type="submit" style={{ padding: "0.5rem 0.875rem", backgroundColor: "var(--blue-primary)", color: "white", border: "none", borderRadius: "0.5rem", fontSize: "0.8125rem", fontWeight: 600, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                <Save style={{ width: "14px", height: "14px" }} />
                Salvează
              </button>
            </div>
          </form>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
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
    display: "inline-flex",
    alignItems: "center",
  };
}
