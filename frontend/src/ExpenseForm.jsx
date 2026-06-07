import { useState } from "react";
import { createExpense } from "./api";
import { useAuth } from "./AuthContext";

const CATEGORIES = [
  "Food & Drink",
  "Transport",
  "Shopping",
  "Health",
  "Entertainment",
  "Utilities",
  "Other",
];

export default function ExpenseForm({ onExpenseAdded }) {
  const { token } = useAuth();
  const [amount, setAmount] = useState("");
  const [merchant, setMerchant] = useState("");
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [category, setCategory] = useState("Food & Drink");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const expense = await createExpense(token, {
        amount: parseFloat(amount),
        merchant,
        date,
        category,
      });
      onExpenseAdded(expense);
      setAmount("");
      setMerchant("");
      setDate(new Date().toISOString().split("T")[0]);
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
      <h2 style={{ fontSize: "16px", marginBottom: "1rem" }}>Add expense</h2>
      <form onSubmit={handleSubmit}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "12px" }}>
          <input
            type="number"
            placeholder="Amount"
            value={amount}
            onChange={e => setAmount(e.target.value)}
            step="0.01"
            min="0"
            required
          />
          <input
            type="text"
            placeholder="Merchant"
            value={merchant}
            onChange={e => setMerchant(e.target.value)}
            required
          />
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            required
          />
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            style={{
              padding: "10px 14px",
              border: "1px solid #ddd",
              borderRadius: "8px",
              fontSize: "15px",
              background: "white",
            }}
          >
            {CATEGORIES.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={loading}>
          {loading ? "Adding..." : "Add expense"}
        </button>
      </form>
    </div>
  );
}