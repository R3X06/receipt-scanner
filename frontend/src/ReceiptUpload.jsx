import { useState } from "react";
import { useAuth } from "./AuthContext";
//import { createExpense, suggestCategory } from "./api";
import { CATEGORIES, CURRENCIES } from "./constants";
import { createExpense, extractFields } from "./api";


const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const inputStyle = {
  width: "100%",
  padding: "10px 14px",
  border: "1px solid #ddd",
  borderRadius: "8px",
  fontSize: "15px",
  background: "white",
  boxSizing: "border-box",
};

const labelStyle = {
  display: "block",
  fontSize: "12px",
  color: "#888",
  marginBottom: "4px",
};

export default function ReceiptUpload({ onExpenseAdded }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [inputKey, setInputKey] = useState(0);

  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  async function handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    setError("");
    setSaveError("");
    setDraft(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_URL}/ocr`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "OCR failed");

      // OCR fallbacks
      let merchant = data.merchant === "Unknown" ? "" : (data.merchant || "");
      let category = CATEGORIES.includes(data.category) ? data.category : "Other";

      // Ask the AI to pull the real merchant + category from the scanned text.
      try {
        const ex = await extractFields(token, { raw_text: data.raw_ocr_text });
        if (ex?.merchant) merchant = ex.merchant;
        if (ex?.category && CATEGORIES.includes(ex.category)) category = ex.category;
      } catch {
        // best-effort — keep the OCR fallbacks
      }

      setDraft({
        merchant,
        amount: data.amount ? String(data.amount) : "",
        date: data.date || "",
        category,
        currency: CURRENCIES.includes(data.currency) ? data.currency : "USD",
        raw_ocr_text: data.raw_ocr_text || "",
        parsed_ok: data.parsed_ok,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setInputKey((prev) => prev + 1);
    }
  }

  function updateField(field, value) {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSave() {
    if (!draft) return;

    const amountNum = parseFloat(draft.amount);
    if (isNaN(amountNum) || amountNum <= 0) {
      setSaveError("Please enter a valid amount.");
      return;
    }
    if (!draft.merchant.trim()) {
      setSaveError("Please enter a merchant.");
      return;
    }

    setSaving(true);
    setSaveError("");
    try {
      const saved = await createExpense(token, {
        amount: amountNum,
        merchant: draft.merchant.trim(),
        date: draft.date,
        category: draft.category,
        currency: draft.currency,
        raw_ocr_text: draft.raw_ocr_text,
        parsed_ok: draft.parsed_ok,
      });
      onExpenseAdded(saved);
      setDraft(null);
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function handleDiscard() {
    setDraft(null);
    setSaveError("");
  }

  return (
    <div
      style={{
        background: "white",
        borderRadius: "12px",
        padding: "1.5rem",
        boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
        marginBottom: "1.5rem",
      }}
    >
      <h2 style={{ fontSize: "16px", marginBottom: "0.5rem" }}>Scan a receipt</h2>
      <p style={{ fontSize: "13px", color: "#888", marginBottom: "1rem" }}>
        Take a photo or upload an image of your receipt
      </p>

      {!draft && (
        <label
          style={{
            display: "block",
            border: "2px dashed #ddd",
            borderRadius: "8px",
            padding: "2rem",
            textAlign: "center",
            cursor: loading ? "default" : "pointer",
            color: "#888",
            fontSize: "14px",
          }}
        >
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
      )}

      {error && (
        <p className="error" style={{ marginTop: "8px" }}>
          {error}
        </p>
      )}

      {draft && (
        <div
          style={{
            marginTop: "0.5rem",
            padding: "1rem",
            background: "#f9fafb",
            border: "1px solid #eee",
            borderRadius: "8px",
          }}
        >
          <p
            style={{
              fontSize: "13px",
              fontWeight: 500,
              marginBottom: "12px",
              color: draft.parsed_ok ? "#16a34a" : "#ea580c",
            }}
          >
            {draft.parsed_ok
              ? "✓ Receipt scanned — review and edit before saving"
              : "⚠ Couldn't read this clearly — please check every field"}
          </p>

          <div style={{ marginBottom: "12px" }}>
            <label style={labelStyle}>Merchant</label>
            <input
              type="text"
              value={draft.merchant}
              onChange={(e) => updateField("merchant", e.target.value)}
              placeholder="Merchant name"
              style={inputStyle}
            />
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "12px",
              marginBottom: "12px",
            }}
          >
            <div>
              <label style={labelStyle}>Amount</label>
              <input
                type="number"
                value={draft.amount}
                onChange={(e) => updateField("amount", e.target.value)}
                step="0.01"
                min="0"
                placeholder="0.00"
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Currency</label>
              <select
                value={draft.currency}
                onChange={(e) => updateField("currency", e.target.value)}
                style={inputStyle}
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "12px",
              marginBottom: "12px",
            }}
          >
            <div>
              <label style={labelStyle}>Date</label>
              <input
                type="text"
                value={draft.date}
                onChange={(e) => updateField("date", e.target.value)}
                placeholder="As printed on receipt"
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Category</label>
              <select
                value={draft.category}
                onChange={(e) => updateField("category", e.target.value)}
                style={inputStyle}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {draft.raw_ocr_text && (
            <details style={{ marginBottom: "12px" }}>
              <summary style={{ fontSize: "12px", color: "#888", cursor: "pointer" }}>
                Show scanned text
              </summary>
              <pre
                style={{
                  marginTop: "8px",
                  whiteSpace: "pre-wrap",
                  fontSize: "12px",
                  color: "#666",
                  background: "white",
                  border: "1px solid #eee",
                  borderRadius: "6px",
                  padding: "8px",
                  maxHeight: "160px",
                  overflow: "auto",
                }}
              >
                {draft.raw_ocr_text}
              </pre>
            </details>
          )}

          {saveError && (
            <p className="error" style={{ marginBottom: "8px" }}>
              {saveError}
            </p>
          )}

          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={handleDiscard}
              disabled={saving}
              style={{
                width: "auto",
                padding: "10px 16px",
                background: "transparent",
                color: "#888",
                border: "1px solid #ddd",
              }}
            >
              Discard
            </button>
            <button onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
              {saving ? "Saving..." : "Save expense"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}