import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { getExpenses } from "./api";
import ExpenseForm from "./ExpenseForm";
import ReceiptUpload from "./ReceiptUpload";
import Charts from "./Charts";

export default function Dashboard() {
  const { user, token, logout } = useAuth();
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getExpenses(token)
      .then(setExpenses)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [token]);

  function handleExpenseAdded(expense) {
    setExpenses(prev => [expense, ...prev]);
  }

  const total = expenses.reduce((sum, e) => sum + e.amount, 0);

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
          background: "#4f46e5",
          borderRadius: "12px",
          padding: "1.5rem",
          marginBottom: "1.5rem",
          color: "white",
        }}>
          <p style={{ fontSize: "13px", opacity: 0.8, marginBottom: "4px" }}>Total spent</p>
          <p style={{ fontSize: "36px", fontWeight: "600" }}>${total.toFixed(2)}</p>
          <p style={{ fontSize: "13px", opacity: 0.8, marginTop: "4px" }}>{expenses.length} expenses</p>
        </div>

        <Charts expenses={expenses} />
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
            <p style={{ padding: "2rem", textAlign: "center", color: "#888" }}>No expenses yet — add one above!</p>
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