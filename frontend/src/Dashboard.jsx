import { useAuth } from "./AuthContext";

export default function Dashboard() {
  const { user, logout } = useAuth();

  return (
    <div style={{
      minHeight: "100vh",
      padding: "2rem",
    }}>
      <div style={{
        maxWidth: "800px",
        margin: "0 auto",
      }}>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "2rem",
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
          padding: "3rem",
          textAlign: "center",
          boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
        }}>
          <p style={{ fontSize: "48px", marginBottom: "1rem" }}>🧾</p>
          <h2 style={{ fontSize: "18px", marginBottom: "8px" }}>No expenses yet</h2>
          <p style={{ color: "#888", fontSize: "14px" }}>
            Receipt scanning coming in Phase 2
          </p>
        </div>
      </div>
    </div>
  );
}