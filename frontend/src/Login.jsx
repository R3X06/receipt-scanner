import { useState } from "react";
import { login, signup } from "./api";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";

export default function Login() {
  const { saveToken } = useAuth();
  const [isSignup, setIsSignup] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [currency, setCurrency] = useState("SGD");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = isSignup
        ? await signup(email, password, currency)
        : await login(email, password);
      saveToken(data.access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    }}>
      <div style={{
        background: "white",
        padding: "2rem",
        borderRadius: "12px",
        width: "100%",
        maxWidth: "380px",
        boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
      }}>
        <h1 style={{ marginBottom: "0.25rem", fontSize: "22px" }}>
          {isSignup ? "Create account" : "Welcome back"}
        </h1>
        <p style={{ color: "#888", fontSize: "14px", marginBottom: "1.5rem" }}>
          {isSignup ? "Start tracking your expenses" : "Sign in to your account"}
        </p>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "12px" }}>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
          </div>
          <div style={{ marginBottom: isSignup ? "12px" : "16px" }}>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>

          {isSignup && (
            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", fontSize: "12px", color: "#888", marginBottom: "4px" }}>
                Primary currency
              </label>
              <select
                value={currency}
                onChange={e => setCurrency(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 14px",
                  border: "1px solid #ddd",
                  borderRadius: "8px",
                  fontSize: "15px",
                  background: "white",
                  boxSizing: "border-box",
                }}
              >
                {CURRENCIES.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <p style={{ fontSize: "12px", color: "#aaa", marginTop: "4px" }}>
                Your charts will show totals converted into this currency.
              </p>
            </div>
          )}

          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={loading} style={{ marginTop: "8px" }}>
            {loading ? "Please wait..." : isSignup ? "Create account" : "Sign in"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: "1rem", fontSize: "14px", color: "#888" }}>
          {isSignup ? "Already have an account? " : "Don't have an account? "}
          <span
            onClick={() => setIsSignup(!isSignup)}
            style={{ color: "#4f46e5", cursor: "pointer" }}
          >
            {isSignup ? "Sign in" : "Sign up"}
          </span>
        </p>
      </div>
    </div>
  );
}