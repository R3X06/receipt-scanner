import { useState } from "react";
import { resetPassword } from "./api";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function ResetPassword() {
  const token = new URLSearchParams(window.location.search).get("token");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (!token) {
      setError("This link is missing its reset token.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }

    setLoading(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(err.message || "This link is invalid or has expired.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center p-4">
      {/* soft purple glow behind the card, matching Login */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(600px circle at 50% 50%, rgba(49, 15, 81, 0.12), transparent 0%)",
        }}
      />

      <Card className="relative z-10 w-full max-w-sm rounded-2xl border-white/4 bg-white/[0.0] backdrop-blur-xl shadow-2xl shadow-black/30">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-sans tracking-tight text-glow2">
            {done ? "Password reset" : "Reset your password"}
          </CardTitle>
          <CardDescription className="text-glow2">
            {done
              ? "Please log in with your new password."
              : "Choose a new password for your KALLA account."}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {done ? (
            <Button
              className="w-full font-medium text-glow2"
              onClick={() => (window.location.href = "/")}
            >
              Go to login
            </Button>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="new-password" className="text-glow font-sans">
                  New password
                </Label>
                <Input
                  id="new-password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  maxLength={128}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password" className="text-glow font-sans">
                  Confirm password
                </Label>
                <Input
                  id="confirm-password"
                  type="password"
                  placeholder="••••••••"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  minLength={8}
                  maxLength={128}
                />
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" disabled={loading} className="w-full font-medium text-glow2">
                {loading ? "Please wait..." : "Reset password"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}