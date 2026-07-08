import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthContext";
import { askAI } from "./api";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

const EXAMPLES = [
  "How much did I spend last month?",
  "What's my biggest category?",
  "How much on Food & Drink?",
];

// Splits on existing newlines if the answer has them; otherwise falls back
// to sentence breaks so a single-paragraph answer still prints in beats
// rather than flashing in as one block.
function answerLines(text) {
  const byNewline = text.split(/\n+/).map((l) => l.trim()).filter(Boolean);
  if (byNewline.length > 1) return byNewline;
  return text.split(/(?<=[.!?])\s+/).map((l) => l.trim()).filter(Boolean);
}

export default function AskAI() {
  const { token } = useAuth();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const holderRef = useRef(null);

  async function ask(q) {
    const query = (q ?? question).trim();
    if (!query) return;
    setQuestion(query);
    setLoading(true);
    setError("");
    setAnswer("");
    try {
      const data = await askAI(token, query);
      setAnswer(data.answer);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter") ask();
  }

  useEffect(() => {
    if (!answer || !holderRef.current) return;
    const holder = holderRef.current;
    holder.innerHTML = "";
    const lines = answerLines(answer);
    const PER = 90;
    lines.forEach((line, i) => {
      const el = document.createElement("p");
      el.className = "kalla-ai-line";
      el.textContent = line;
      holder.appendChild(el);
      setTimeout(() => { el.style.opacity = "1"; }, i * PER);
    });
  }, [answer]);

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-3">
        <style>{`
          .kalla-ai-line {
            font-family: ui-monospace, monospace;
            font-size: 12.5px;
            line-height: 1.7;
            color: #E8EDF2;
            opacity: 0;
            transition: opacity 0.15s ease;
            margin: 0 0 4px;
          }
        `}</style>

        <div>
          <h2 className="text-base font-medium">Ask about your spending</h2>
          <p className="text-sm text-muted-foreground">
            Ask a question in plain English and get an answer from your data.
          </p>
        </div>

        <div className="flex gap-2">
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="e.g. How much did I spend on transport this month?"
          />
          <Button onClick={() => ask()} disabled={loading} className="font-medium">
            {loading ? "Thinking..." : "Ask"}
          </Button>
        </div>

        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => ask(ex)}
              disabled={loading}
              className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:opacity-50"
            >
              {ex}
            </button>
          ))}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {answer && (
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <div ref={holderRef} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}