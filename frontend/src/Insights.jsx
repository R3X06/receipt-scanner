import { useState } from "react";
import { useAuth } from "./AuthContext";
import { getInsights } from "./api";

export default function Insights() {
  const { token } = useAuth();
  const [insights, setInsights] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    setLoading(true);
    setError("");
    try {
      const data = await getInsights(token);
      setInsights(data.insights);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      background: "white",
      borderRadius: "12px",
      padding: "1.5rem",
      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
      marginBottom: "1.5rem",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: insights || error ? "12px" : 0 }}>
        <h2 style={{ fontSize: "16px" }}>Insights</h2>
        <button onClick={generate} disabled={loading} style={{ width: "auto", padding: "8px 16px", fontSize: "13px" }}>
          {loading ? "Analyzing..." : insights ? "Refresh" : "Generate"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {insights ? (
        <div style={{
          background: "#f9fafb",
          border: "1px solid #eee",
          borderRadius: "8px",
          padding: "12px 14px",
          fontSize: "14px",
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
        }}>
          {insights}
        </div>
      ) : (
        !loading && !error && (
          <p style={{ fontSize: "13px", color: "#888" }}>
            Tap Generate for AI observations about your spending patterns.
          </p>
        )
      )}
    </div>
  );
}