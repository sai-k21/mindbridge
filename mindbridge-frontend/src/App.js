import { useState, useRef, useEffect } from "react";
import axios from "axios";

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

function getOrCreateUserId() {
  try {
    let userId = localStorage.getItem("mindbridge_user_id");
    if (!userId) {
      userId = "user_" + Math.random().toString(36).substr(2, 9);
      localStorage.setItem("mindbridge_user_id", userId);
    }
    return userId;
  } catch {
    return "user_" + Math.random().toString(36).substr(2, 9);
  }
}

function getStoredAccessToken() {
  try {
    return localStorage.getItem("mindbridge_access_token");
  } catch {
    return null;
  }
}

function storeAccessToken(token) {
  try {
    if (token) localStorage.setItem("mindbridge_access_token", token);
  } catch {
    // localStorage unavailable — memory features that need the token
    // (like Save memory, or the sessions sidebar) just won't work this
    // session, live chat still will.
  }
}

function newSessionId() {
  return "session_" + Date.now();
}

function formatSessionDate(iso) {
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    return sameDay
      ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [userId] = useState(getOrCreateUserId);
  const [accessToken, setAccessToken] = useState(getStoredAccessToken);
  const [sessionId, setSessionId] = useState(newSessionId);
  const [lastEmotion, setLastEmotion] = useState(null);
  const [showPrivacyNotice, setShowPrivacyNotice] = useState(false);
  const [memoryUpdating, setMemoryUpdating] = useState(false);
  const [memoryMessage, setMemoryMessage] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    const seen = localStorage.getItem("mindbridge_privacy_seen");
    if (!seen) setShowPrivacyNotice(true);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Returning visitor — we already have a token from a past visit, so
  // populate the sidebar immediately without waiting for a new message.
  useEffect(() => {
    if (accessToken) loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dismissPrivacyNotice = () => {
    localStorage.setItem("mindbridge_privacy_seen", "true");
    setShowPrivacyNotice(false);
  };

  const loadSessions = async (token) => {
    const authToken = token || accessToken;
    if (!authToken) return;
    setSessionsLoading(true);
    try {
      const res = await axios.get(`/api/sessions?user_id=${userId}`, {
        headers: { "X-Access-Token": authToken }
      });
      setSessions(res.data.sessions || []);
    } catch {
      // Quietly leave the sidebar as-is — this is a nice-to-have, not
      // worth surfacing an error banner for.
    } finally {
      setSessionsLoading(false);
    }
  };

  const startNewChat = () => {
    setSessionId(newSessionId());
    setMessages([]);
    setLastEmotion(null);
  };

  const loadSession = async (targetSessionId) => {
    if (!accessToken || targetSessionId === sessionId) return;
    setHistoryLoading(true);
    try {
      const res = await axios.get(
        `/api/history?user_id=${userId}&session_id=${targetSessionId}`,
        { headers: { "X-Access-Token": accessToken } }
      );
      const loaded = (res.data.conversations || []).map(c => ({
        role: c.role,
        content: c.content,
        emotion: c.emotion,
        crisis: c.role === "assistant" && c.emotion === "crisis"
      }));
      setMessages(loaded);
      setSessionId(targetSessionId);
      const lastAssistant = [...loaded].reverse().find(m => m.role === "assistant");
      setLastEmotion(lastAssistant?.emotion || null);
    } catch {
      setMessages([{
        role: "assistant",
        content: "Couldn't load that conversation. Please try again.",
        emotion: null
      }]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const updateMemory = async () => {
    setMemoryUpdating(true);
    setMemoryMessage(null);
    try {
      await axios.post(
        `/api/memory-update?user_id=${userId}`,
        {},
        { headers: { "X-Access-Token": accessToken || "" } }
      );
      setMemoryMessage("Memory updated successfully.");
    } catch {
      setMemoryMessage("Nothing to update yet — keep chatting first.");
    } finally {
      setMemoryUpdating(false);
      setTimeout(() => setMemoryMessage(null), 3000);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: userMessage }]);
    setLoading(true);

    try {
      const res = await axios.post(`/api/chat`, {
        user_id: userId,
        session_id: sessionId,
        message: userMessage
      });

      let tokenForRefresh = accessToken;
      if (res.data.access_token) {
        storeAccessToken(res.data.access_token);
        setAccessToken(res.data.access_token);
        tokenForRefresh = res.data.access_token;
      }

      setLastEmotion(res.data.emotion_detected);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: res.data.reply,
        emotion: res.data.emotion_detected,
        crisis: res.data.crisis_escalated
      }]);

      // Refresh the sidebar so this session (new or continued) shows up
      // with its latest preview/timestamp.
      loadSessions(tokenForRefresh);
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
      fontFamily: "'Segoe UI', sans-serif",
      color: "#fff"
    }}>

      {/* Privacy Notice */}
      {showPrivacyNotice && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.8)",
          display: "flex", alignItems: "center", justifyContent: "center",
          zIndex: 1000, padding: 20
        }}>
          <div style={{
            background: "#1a1a2e", border: "1px solid #2a2a3e",
            borderRadius: 16, padding: 32, maxWidth: 440, width: "100%"
          }}>
            <div style={{ fontSize: 24, marginBottom: 12 }}>🔒 Privacy Notice</div>
            <div style={{ fontSize: 14, color: "#aaa", lineHeight: 1.7, marginBottom: 20 }}>
              MindBridge saves a session ID on this device so it can remember
              you across visits. No personal information is collected — no name,
              email, or account required.
              <br /><br />
              <strong style={{ color: "#fff" }}>Do not use on shared or public computers.</strong>
              <br /><br />
              You can clear your data anytime by clearing your browser storage.
            </div>
            <button
              onClick={dismissPrivacyNotice}
              style={{
                width: "100%",
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                border: "none", borderRadius: 10,
                padding: "12px", color: "#fff",
                fontSize: 14, cursor: "pointer", fontWeight: 600
              }}
            >
              I understand — let's go
            </button>
          </div>
        </div>
      )}

      {/* Sidebar */}
      <div style={{
        width: 260,
        flexShrink: 0,
        borderRight: "1px solid #222",
        display: "flex",
        flexDirection: "column",
        padding: "16px 12px",
        height: "100vh",
        position: "sticky",
        top: 0
      }}>
        <button
          onClick={startNewChat}
          style={{
            display: "flex", alignItems: "center", gap: 8,
            background: "#1a1a2e", border: "1px solid #2a2a3e",
            borderRadius: 10, padding: "10px 14px",
            color: "#fff", fontSize: 13, fontWeight: 600,
            cursor: "pointer", marginBottom: 16
          }}
        >
          ✚ New chat
        </button>

        <div style={{
          fontSize: 11, color: "#666", fontWeight: 600,
          letterSpacing: 0.5, textTransform: "uppercase",
          padding: "0 4px", marginBottom: 8
        }}>
          Recent chats
        </div>

        <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
          {sessionsLoading && sessions.length === 0 && (
            <div style={{ fontSize: 12, color: "#555", padding: "8px 4px" }}>Loading…</div>
          )}
          {!sessionsLoading && sessions.length === 0 && (
            <div style={{ fontSize: 12, color: "#555", padding: "8px 4px", lineHeight: 1.5 }}>
              No past chats yet — they'll show up here once you send a message.
            </div>
          )}
          {sessions.map(s => (
            <button
              key={s.session_id}
              onClick={() => loadSession(s.session_id)}
              disabled={historyLoading}
              style={{
                textAlign: "left",
                background: s.session_id === sessionId ? "#1a1a2e" : "transparent",
                border: s.session_id === sessionId ? "1px solid #6366f1" : "1px solid transparent",
                borderRadius: 10,
                padding: "8px 10px",
                cursor: historyLoading ? "wait" : "pointer",
                color: "#ddd"
              }}
            >
              <div style={{
                fontSize: 12.5, lineHeight: 1.4,
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis"
              }}>
                {s.preview || "New conversation"}
              </div>
              <div style={{ fontSize: 10.5, color: "#666", marginTop: 2 }}>
                {formatSessionDate(s.last_message_at)} · {s.message_count} msg{s.message_count === 1 ? "" : "s"}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Main column */}
      <div style={{
        flex: 1, minWidth: 0,
        display: "flex", flexDirection: "column", alignItems: "center"
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
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
              {lastEmotion && (
                <div style={{
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
              <button
                onClick={updateMemory}
                disabled={memoryUpdating}
                title="Save this session to long-term memory"
                style={{
                  background: "#1a1a2e",
                  border: "1px solid #2a2a3e",
                  borderRadius: 20,
                  padding: "4px 12px",
                  fontSize: 12,
                  color: memoryUpdating ? "#555" : "#888",
                  cursor: memoryUpdating ? "wait" : "pointer"
                }}
              >
                {memoryUpdating ? "Saving..." : "💾 Save memory"}
              </button>
            </div>
          </div>
          {memoryMessage && (
            <div style={{
              marginTop: 8, fontSize: 12,
              color: "#4CAF50", textAlign: "right"
            }}>
              {memoryMessage}
            </div>
          )}
        </div>

        {/* Messages */}
        <div style={{
          flex: 1, width: "100%", maxWidth: 700,
          padding: "20px", overflowY: "auto",
          display: "flex", flexDirection: "column", gap: 16,
          minHeight: "calc(100vh - 160px)"
        }}>
          {historyLoading && (
            <div style={{ textAlign: "center", color: "#555", marginTop: 80 }}>
              Loading conversation…
            </div>
          )}

          {!historyLoading && messages.length === 0 && (
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

          {!historyLoading && messages.map((msg, i) => (
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
        </div>
      </div>
    </div>
  );
}