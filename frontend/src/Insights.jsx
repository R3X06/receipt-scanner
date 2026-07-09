import { useState } from "react";
import { useAuth } from "./AuthContext";
import { getInsights } from "./api";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { motion, AnimatePresence } from "motion/react";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

export default function Insights() {
  const { token } = useAuth();
  const [insights, setInsights] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    setLoading(true);
    setError("");
    try {
      const data = await getInsights(token);
      setInsights(data.insights);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-medium">Insights</h2>
          <Button onClick={generate} disabled={loading} size="sm" className="font-medium">
            {loading ? "Analyzing..." : insights ? "Refresh" : "Generate"}
          </Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <AnimatePresence mode="wait">
          {insights && (
            <motion.div
              key={insights}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
              className="whitespace-pre-wrap rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm leading-relaxed"
            >
              {insights}
            </motion.div>
          )}
        </AnimatePresence>
        {!insights && !loading && !error && (
          <p className="text-sm text-muted-foreground">
            Tap Generate for AI observations about your spending patterns.
          </p>
        )}
      </CardContent>
    </Card>
  );
}