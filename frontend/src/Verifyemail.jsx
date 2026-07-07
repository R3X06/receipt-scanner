import { useEffect, useState } from "react";
import { verifyEmail } from "./api";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function VerifyEmail() {
  const [token] = useState(() => new URLSearchParams(window.location.search).get("token"));
  const [status, setStatus] = useState(token ? "verifying" : "error"); // 'verifying' | 'success' | 'error'
  const [message, setMessage] = useState(token ? "" : "This link is missing its verification token.");

  useEffect(() => {
    if (!token) return; // already reflected in the initial state above
    verifyEmail(token)
      .then(() => setStatus("success"))
      .catch((err) => {
        setStatus("error");
        setMessage(err.message || "This link is invalid or has expired.");
      });
  }, [token]);

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
            {status === "verifying" && "Verifying your email..."}
            {status === "success" && "Email verified"}
            {status === "error" && "Verification failed"}
          </CardTitle>
          <CardDescription className="text-glow2">
            {status === "verifying" && "One moment."}
            {status === "success" && "Your KALLA account is confirmed."}
            {status === "error" && message}
          </CardDescription>
        </CardHeader>

        {status !== "verifying" && (
          <CardContent>
            <Button
              className="w-full font-medium text-glow2"
              onClick={() => (window.location.href = "/")}
            >
              Continue to KALLA
            </Button>
          </CardContent>
        )}
      </Card>
    </div>
  );
}

//end of code