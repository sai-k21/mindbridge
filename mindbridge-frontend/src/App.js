import { useState, useRef, useEffect } from "react";
import axios from "axios";

const API = "https://mindbridge-api-vh6n.onrender.com";

const EMOTION_COLORS = {
  calm: "#4CAF50",
  stressed: "#FF9800",
  anxious: "#FF5722",
  overwhelmed: "#F44336",
  crisis: "#9C27B0"
};

const EMOTION_EMOJI = {
  calm: "😌",
  stressed: "😰",
  anxious: "😟",
  overwhelmed: "😩",
  crisis: "🆘"
};

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [userId] = useState("user_" + Math.random().toString(36).substr(2, 6));
  const [sessionId] = useState("session_" + Date.now());
  const [lastEmotion, setLastEmotion] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: userMessage }]);
    setLoading(true);

    try {
      const res = await axios.post(`${API}/chat`, null, {
        params: { user_id: userId, session_id: sessionId, message: userMessage }
      });

      setLastEmotion(res.data.emotion_detected);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: res.data.reply,
        emotion: res.data.emotion_detected,
        crisis: res.data.crisis_escalated
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "Something went wrong. Please try again.",
        emotion: null
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0f0f13",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      fontFamily: "'Segoe UI', sans-serif",
      color: "#fff"
    }}>
      {/* Header */}
      <div style={{
        width: "100%",
        maxWidth: 700,
        padding: "24px 20px 12px",
        borderBottom: "1px solid #222"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 40, height: 40, borderRadius: "50%",
            background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 20
          }}>🧠</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 18 }}>MindBridge</div>
            <div style={{ fontSize: 12, color: "#888" }}>
              AI companion with persistent memory
            </div>
          </div>
          {lastEmotion && (
            <div style={{
              marginLeft: "auto",
              background: "#1a1a2e",
              border: `1px solid ${EMOTION_COLORS[lastEmotion]}`,
              borderRadius: 20,
              padding: "4px 12px",
              fontSize: 13,
              color: EMOTION_COLORS[lastEmotion]
            }}>
              {EMOTION_EMOJI[lastEmotion]} {lastEmotion}
            </div>
          )}
        </div>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1, width: "100%", maxWidth: 700,
        padding: "20px", overflowY: "auto",
        display: "flex", flexDirection: "column", gap: 16,
        minHeight: "calc(100vh - 160px)"
      }}>
        {messages.length === 0 && (
          <div style={{
            textAlign: "center", color: "#555",
            marginTop: 80, lineHeight: 1.8
          }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>🌿</div>
            <div style={{ fontSize: 16, color: "#666" }}>
              MindBridge remembers you across every session.
            </div>
            <div style={{ fontSize: 13, color: "#444", marginTop: 8 }}>
              How are you feeling today?
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={{
            display: "flex",
            justifyContent: msg.role === "user" ? "flex-end" : "flex-start"
          }}>
            <div style={{
              maxWidth: "80%",
              background: msg.role === "user"
                ? "linear-gradient(135deg, #6366f1, #8b5cf6)"
                : msg.crisis ? "#2d0a3a" : "#1a1a2e",
              border: msg.crisis ? "1px solid #9C27B0" :
                msg.role === "assistant" ? "1px solid #2a2a3e" : "none",
              borderRadius: msg.role === "user"
                ? "18px 18px 4px 18px"
                : "18px 18px 18px 4px",
              padding: "12px 16px",
              fontSize: 14,
              lineHeight: 1.6,
              color: "#fff",
              whiteSpace: "pre-wrap"
            }}>
              {msg.content}
              {msg.emotion && msg.role === "assistant" && (
                <div style={{
                  marginTop: 8,
                  fontSize: 11,
                  color: EMOTION_COLORS[msg.emotion] || "#666",
                  opacity: 0.8
                }}>
                  {EMOTION_EMOJI[msg.emotion]} detected: {msg.emotion}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ display: "flex", justifyContent: "flex-start" }}>
            <div style={{
              background: "#1a1a2e", border: "1px solid #2a2a3e",
              borderRadius: "18px 18px 18px 4px",
              padding: "12px 16px", fontSize: 14, color: "#666"
            }}>
              MindBridge is thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        width: "100%", maxWidth: 700,
        padding: "16px 20px",
        borderTop: "1px solid #222",
        background: "#0f0f13"
      }}>
        <div style={{ display: "flex", gap: 12 }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="How are you feeling today? (Enter to send)"
            rows={2}
            style={{
              flex: 1, background: "#1a1a2e",
              border: "1px solid #2a2a3e", borderRadius: 12,
              padding: "12px 16px", color: "#fff",
              fontSize: 14, resize: "none", outline: "none",
              fontFamily: "inherit", lineHeight: 1.5
            }}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            style={{
              background: loading || !input.trim()
                ? "#2a2a3e"
                : "linear-gradient(135deg, #6366f1, #8b5cf6)",
              border: "none", borderRadius: 12,
              width: 50, cursor: loading ? "wait" : "pointer",
              fontSize: 20, color: "#fff",
              transition: "all 0.2s"
            }}
          >
            ↑
          </button>
        </div>
        <div style={{ fontSize: 11, color: "#333", marginTop: 8, textAlign: "center" }}>
          Your session: {sessionId} • Memory persists across sessions
        </div>
      </div>
    </div>
  );
}