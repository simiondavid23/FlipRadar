"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { adminAPI } from "@/lib/api";
import Link from "next/link";
import { ArrowLeft, Send, XCircle, User, Shield } from "lucide-react";

export default function AdminTicketDetail() {
  const { id } = useParams();
  const [ticket, setTicket] = useState(null);
  const [reply, setReply] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef(null);

  const loadTicket = useCallback(async () => {
    try {
      const res = await adminAPI.getTicket(id);
      setTicket(res.data);
    } catch (error) {
      console.error("Error loading ticket:", error);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadTicket();
  }, [loadTicket]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [ticket?.messages]);

  const handleReply = async (e) => {
    e.preventDefault();
    if (!reply.trim() || sending) return;
    setSending(true);
    try {
      await adminAPI.replyTicket(id, { content: reply });
      setReply("");
      loadTicket();
    } catch (error) {
      console.error("Error replying:", error);
    } finally {
      setSending(false);
    }
  };

  const handleClose = async () => {
    if (!confirm("Esti sigur ca vrei sa inchizi acest ticket?")) return;
    try {
      await adminAPI.closeTicket(id);
      loadTicket();
    } catch (error) {
      console.error("Error closing ticket:", error);
    }
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{ width: "2.5rem", height: "2.5rem", border: "4px solid #2563eb", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  if (!ticket) {
    return <p style={{ color: "white", textAlign: "center" }}>Ticketul nu a fost gasit.</p>;
  }

  const cardStyle = {
    backgroundColor: "var(--bg-card)", border: "1px solid var(--border-color)",
    borderRadius: "1rem",
  };

  const statusMap = {
    open: { bg: "rgba(250,204,21,0.15)", color: "#facc15", label: "Deschis" },
    in_progress: { bg: "rgba(59,130,246,0.15)", color: "#60a5fa", label: "In progres" },
    closed: { bg: "rgba(34,197,94,0.15)", color: "#4ade80", label: "Inchis" },
  };
  const st = statusMap[ticket.status] || statusMap.open;

  return (
    <div style={{ maxWidth: "800px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <div>
          <Link href="/admin" style={{ display: "flex", alignItems: "center", gap: "0.375rem", color: "#60a5fa", fontSize: "0.8125rem", textDecoration: "none", marginBottom: "0.5rem" }}>
            <ArrowLeft style={{ width: "14px", height: "14px" }} /> Inapoi la pagina principala
          </Link>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <h1 style={{ fontSize: "1.25rem", fontWeight: 700, color: "white", margin: 0 }}>{ticket.subject}</h1>
            <span style={{ padding: "0.125rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.6875rem", backgroundColor: st.bg, color: st.color }}>{st.label}</span>
          </div>
          <p style={{ fontSize: "0.75rem", color: "#64748b", margin: "0.25rem 0 0" }}>
            De la: {ticket.user.full_name || ticket.user.username} ({ticket.user.email}) • {new Date(ticket.created_at).toLocaleDateString("ro-RO")}
          </p>
        </div>
        {ticket.status !== "closed" && (
          <button onClick={handleClose} style={{
            display: "flex", alignItems: "center", gap: "0.375rem",
            padding: "0.5rem 1rem", borderRadius: "0.5rem",
            backgroundColor: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
            color: "#f87171", cursor: "pointer", fontSize: "0.8125rem",
          }}>
            <XCircle style={{ width: "14px", height: "14px" }} /> Inchide ticket
          </button>
        )}
      </div>

      {/* Messages */}
      <div style={{ ...cardStyle, display: "flex", flexDirection: "column", minHeight: "400px", maxHeight: "60vh" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "1.5rem" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {ticket.messages.map((msg) => (
              <div key={msg.id} style={{ display: "flex", gap: "0.75rem", justifyContent: msg.is_admin ? "flex-end" : "flex-start" }}>
                {!msg.is_admin && (
                  <div style={{ width: "32px", height: "32px", borderRadius: "50%", backgroundColor: "#7c3aed", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <User style={{ width: "16px", height: "16px", color: "white" }} />
                  </div>
                )}
                <div style={{
                  maxWidth: "70%", padding: "0.75rem 1rem", borderRadius: "1rem",
                  ...(msg.is_admin
                    ? { backgroundColor: "#2563eb", color: "white", borderBottomRightRadius: "0.25rem" }
                    : { backgroundColor: "#334155", color: "#e2e8f0", borderBottomLeftRadius: "0.25rem" }),
                }}>
                  <p style={{ fontSize: "0.6875rem", fontWeight: 600, margin: "0 0 0.25rem", opacity: 0.7 }}>
                    {msg.is_admin ? "Admin" : msg.sender_name}
                  </p>
                  <p style={{ fontSize: "0.8125rem", whiteSpace: "pre-wrap", margin: 0, lineHeight: 1.6 }}>{msg.content}</p>
                  <p style={{ fontSize: "0.625rem", margin: "0.375rem 0 0", opacity: 0.5 }}>
                    {new Date(msg.created_at).toLocaleString("ro-RO")}
                  </p>
                </div>
                {msg.is_admin && (
                  <div style={{ width: "32px", height: "32px", borderRadius: "50%", backgroundColor: "#dc2626", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Shield style={{ width: "16px", height: "16px", color: "white" }} />
                  </div>
                )}
              </div>
            ))}
          </div>
          <div ref={messagesEndRef} />
        </div>

        {/* Reply input */}
        {ticket.status !== "closed" && (
          <div style={{ padding: "1rem 1.5rem", borderTop: "1px solid var(--border-color)" }}>
            <form onSubmit={handleReply} style={{ display: "flex", gap: "0.75rem" }}>
              <input type="text" value={reply} onChange={(e) => setReply(e.target.value)}
                placeholder="Scrie un raspuns..." disabled={sending}
                style={{
                  flex: 1, padding: "0.75rem 1rem", borderRadius: "0.625rem",
                  backgroundColor: "var(--bg-dark)", border: "1px solid var(--border-color)",
                  color: "white", fontSize: "0.875rem", outline: "none",
                }} />
              <button type="submit" disabled={sending || !reply.trim()}
                style={{
                  padding: "0.75rem 1.25rem", borderRadius: "0.625rem",
                  backgroundColor: "#2563eb", border: "none", color: "white",
                  cursor: sending ? "not-allowed" : "pointer",
                  opacity: sending || !reply.trim() ? 0.5 : 1,
                  display: "flex", alignItems: "center", gap: "0.375rem",
                  fontSize: "0.8125rem", fontWeight: 600,
                }}>
                <Send style={{ width: "16px", height: "16px" }} /> Trimite
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
