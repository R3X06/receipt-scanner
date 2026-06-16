import { useState } from "react";
import { useAuth } from "./AuthContext";
import { askAI } from "./api";

const EXAMPLES = [
  "How much did I spend last month?",
  "What's my biggest category?",
  "How much on Food & Drink?",
];

export default function AskAI() {
  const { token } = useAuth();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function ask(q) {
    const query = (q ?? question).trim();
    if (!query) return;
    setQuestion(query);
    setLoading(true);
    setError("");
    setAnswer("");
    try {
      const data = await askAI(token, query);
      setAnswer(data.answer);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter") ask();
  }

  return (
    <div style={{
      background: "white",
      borderRadius: "12px",
      padding: "1.5rem",
      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
      marginBottom: "1.5rem",
    }}>
      <h2 style={{ fontSize: "16px", marginBottom: "0.25rem" }}>Ask about your spending</h2>
      <p style={{ fontSize: "13px", color: "#888", marginBottom: "1rem" }}>
        Ask a question in plain English and get an answer from your data.
      </p>

      <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="e.g. How much did I spend on transport this month?"
          style={{
            flex: 1,
            padding: "10px 14px",
            border: "1px solid #ddd",
            borderRadius: "8px",
            fontSize: "15px",
            boxSizing: "border-box",
          }}
        />
        <button onClick={() => ask()} disabled={loading} style={{ width: "auto", padding: "10px 18px" }}>
          {loading ? "Thinking..." : "Ask"}
        </button>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: (answer || error) ? "12px" : 0 }}>
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => ask(ex)}
            disabled={loading}
            style={{
              width: "auto",
              padding: "5px 10px",
              fontSize: "12px",
              background: "#f3f4f6",
              color: "#4f46e5",
              border: "1px solid #e5e7eb",
            }}
          >
            {ex}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}

      {answer && (
        <div style={{
          background: "#f9fafb",
          border: "1px solid #eee",
          borderRadius: "8px",
          padding: "12px 14px",
          fontSize: "14px",
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
        }}>
          {answer}
        </div>
      )}
    </div>
  );
}