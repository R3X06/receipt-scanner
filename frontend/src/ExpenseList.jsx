import { useState } from "react";
import { useAuth } from "./AuthContext";
import { CATEGORIES, CURRENCIES } from "./constants";
import { updateExpense, deleteExpense } from "./api";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Pencil, Trash2, Check, X } from "lucide-react";

const CATEGORY_COLORS = {
  "Food & Drink": "#F0B14B",
  Transport: "#34D6E7",
  Shopping: "#A855F7",
  Health: "#F06B9A",
  Entertainment: "#818CF8",
  Utilities: "#38BDF8",
  Other: "#8A97A6",
};

function ExpenseRow({ expense, onUpdated, onDeleted }) {
  const { token } = useAuth();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    merchant: expense.merchant || "",
    amount: String(expense.amount ?? ""),
    currency: expense.currency || "SGD",
    date: expense.date || "",
    category: CATEGORIES.includes(expense.category) ? expense.category : "Other",
  });

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    const amountNum = parseFloat(form.amount);
    if (isNaN(amountNum) || amountNum <= 0) return setError("Enter a valid amount.");
    if (!form.merchant.trim()) return setError("Enter a merchant.");
    setBusy(true);
    setError("");
    try {
      const updated = await updateExpense(token, expense.id, {
        amount: amountNum,
        merchant: form.merchant.trim(),
        date: form.date,
        category: form.category,
        currency: form.currency,
      });
      onUpdated(updated);
      setEditing(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await deleteExpense(token, expense.id);
      onDeleted(expense.id);
    } catch (err) {
      setError(err.message);
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  if (editing) {
    return (
      <div className="space-y-3 px-5 py-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Input
            value={form.merchant}
            onChange={(e) => setField("merchant", e.target.value)}
            placeholder="Merchant"
          />
          <div className="grid grid-cols-2 gap-2">
            <Input
              type="number"
              value={form.amount}
              onChange={(e) => setField("amount", e.target.value)}
              step="0.01"
              min="0"
              placeholder="Amount"
            />
            <Select value={form.currency} onValueChange={(v) => setField("currency", v)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CURRENCIES.map((c) => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Input
            type="text"
            value={form.date}
            onChange={(e) => setField("date", e.target.value)}
            placeholder="Date (as printed)"
          />
          <Select value={form.category} onValueChange={(v) => setField("category", v)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((c) => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setEditing(false); setError(""); }}
            disabled={busy}
            className="border-white/15 bg-transparent hover:bg-white/5"
          >
            <X className="mr-1 h-3.5 w-3.5" /> Cancel
          </Button>
          <Button size="sm" onClick={save} disabled={busy} className="font-medium">
            <Check className="mr-1 h-3.5 w-3.5" /> {busy ? "Saving..." : "Save"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between gap-3 px-5 py-4">
      <div className="flex min-w-0 items-center gap-3">
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ background: CATEGORY_COLORS[expense.category] || "#8A97A6" }}
        />
        <div className="min-w-0">
          <p className="truncate font-medium">{expense.merchant}</p>
          <p className="truncate text-sm text-muted-foreground">
            {expense.category} · {expense.date}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <p className="font-semibold tabular-nums">
          {expense.currency || "SGD"} {Number(expense.amount).toFixed(2)}
        </p>
        {confirmDelete ? (
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground">Delete?</span>
            <button onClick={remove} disabled={busy} aria-label="Confirm delete"
              className="text-destructive hover:opacity-80">
              <Check className="h-4 w-4" />
            </button>
            <button onClick={() => setConfirmDelete(false)} disabled={busy} aria-label="Cancel delete"
              className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button onClick={() => setEditing(true)} aria-label="Edit expense"
              className="text-muted-foreground hover:text-foreground">
              <Pencil className="h-4 w-4" />
            </button>
            <button onClick={() => setConfirmDelete(true)} aria-label="Delete expense"
              className="text-muted-foreground hover:text-destructive">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ExpenseList({ expenses, loading, hasFilter, onUpdated, onDeleted }) {
  if (loading) {
    return <p className="py-8 text-center text-muted-foreground">Loading...</p>;
  }
  if (!expenses.length) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        {hasFilter ? "No expenses match these filters." : "No expenses yet — add one above!"}
      </p>
    );
  }
  return (
    <div className="divide-y divide-white/5">
      {expenses.map((e) => (
        <ExpenseRow key={e.id} expense={e} onUpdated={onUpdated} onDeleted={onDeleted} />
      ))}
    </div>
  );
}