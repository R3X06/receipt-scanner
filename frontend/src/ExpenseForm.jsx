import { useState, useEffect } from "react";
import { createExpense, getAccounts } from "./api";
import { useAuth } from "./AuthContext";
import { CATEGORIES, CURRENCIES } from "./constants";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

export default function ExpenseForm({ onExpenseAdded }) {
  const { token } = useAuth();
  const [amount, setAmount] = useState("");
  const [merchant, setMerchant] = useState("");
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [category, setCategory] = useState("Other");
  const [currency, setCurrency] = useState("SGD");
  const [accounts, setAccounts] = useState([]);
  const [fromId, setFromId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getAccounts(token).then((d) => {
      const accs = d.accounts || [];
      setAccounts(accs);
      const spending = accs.find((a) => a.type === "spending");
      if (spending) setFromId(spending.id);
    }).catch(() => {});
  }, [token]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const acc = accounts.find((a) => a.id === fromId);
      const expense = await createExpense(token, {
        amount: parseFloat(amount),
        merchant,
        date,
        category,
        currency,
        from_account_id: fromId || null,
        from_type: acc?.type,
        from_name: acc?.name,
      });
      onExpenseAdded(expense);
      setAmount("");
      setMerchant("");
      setDate(new Date().toISOString().split("T")[0]);
    } catch (err) {
      setError(err.message);
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
            <Input type="text" placeholder="Merchant" value={merchant} onChange={(e) => setMerchant(e.target.value)} required />
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} required className="[&::-webkit-calendar-picker-indicator]:invert" />
            <div className="col-span-2">
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Select value={fromId} onValueChange={setFromId}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Paid from" /></SelectTrigger>
                <SelectContent>
                  {accounts.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.type === "spending" ? "Spending" : `Savings · ${a.name}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={loading} className="w-full font-medium">
            {loading ? "Adding..." : "Add expense"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}