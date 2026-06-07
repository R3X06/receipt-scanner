import { useState } from "react";
import { useAuth } from "./AuthContext";

export default function ReceiptUpload({ onExpenseAdded }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [inputKey, setInputKey] = useState(0);

  async function handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("http://localhost:8000/ocr", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "OCR failed");

      setResult(data);
      setInputKey(prev => prev + 1);
      onExpenseAdded(data.expense);
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
      <h2 style={{ fontSize: "16px", marginBottom: "0.5rem" }}>Scan a receipt</h2>
      <p style={{ fontSize: "13px", color: "#888", marginBottom: "1rem" }}>
        Take a photo or upload an image of your receipt
      </p>

      <label style={{
        display: "block",
        border: "2px dashed #ddd",
        borderRadius: "8px",
        padding: "2rem",
        textAlign: "center",
        cursor: "pointer",
        color: "#888",
        fontSize: "14px",
      }}>
        {loading ? "Scanning..." : "📷 Click to upload receipt"}
        <input
          key={inputKey}
          type="file"
          accept="image/*"
          onChange={handleUpload}
          style={{ display: "none" }}
          disabled={loading}
        />
      </label>

      {error && <p className="error" style={{ marginTop: "8px" }}>{error}</p>}

      {result && (
        <div style={{
          marginTop: "1rem",
          padding: "1rem",
          background: result.parsed_ok ? "#f0fdf4" : "#fff7ed",
          borderRadius: "8px",
          fontSize: "14px",
        }}>
          {result.parsed_ok ? (
            <>
              <p style={{ color: "#16a34a", fontWeight: "500", marginBottom: "4px" }}>✓ Receipt scanned</p>
              <p>Merchant: <strong>{result.expense.merchant}</strong></p>
              <p>Amount: <strong>${result.expense.amount.toFixed(2)}</strong></p>
              <p>Date: <strong>{result.expense.date || "Not found"}</strong></p>
            </>
          ) : (
            <p style={{ color: "#ea580c" }}>⚠ Couldn't parse receipt clearly — expense saved, please review it</p>
          )}
        </div>
      )}
    </div>
  );
}