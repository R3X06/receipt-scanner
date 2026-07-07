import { AuthProvider, useAuth } from "./AuthContext";
import Login from "./Login";
import Dashboard from "./Dashboard";
import VerifyEmail from "./VerifyEmail";
import ResetPassword from "./ResetPassword";

function AppContent() {
  const { user, loading } = useAuth();

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

  return (
    <>
      {user ? <Dashboard /> : <Login />}
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}