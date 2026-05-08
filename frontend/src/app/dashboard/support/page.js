"use client";
import { useState, useEffect, useRef } from "react";
import { aiAPI, ticketsAPI } from "@/lib/api";
import { MessageCircle, Send, Trash2, Headphones, Bot, User, Plus, Ticket, Clock, CheckCircle2, AlertCircle } from "lucide-react";

export default function SupportPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showStaffForm, setShowStaffForm] = useState(false);
  const [showTicketForm, setShowTicketForm] = useState(false);
  const [ticketForm, setTicketForm] = useState({ subject: "", message: "", priority: "normal" });
  const [ticketMsg, setTicketMsg] = useState("");
  const [tickets, setTickets] = useState([]);
  const [activeTicket, setActiveTicket] = useState(null);
  const [replyContent, setReplyContent] = useState("");
  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadHistory();
    loadTickets();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadHistory = async () => {
    try {
      const res = await aiAPI.getChatHistory();
      setMessages(res.data);
    } catch {
      console.log("No history");
    }
  };

  const loadTickets = async () => {
    try {
      const res = await ticketsAPI.getMyTickets();
      setTickets(res.data);
    } catch (e) {
      console.error(e);
    }
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    const currentInput = input;
    setInput("");
    setLoading(true);

    try {
      const history = messages.slice(-10).map((m) => ({ role: m.role, content: m.content }));
      const res = await aiAPI.chat({ message: currentInput, history });
      const assistantMsg = {
        role: "assistant",
        content: res.data.response,
        needs_staff: res.data.needs_staff,
      };
      setMessages((prev) => [...prev, assistantMsg]);
      if (res.data.needs_staff) setShowStaffForm(true);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Eroare la comunicarea cu serverul. Incearca din nou." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = async () => {
    try {
      await aiAPI.clearChatHistory();
      setMessages([]);
    } catch (e) {
      console.error(e);
    }
  };

  const openTicketForm = (prefillFromChat = false) => {
    if (prefillFromChat && messages.length > 0) {
      const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
      if (lastUserMsg) {
        setTicketForm({
          subject: lastUserMsg.content.slice(0, 80),
          message: lastUserMsg.content,
          priority: "normal",
        });
      }
    } else {
      setTicketForm({ subject: "", message: "", priority: "normal" });
    }
    setTicketMsg("");
    setShowTicketForm(true);
    setShowStaffForm(false);
  };

  const submitTicket = async (e) => {
    e.preventDefault();
    setTicketMsg("");
    try {
      await ticketsAPI.createTicket(ticketForm);
      setTicketMsg("Ticket creat cu succes! Echipa de suport va reveni catre tine.");
      setTicketForm({ subject: "", message: "", priority: "normal" });
      await loadTickets();
      setTimeout(() => { setShowTicketForm(false); setTicketMsg(""); }, 2000);
    } catch (error) {
      setTicketMsg(error.response?.data?.detail || "Eroare la crearea ticketului");
    }
  };

  const openTicket = async (id) => {
    try {
      const res = await ticketsAPI.getTicket(id);
      setActiveTicket(res.data);
      setReplyContent("");
    } catch {
      alert("Nu s-a putut incarca ticketul");
    }
  };

  const submitReply = async (e) => {
    e.preventDefault();
    if (!replyContent.trim() || !activeTicket) return;
    try {
      await ticketsAPI.replyTicket(activeTicket.id, { content: replyContent });
      setReplyContent("");
      const res = await ticketsAPI.getTicket(activeTicket.id);
      setActiveTicket(res.data);
      await loadTickets();
    } catch (error) {
      alert(error.response?.data?.detail || "Eroare la trimitere");
    }
  };

  const suggestedQuestions = [
    "Cum adaug un produs la favorite sau blacklist?",
    "Cum setez o alerta de pret?",
    "Cum import produse in inventar dintr-un Excel?",
    "Cum inregistrez o vanzare dintr-un produs din inventar?",
  ];

  const statusConfig = {
    open: { label: "Deschis", color: "#60a5fa", bg: "rgba(59,130,246,0.15)", icon: AlertCircle },
    in_progress: { label: "In curs", color: "#facc15", bg: "rgba(234,179,8,0.15)", icon: Clock },
    closed: { label: "Inchis", color: "#94a3b8", bg: "rgba(148,163,184,0.15)", icon: CheckCircle2 },
  };

  const priorityConfig = {
    low: { label: "Scazuta", color: "#94a3b8" },
    normal: { label: "Normala", color: "#60a5fa" },
    high: { label: "Ridicata", color: "#f87171" },
  };

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
            <div style={{ padding: "0.5rem", borderRadius: "0.625rem", backgroundColor: "#2563eb", display: "flex" }}>
              <MessageCircle style={{ width: "20px", height: "20px", color: "white" }} />
            </div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "white", margin: 0 }}>Support</h1>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", marginLeft: "3rem" }}>
            Intreaba AI-ul sau deschide un ticket catre echipa de suport
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button onClick={() => openTicketForm(false)}
            style={{
              display: "flex", alignItems: "center", gap: "0.375rem",
              padding: "0.5rem 0.875rem", borderRadius: "0.5rem",
              backgroundColor: "#ca8a04", border: "none",
              color: "black", fontWeight: 600, cursor: "pointer", fontSize: "0.8125rem",
            }}
          >
            <Plus style={{ width: "14px", height: "14px" }} /> Ticket nou
          </button>
          {messages.length > 0 && (
            <button onClick={clearHistory}
              style={{
                display: "flex", alignItems: "center", gap: "0.375rem",
                padding: "0.5rem 0.75rem", borderRadius: "0.5rem",
                backgroundColor: "transparent", border: "1px solid var(--border-color)",
                color: "#94a3b8", cursor: "pointer", fontSize: "0.8125rem",
              }}
            >
              <Trash2 style={{ width: "14px", height: "14px" }} /> Sterge istoric
            </button>
          )}
        </div>
      </div>

      {/* Ticket form modal */}
      {showTicketForm && (
        <div style={{
          backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderRadius: "0.75rem", padding: "1.5rem", marginBottom: "1.5rem",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
            <h2 style={{ color: "white", fontWeight: 600, margin: 0, fontSize: "1rem" }}>
              <Ticket style={{ width: "16px", height: "16px", display: "inline", marginRight: "0.375rem", color: "#facc15" }} />
              Creeaza ticket nou
            </h2>
            <button onClick={() => setShowTicketForm(false)}
              style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "1.25rem" }}>
              ×
            </button>
          </div>
          <form onSubmit={submitTicket}>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Subiect *</label>
              <input required value={ticketForm.subject}
                onChange={(e) => setTicketForm({ ...ticketForm, subject: e.target.value })}
                placeholder="Ex: Problema la creare alerta"
                style={{
                  backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                  borderRadius: "0.5rem", color: "white", padding: "0.625rem 0.875rem",
                  fontSize: "0.875rem", width: "100%", outline: "none",
                }}
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem", display: "block", marginBottom: "0.25rem" }}>Descriere *</label>
              <textarea required value={ticketForm.message}
                onChange={(e) => setTicketForm({ ...ticketForm, message: e.target.value })}
                placeholder="Descrie problema cu cat mai multe detalii..."
                style={{
                  backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                  borderRadius: "0.5rem", color: "white", padding: "0.625rem 0.875rem",
                  fontSize: "0.875rem", width: "100%", outline: "none", minHeight: "100px",
                  resize: "vertical", fontFamily: "inherit",
                }}
              />
            </div>
            {ticketMsg && (
              <p style={{ fontSize: "0.8125rem", marginBottom: "0.75rem",
                color: ticketMsg.includes("succes") ? "#4ade80" : "#f87171" }}>
                {ticketMsg}
              </p>
            )}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="submit"
                style={{
                  padding: "0.625rem 1rem", borderRadius: "0.5rem",
                  backgroundColor: "#ca8a04", border: "none", color: "black",
                  fontWeight: 600, cursor: "pointer", fontSize: "0.875rem",
                }}
              >
                Trimite ticket
              </button>
              <button type="button" onClick={() => setShowTicketForm(false)}
                style={{
                  padding: "0.625rem 1rem", borderRadius: "0.5rem",
                  backgroundColor: "transparent", color: "#94a3b8",
                  border: "1px solid var(--border-color)", cursor: "pointer", fontSize: "0.875rem",
                }}
              >
                Anuleaza
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Active ticket detail view */}
      {activeTicket && (
        <div style={{
          backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderRadius: "0.75rem", padding: "1.5rem", marginBottom: "1.5rem",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
            <div>
              <h2 style={{ color: "white", fontWeight: 600, margin: 0, fontSize: "1rem" }}>
                #{activeTicket.id} — {activeTicket.subject}
              </h2>
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.375rem", alignItems: "center" }}>
                {(() => {
                  const sc = statusConfig[activeTicket.status] || statusConfig.open;
                  const SIcon = sc.icon;
                  return (
                    <span style={{
                      display: "inline-flex", alignItems: "center", gap: "0.25rem",
                      padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem",
                      backgroundColor: sc.bg, color: sc.color,
                    }}>
                      <SIcon style={{ width: "10px", height: "10px" }} /> {sc.label}
                    </span>
                  );
                })()}
              </div>
            </div>
            <button onClick={() => setActiveTicket(null)}
              style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "1.25rem" }}>
              ×
            </button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginBottom: "1rem", maxHeight: "400px", overflowY: "auto" }}>
            {activeTicket.messages?.map((m) => (
              <div key={m.id} style={{
                padding: "0.75rem 1rem", borderRadius: "0.625rem",
                backgroundColor: m.is_admin ? "rgba(147,51,234,0.1)" : "rgba(59,130,246,0.1)",
                border: m.is_admin ? "1px solid rgba(147,51,234,0.2)" : "1px solid rgba(59,130,246,0.2)",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.375rem" }}>
                  <span style={{ fontSize: "0.75rem", fontWeight: 600, color: m.is_admin ? "#c4b5fd" : "#93c5fd" }}>
                    {m.is_admin ? "Suport" : m.sender_name}
                  </span>
                  <span style={{ fontSize: "0.6875rem", color: "#94a3b8" }}>
                    {new Date(m.created_at).toLocaleString("ro-RO")}
                  </span>
                </div>
                <p style={{ color: "#e2e8f0", fontSize: "0.8125rem", margin: 0, whiteSpace: "pre-wrap" }}>{m.content}</p>
              </div>
            ))}
          </div>
          {activeTicket.status !== "closed" && (
            <form onSubmit={submitReply} style={{ display: "flex", gap: "0.5rem" }}>
              <input value={replyContent} onChange={(e) => setReplyContent(e.target.value)}
                placeholder="Scrie un raspuns..."
                style={{
                  flex: 1, padding: "0.625rem 0.875rem", borderRadius: "0.5rem",
                  backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                  color: "white", fontSize: "0.875rem", outline: "none",
                }}
              />
              <button type="submit"
                style={{ padding: "0.625rem 1rem", borderRadius: "0.5rem", backgroundColor: "#2563eb",
                  border: "none", color: "white", cursor: "pointer", fontSize: "0.875rem" }}>
                Trimite
              </button>
            </form>
          )}
        </div>
      )}

      {/* Existing tickets list */}
      {tickets.length > 0 && !activeTicket && (
        <div style={{
          backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderRadius: "0.75rem", padding: "1rem 1.25rem", marginBottom: "1.5rem",
        }}>
          <h3 style={{ color: "white", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Ticket style={{ width: "14px", height: "14px", display: "inline", marginRight: "0.375rem", color: "#facc15" }} />
            Ticketele mele ({tickets.length})
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {tickets.map((t) => {
              const sc = statusConfig[t.status] || statusConfig.open;
              const pc = priorityConfig[t.priority] || priorityConfig.normal;
              return (
                <div key={t.id} onClick={() => openTicket(t.id)}
                  style={{
                    padding: "0.625rem 0.875rem", borderRadius: "0.5rem",
                    border: "1px solid var(--border-color)", cursor: "pointer",
                    transition: "all 0.15s ease",
                    display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem", flexWrap: "wrap",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)"; e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.02)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border-color)"; e.currentTarget.style.backgroundColor = "transparent"; }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                      <span style={{ color: "white", fontWeight: 500, fontSize: "0.875rem" }}>
                        #{t.id} · {t.subject}
                      </span>
                      <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: sc.bg, color: sc.color }}>
                        {sc.label}
                      </span>
                      <span style={{ fontSize: "0.6875rem", color: pc.color }}>
                        · {pc.label}
                      </span>
                      {t.has_admin_reply && (
                        <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: "rgba(34,197,94,0.15)", color: "#4ade80" }}>
                          Raspuns primit
                        </span>
                      )}
                    </div>
                    <p style={{ fontSize: "0.75rem", color: "#94a3b8", margin: "0.25rem 0 0" }}>
                      {t.message_count} mesaje · {new Date(t.updated_at).toLocaleDateString("ro-RO")}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Chat area */}
      {!activeTicket && (
        <div style={{
          backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderRadius: "1rem", display: "flex", flexDirection: "column", height: "60vh",
        }}>
          {/* Messages */}
          <div style={{ flex: 1, overflowY: "auto", padding: "1.5rem" }}>
            {messages.length === 0 && (
              <div style={{ textAlign: "center", padding: "3rem 0" }}>
                <Bot style={{ width: "3rem", height: "3rem", margin: "0 auto 1rem", color: "#60a5fa", opacity: 0.5 }} />
                <p style={{ fontSize: "1rem", color: "white", marginBottom: "0.375rem" }}>Bine ai venit la FlipRadar AI Support!</p>
                <p style={{ fontSize: "0.8125rem", color: "#94a3b8", marginBottom: "1.5rem" }}>Pot sa te ajut cu intrebari despre:</p>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.625rem", maxWidth: "400px", margin: "0 auto" }}>
                  {suggestedQuestions.map((q) => (
                    <button key={q} onClick={() => setInput(q)}
                      style={{
                        textAlign: "left", fontSize: "0.8125rem", padding: "0.75rem",
                        borderRadius: "0.625rem", color: "#cbd5e1",
                        backgroundColor: "transparent", border: "1px solid var(--border-color)",
                        cursor: "pointer", transition: "all 0.15s ease",
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {messages.map((msg, i) => (
                <div key={i} style={{ display: "flex", gap: "0.75rem", justifyContent: msg.role === "user" ? "flex-end" : "flex-start" }}>
                  {msg.role === "assistant" && (
                    <div style={{ width: "32px", height: "32px", borderRadius: "50%", backgroundColor: "#2563eb", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <Bot style={{ width: "16px", height: "16px", color: "white" }} />
                    </div>
                  )}
                  <div style={{
                    maxWidth: "70%", padding: "0.75rem 1rem", borderRadius: "1rem",
                    ...(msg.role === "user"
                      ? { backgroundColor: "#2563eb", color: "white", borderBottomRightRadius: "0.25rem" }
                      : { backgroundColor: "#334155", color: "#e2e8f0", borderBottomLeftRadius: "0.25rem" }),
                  }}>
                    <p style={{ fontSize: "0.8125rem", whiteSpace: "pre-wrap", margin: 0, lineHeight: 1.6 }}>{msg.content}</p>
                  </div>
                  {msg.role === "user" && (
                    <div style={{ width: "32px", height: "32px", borderRadius: "50%", backgroundColor: "#7c3aed", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <User style={{ width: "16px", height: "16px", color: "white" }} />
                    </div>
                  )}
                </div>
              ))}

              {loading && (
                <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-start" }}>
                  <div style={{ width: "32px", height: "32px", borderRadius: "50%", backgroundColor: "#2563eb", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Bot style={{ width: "16px", height: "16px", color: "white" }} />
                  </div>
                  <div style={{ padding: "0.75rem 1rem", borderRadius: "1rem", backgroundColor: "#334155", borderBottomLeftRadius: "0.25rem" }}>
                    <div style={{ display: "flex", gap: "4px" }}>
                      <div style={{ width: "8px", height: "8px", backgroundColor: "#60a5fa", borderRadius: "50%", animation: "bounce 1s infinite" }} />
                      <div style={{ width: "8px", height: "8px", backgroundColor: "#60a5fa", borderRadius: "50%", animation: "bounce 1s infinite 0.15s" }} />
                      <div style={{ width: "8px", height: "8px", backgroundColor: "#60a5fa", borderRadius: "50%", animation: "bounce 1s infinite 0.3s" }} />
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div ref={messagesEndRef} />
          </div>

          {/* Staff redirect banner */}
          {showStaffForm && (
            <div style={{
              margin: "0 1.5rem 0.75rem", padding: "1rem", borderRadius: "0.75rem",
              backgroundColor: "rgba(250,204,21,0.08)", border: "1px solid rgba(250,204,21,0.25)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <Headphones style={{ width: "18px", height: "18px", color: "#facc15", flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: "200px" }}>
                  <p style={{ fontSize: "0.8125rem", fontWeight: 600, color: "#facc15", margin: 0 }}>Doresti sa contactezi echipa de suport?</p>
                  <p style={{ fontSize: "0.75rem", color: "#94a3b8", margin: "0.25rem 0 0" }}>Deschide un ticket si vom reveni catre tine.</p>
                </div>
                <button onClick={() => openTicketForm(true)}
                  style={{
                    padding: "0.5rem 1rem", borderRadius: "0.5rem",
                    backgroundColor: "#ca8a04", border: "none", color: "black",
                    fontWeight: 600, fontSize: "0.8125rem", cursor: "pointer",
                  }}>
                  Creeaza ticket
                </button>
                <button onClick={() => setShowStaffForm(false)}
                  style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "0.8125rem" }}>
                  Inchide
                </button>
              </div>
            </div>
          )}

          {/* Input */}
          <div style={{ padding: "1rem 1.5rem", borderTop: "1px solid var(--border-color)" }}>
            <form onSubmit={sendMessage} style={{ display: "flex", gap: "0.75rem" }}>
              <input type="text" value={input} onChange={(e) => setInput(e.target.value)}
                placeholder="Scrie un mesaj..." disabled={loading}
                style={{
                  flex: 1, padding: "0.75rem 1rem", borderRadius: "0.625rem",
                  backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                  color: "white", fontSize: "0.875rem", outline: "none",
                }} />
              <button type="submit" disabled={loading || !input.trim()}
                style={{
                  padding: "0.75rem 1rem", borderRadius: "0.625rem",
                  backgroundColor: "#2563eb", border: "none", color: "white",
                  cursor: loading || !input.trim() ? "not-allowed" : "pointer",
                  opacity: loading || !input.trim() ? 0.5 : 1,
                }}>
                <Send style={{ width: "18px", height: "18px" }} />
              </button>
            </form>
          </div>
        </div>
      )}

      <style>{`
        @keyframes bounce {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
        }
      `}</style>
    </div>
  );
}
