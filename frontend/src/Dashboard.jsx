import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { getExpenses } from "./api";
import { CATEGORIES } from "./constants";
import ExpenseForm from "./ExpenseForm";
import ReceiptUpload from "./ReceiptUpload";
import Charts from "./Charts";
import AskAI from "./AskAI";
import Insights from "./Insights";

const fInput = {
  width: "100%",
  padding: "10px 14px",
  border: "1px solid #ddd",
  borderRadius: "8px",
  fontSize: "15px",
  background: "white",
  boxSizing: "border-box",
};

const fLabel = { display: "block", fontSize: "12px", color: "#888", marginBottom: "4px" };

export default function Dashboard() {
  const { user, token, logout } = useAuth();
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ start: "", end: "", category: "" });

  useEffect(() => {
    setLoading(true);
    getExpenses(token, filters)
      .then(setExpenses)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [token, filters]);

  function handleExpenseAdded(expense) {
    setExpenses(prev => [expense, ...prev]);
  }

  const baseCurrency = user?.primary_currency || "SGD";
  const hasFilter = !!(filters.start || filters.end || filters.category);

  const currencyTotals = Object.entries(
    expenses.reduce((acc, e) => {
      const cur = e.currency || "USD";
      acc[cur] = (acc[cur] || 0) + e.amount;
      return acc;
    }, {})
  ).sort((a, b) => b[1] - a[1]);

  return (
    <div style={{ minHeight: "100vh", padding: "2rem" }}>
      <div style={{ maxWidth: "800px", margin: "0 auto" }}>

        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1.5rem",
          background: "white",
          padding: "1rem 1.5rem",
          borderRadius: "12px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
        }}>
          <div>
            <h1 style={{ fontSize: "20px", marginBottom: "2px" }}>Receipt Scanner</h1>
            <p style={{ color: "#888", fontSize: "13px" }}>{user?.email}</p>
          </div>
          <button
            onClick={logout}
            style={{
              width: "auto",
              padding: "8px 16px",
              background: "transparent",
              color: "#888",
              border: "1px solid #ddd",
              fontSize: "13px",
            }}
          >
            Sign out
          </button>
        </div>

        <div style={{
          background: "white",
          borderRadius: "12px",
          padding: "1.5rem",
          marginBottom: "1.5rem",
          boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
        }}>
          <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "12px",
          }}>
            <h2 style={{ fontSize: "16px" }}>Filter</h2>
            {hasFilter && (
              <button
                onClick={() => setFilters({ start: "", end: "", category: "" })}
                style={{
                  width: "auto",
                  padding: "6px 12px",
                  background: "transparent",
                  color: "#4f46e5",
                  border: "1px solid #ddd",
                  fontSize: "13px",
                }}
              >
                Clear
              </button>
            )}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "12px" }}>
            <div>
              <label style={fLabel}>From</label>
              <input
                type="date"
                value={filters.start}
                onChange={e => setFilters(f => ({ ...f, start: e.target.value }))}
                style={fInput}
              />
            </div>
            <div>
              <label style={fLabel}>To</label>
              <input
                type="date"
                value={filters.end}
                onChange={e => setFilters(f => ({ ...f, end: e.target.value }))}
                style={fInput}
              />
            </div>
            <div>
              <label style={fLabel}>Category</label>
              <select
                value={filters.category}
                onChange={e => setFilters(f => ({ ...f, category: e.target.value }))}
                style={fInput}
              >
                <option value="">All categories</option>
                {CATEGORIES.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div style={{
          background: "#4f46e5",
          borderRadius: "12px",
          padding: "1.5rem",
          marginBottom: "1.5rem",
          color: "white",
        }}>
          <p style={{ fontSize: "13px", opacity: 0.8, marginBottom: "8px" }}>
            {hasFilter ? "Total spent (filtered)" : "Total spent"}
          </p>
          {currencyTotals.length === 0 ? (
            <p style={{ fontSize: "36px", fontWeight: "600" }}>—</p>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "1.5rem", alignItems: "baseline" }}>
              {currencyTotals.map(([cur, amt]) => (
                <div key={cur}>
                  <span style={{ fontSize: "32px", fontWeight: "600" }}>{amt.toFixed(2)}</span>
                  <span style={{ fontSize: "15px", marginLeft: "6px", opacity: 0.85 }}>{cur}</span>
                </div>
              ))}
            </div>
          )}
          <p style={{ fontSize: "13px", opacity: 0.8, marginTop: "8px" }}>{expenses.length} expenses</p>
        </div>

        <Charts expenses={expenses} baseCurrency={baseCurrency} />
        <AskAI />
        <Insights />
        <ReceiptUpload onExpenseAdded={handleExpenseAdded} />
        <ExpenseForm onExpenseAdded={handleExpenseAdded} />

        <div style={{
          background: "white",
          borderRadius: "12px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
          overflow: "hidden",
        }}>
          {loading ? (
            <p style={{ padding: "2rem", textAlign: "center", color: "#888" }}>Loading...</p>
          ) : expenses.length === 0 ? (
            <p style={{ padding: "2rem", textAlign: "center", color: "#888" }}>
              {hasFilter ? "No expenses match these filters." : "No expenses yet — add one above!"}
            </p>
          ) : (
            expenses.map((e, i) => (
              <div key={e.id} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "1rem 1.5rem",
                borderBottom: i < expenses.length - 1 ? "1px solid #f0f0f0" : "none",
              }}>
                <div>
                  <p style={{ fontWeight: "500", marginBottom: "2px" }}>{e.merchant}</p>
                  <p style={{ fontSize: "13px", color: "#888" }}>{e.category} · {e.date}</p>
                </div>
                <p style={{ fontWeight: "600", color: "#4f46e5" }}>{e.currency || "USD"} {e.amount.toFixed(2)}</p>
              </div>
            ))
          )}
        </div>

      </div>
    </div>
  );
}