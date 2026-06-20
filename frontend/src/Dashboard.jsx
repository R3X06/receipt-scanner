import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { getExpenses } from "./api";
import { CATEGORIES } from "./constants";
import ExpenseForm from "./ExpenseForm";
import ReceiptUpload from "./ReceiptUpload";
import Charts from "./Charts";
import AskAI from "./AskAI";
import Insights from "./Insights";
import ProfileCard from "./ProfileCard";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LogOut } from "lucide-react";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

const CATEGORY_COLORS = {
  "Food & Drink": "#F0B14B",
  Transport: "#34D6E7",
  Shopping: "#A855F7",
  Health: "#F06B9A",
  Entertainment: "#818CF8",
  Utilities: "#38BDF8",
  Other: "#8A97A6",
};

const TABS = ["Overview", "Expenses", "Scan", "Ask AI"];

export default function Dashboard() {
  const { user, token, logout } = useAuth();
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ start: "", end: "", category: "" });
  const [tab, setTab] = useState("Overview");

  useEffect(() => {
    setLoading(true);
    getExpenses(token, filters)
      .then(setExpenses)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [token, filters]);

  function handleExpenseAdded(expense) {
    setExpenses((prev) => [expense, ...prev]);
  }

  const baseCurrency = user?.primary_currency || "SGD";
  const displayName = user?.email ? user.email.split("@")[0] : "your";
  const hasFilter = !!(filters.start || filters.end || filters.category);

  const currencyTotals = Object.entries(
    expenses.reduce((acc, e) => {
      const cur = e.currency || "USD";
      acc[cur] = (acc[cur] || 0) + e.amount;
      return acc;
    }, {})
  ).sort((a, b) => b[1] - a[1]);

  return (
    <div className="relative min-h-screen p-4 sm:p-6">
      <div className="relative z-10 mx-auto max-w-3xl">
        {/* KALLA wordmark with display name */}
        <div className="pointer-events-none mb-2 select-none text-left text-glow3 leading-none" aria-hidden="true">
          <span
            className="block font-medium capitalize"
            style={{
              fontSize: "clamp(14px, 2vw, 16px)",
              color: "hsla(66, 100%, 98%, 0.18)",
              letterSpacing: "0.04em",
            }}
          >
            {displayName}'s
          </span>
          <span
            className="block font-sans"
            style={{
              fontSize: "clamp(26px, 3vw, 150px)",
              color: "hsla(66, 100%, 98%, 0.18)",
              letterSpacing: "0.08em",
            }}
          >
            KALLA
          </span>
        </div>
        
        {/* top row: profile + tabs + sign out */}
        <div className="mb-6 flex items-start justify-between gap-3">
          <ProfileCard user={user} expenses={expenses} />
          <div className="flex items-center gap-2">
            <div className={`flex gap-1 rounded-full p-1 ${GLASS}`}>
              {TABS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
                    tab === t
                      ? "bg-primary font-medium text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
            <Button
              variant="outline"
              size="icon"
              onClick={logout}
              aria-label="Sign out"
              className="border-white/15 bg-transparent hover:bg-white/5"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* tab content */}
        <div className="space-y-4">
          {tab === "Overview" && (
            <>
              {currencyTotals.length > 0 && (
                <Card className={`${GLASS} rounded-2xl`}>
                  <CardContent className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
                    {currencyTotals.map(([cur, amt], i) => (
                      <div key={cur} className="flex items-baseline gap-1.5">
                        <span
                          className={`font-semibold tabular-nums ${
                            i === 0 ? "text-xl text-foreground" : "text-base text-muted-foreground"
                          }`}
                        >
                          {amt.toFixed(2)}
                        </span>
                        <span
                          className={i === 0 ? "text-xs text-primary" : "text-xs text-muted-foreground"}
                        >
                          {cur}
                        </span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
              <Charts expenses={expenses} baseCurrency={baseCurrency} />
              <Insights />
            </>
          )}

          {tab === "Expenses" && (
            <>
              <Card className={`${GLASS} rounded-2xl`}>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h2 className="text-base font-medium">Filter</h2>
                    {hasFilter && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setFilters({ start: "", end: "", category: "" })}
                        className="text-primary hover:text-primary"
                      >
                        Clear
                      </Button>
                    )}
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="space-y-2">
                      <Label>From</Label>
                      <Input
                        type="date"
                        value={filters.start}
                        onChange={(e) => setFilters((f) => ({ ...f, start: e.target.value }))}
                        className="[&::-webkit-calendar-picker-indicator]:invert"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>To</Label>
                      <Input
                        type="date"
                        value={filters.end}
                        onChange={(e) => setFilters((f) => ({ ...f, end: e.target.value }))}
                        className="[&::-webkit-calendar-picker-indicator]:invert"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Category</Label>
                      <Select
                        value={filters.category || "all"}
                        onValueChange={(v) =>
                          setFilters((f) => ({ ...f, category: v === "all" ? "" : v }))
                        }
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="All categories" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All categories</SelectItem>
                          {CATEGORIES.map((c) => (
                            <SelectItem key={c} value={c}>
                              {c}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <ExpenseForm onExpenseAdded={handleExpenseAdded} />

              <Card className={`${GLASS} overflow-hidden rounded-2xl p-0`}>
                {loading ? (
                  <p className="py-8 text-center text-muted-foreground">Loading...</p>
                ) : expenses.length === 0 ? (
                  <p className="py-8 text-center text-muted-foreground">
                    {hasFilter ? "No expenses match these filters." : "No expenses yet — add one above!"}
                  </p>
                ) : (
                  <div className="divide-y divide-white/5">
                    {expenses.map((e) => (
                      <div key={e.id} className="flex items-center justify-between px-5 py-4">
                        <div className="flex items-center gap-3">
                          <span
                            className="h-2.5 w-2.5 shrink-0 rounded-full"
                            style={{ background: CATEGORY_COLORS[e.category] || "#8A97A6" }}
                          />
                          <div>
                            <p className="font-medium">{e.merchant}</p>
                            <p className="text-sm text-muted-foreground">
                              {e.category} · {e.date}
                            </p>
                          </div>
                        </div>
                        <p className="font-semibold tabular-nums">
                          {e.currency || "USD"} {e.amount.toFixed(2)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </>
          )}

          {tab === "Scan" && <ReceiptUpload onExpenseAdded={handleExpenseAdded} />}

          {tab === "Ask AI" && <AskAI />}
        </div>
      </div>
    </div>
  );
}