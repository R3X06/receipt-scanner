import { useState } from "react";
import { AuthProvider, useAuth } from "./AuthContext";
import Login from "./Login";
import Dashboard from "./Dashboard";
import Landing from "./Landing";
import VerifyEmail from "./VerifyEmail";
import ResetPassword from "./ResetPassword";
import { Toaster } from "sonner"

function AppContent() {
  const { user, loading } = useAuth();
  const [showLogin, setShowLogin] = useState(false);

  // No router in this app — these two pages are reachable pre- or post-auth
  // via an emailed link, so they're matched on path before the auth gate.
  const path = window.location.pathname;
  if (path === "/verify-email") return <VerifyEmail />;
  if (path === "/reset-password") return <ResetPassword />;

  if (loading) {
    return (
      <div style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#888",
      }}>
        Loading...
      </div>
    );
  }

  if (user) return <Dashboard />;
  if (showLogin) return <Login onBack={() => setShowLogin(false)} />;
  return <Landing onGetStarted={() => setShowLogin(true)} />;
}

export default function App() {
  return (
    <>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
      <Toaster theme="dark" position="top-center" toastOptions={{
        style: { background: "rgba(255,255,255,0.04)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.1)", color: "#fff" }
      }} />
    </>
  );
}