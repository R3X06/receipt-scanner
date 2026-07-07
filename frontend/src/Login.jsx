import { useState } from "react";
import { login, signup, forgotPassword } from "./api";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function Login() {
  const { saveToken } = useAuth();
  const [isSignup, setIsSignup] = useState(false);
  const [forgotMode, setForgotMode] = useState(false);
  const [forgotSent, setForgotSent] = useState(false);
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

  async function handleForgotSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await forgotPassword(email);
      setForgotSent(true);
    } catch (err) {
      // Backend already returns a generic message either way — this only
      // fires on a genuine network/server failure, not "email not found".
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function backToSignIn() {
    setForgotMode(false);
    setForgotSent(false);
    setError("");
  }

  if (forgotMode) {
    return (
      <div className="relative min-h-screen flex items-center justify-center p-4">
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
              Reset password
            </CardTitle>
            <CardDescription className="text-glow2">
              {forgotSent
                ? "If that email is registered, a reset link has been sent."
                : "Enter your email and we'll send you a reset link."}
            </CardDescription>
          </CardHeader>

          <CardContent>
            {!forgotSent && (
              <form onSubmit={handleForgotSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="forgot-email" className="text-glow font-sans">Email</Label>
                  <Input
                    id="forgot-email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>

                {error && <p className="text-sm text-destructive">{error}</p>}

                <Button type="submit" disabled={loading} className="w-full font-medium text-glow2">
                  {loading ? "Please wait..." : "Send reset link"}
                </Button>
              </form>
            )}
          </CardContent>

          <CardFooter className="justify-center">
            <button
              type="button"
              onClick={backToSignIn}
              className="text-sm text-primary font-medium hover:underline"
            >
              Back to sign in
            </button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center p-4">
      {/* soft purple glow behind the card */}
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
            {isSignup ? "Create account" : "Welcome back"}
          </CardTitle>
          <CardDescription className = "text-glow2">
            {isSignup ? "Start tracking your expenses" : "Sign in to your account"}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-glow font-sans">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-glow font-sans">Password</Label>
                {!isSignup && (
                  <button
                    type="button"
                    onClick={() => setForgotMode(true)}
                    className="text-xs text-primary font-medium hover:underline"
                  >
                    Forgot password?
                  </button>
                )}
              </div>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            {isSignup && (
              <div className="space-y-2">
                <Label className = "text-glow2">Primary currency</Label>
                <Select value={currency} onValueChange={setCurrency}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select currency" />
                  </SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground text-glow2">
                  Your charts will show totals converted into this currency.
                </p>
              </div>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <Button type="submit" disabled={loading} className="w-full font-medium text-glow2">
              {loading ? "Please wait..." : isSignup ? "Create account" : "Sign in"}
            </Button>
          </form>
        </CardContent>

        <CardFooter className="justify-center">
          <p className="text-sm text-muted-foreground">
            {isSignup ? "Already have an account? " : "Don't have an account? "}
            <button
              type="button"
              onClick={() => setIsSignup(!isSignup)}
              className="text-primary font-medium hover:underline"
            >
              {isSignup ? "Sign in" : "Sign up"}
            </button>
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}