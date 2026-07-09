import { useState } from "react";
import { toast } from "sonner";
import { createExpense, suggestCategory } from "./api";
import { useAuth } from "./AuthContext";
import { CATEGORIES, CURRENCIES } from "./constants";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export default function ExpenseForm({ onExpenseAdded }) {
  const { token } = useAuth();
  const [amount, setAmount] = useState("");
  const [merchant, setMerchant] = useState("");
  const [when, setWhen] = useState(nowLocal());
  const [category, setCategory] = useState("Other");
  const [categoryTouched, setCategoryTouched] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [currency, setCurrency] = useState("SGD");
  const [walletLinked, setWalletLinked] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // suggest a category from the merchant name, unless the user has already picked one
  async function suggestFromMerchant() {
    const name = merchant.trim();
    if (!name || categoryTouched) return;
    setSuggesting(true);
    try {
      const { category: guess } = await suggestCategory(token, { merchant: name });
      if (guess && CATEGORIES.includes(guess) && !categoryTouched) setCategory(guess);
    } catch {
      // best-effort — leave the current category alone
    } finally {
      setSuggesting(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const date = (when || "").split("T")[0];
      const expense = await createExpense(token, {
        amount: parseFloat(amount),
        merchant,
        date,
        occurred_at: when,
        category,
        currency,
        wallet_linked: walletLinked,
      });
      onExpenseAdded(expense);
      toast.success(`Added ${expense.merchant || "expense"} — ${expense.currency} ${expense.amount}`);
      setAmount("");
      setMerchant("");
      setWhen(nowLocal());
      setWalletLinked(true);
      setCategory("Other");
      setCategoryTouched(false);
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-4">
        <h2 className="text-base font-medium">Add expense</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Input type="number" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} step="0.01" min="0" required />
            <Select value={currency} onValueChange={setCurrency}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
            <Input type="text" placeholder="Merchant" value={merchant} onChange={(e) => setMerchant(e.target.value)} onBlur={suggestFromMerchant} required />
            <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} required className="[&::-webkit-calendar-picker-indicator]:invert" />
            <div className="col-span-2">
              <Select value={category} onValueChange={(v) => { setCategory(v); setCategoryTouched(true); }}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
              {suggesting && <p className="mt-1 text-xs text-muted-foreground">Suggesting a category…</p>}
            </div>
          </div>
          <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer select-none">
            <input type="checkbox" checked={!walletLinked} onChange={(e) => setWalletLinked(!e.target.checked)} className="mt-0.5 h-3.5 w-3.5 rounded border-white/20 bg-white/[0.04] accent-primary" />
            <span>Paid from money I'm not tracking — keep it out of my wallet &amp; surplus (still counts in spending)</span>
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={loading} className="w-full font-medium">
            {loading ? "Adding..." : "Add expense"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
