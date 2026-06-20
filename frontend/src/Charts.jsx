import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { Card, CardContent } from "@/components/ui/card";

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
const FALLBACK = ["#A855F7", "#34D6E7", "#818CF8", "#F0B14B", "#F06B9A", "#38BDF8", "#8A97A6"];
const colorFor = (name, i) => CATEGORY_COLORS[name] || FALLBACK[i % FALLBACK.length];

const tooltipStyle = {
  background: "#121821",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 10,
  color: "#E8EDF2",
  fontSize: 13,
};

const baseAmount = (e) => (e.amount_base != null ? e.amount_base : e.amount);

function monthKey(e) {
  for (const c of [e.fx_date, e.date, e.created_at]) {
    if (typeof c === "string") {
      const m = /^(\d{4})-(\d{2})/.exec(c);
      if (m) return `${m[1]}-${m[2]}`;
    }
  }
  return null;
}

function CategoryChart({ expenses, baseCurrency }) {
  const data = expenses
    .reduce((acc, e) => {
      const existing = acc.find((item) => item.name === e.category);
      if (existing) existing.value += baseAmount(e);
      else acc.push({ name: e.category, value: baseAmount(e) });
      return acc;
    }, [])
    .map((d) => ({ ...d, value: parseFloat(d.value.toFixed(2)) }))
    .sort((a, b) => b.value - a.value);

  if (data.length === 0) return null;
  const total = data.reduce((s, d) => s + d.value, 0);

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-1">
        <h2 className="text-base font-medium">Spending by category</h2>
        <p className="text-xs text-muted-foreground">Converted to {baseCurrency}</p>

        <div className="relative mt-2">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={62}
                outerRadius={92}
                paddingAngle={3}
                dataKey="value"
                stroke="none"
              >
                {data.map((d, i) => (
                  <Cell key={i} fill={colorFor(d.name, i)} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={tooltipStyle}
                labelStyle={{ color: "#E8EDF2" }}
                formatter={(val, name) => [`${baseCurrency} ${Number(val).toFixed(2)}`, name]}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-xs text-muted-foreground">Total</span>
            <span className="text-lg font-semibold tabular-nums">{total.toFixed(2)}</span>
          </div>
        </div>

        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
          {data.map((item, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: colorFor(item.name, i) }} />
              <span className="text-muted-foreground">
                {item.name}{" "}
                <span className="text-foreground tabular-nums">
                  {baseCurrency} {item.value.toFixed(2)}
                </span>
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function MonthlyChart({ expenses, baseCurrency }) {
  const data = expenses
    .reduce((acc, e) => {
      const month = monthKey(e);
      if (!month) return acc;
      const existing = acc.find((item) => item.month === month);
      if (existing) existing.amount += baseAmount(e);
      else acc.push({ month, amount: baseAmount(e) });
      return acc;
    }, [])
    .map((d) => ({ ...d, amount: parseFloat(d.amount.toFixed(2)) }))
    .sort((a, b) => a.month.localeCompare(b.month));

  if (data.length === 0) return null;

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-1">
        <h2 className="text-base font-medium">Monthly totals</h2>
        <p className="text-xs text-muted-foreground">Converted to {baseCurrency}</p>

        <div className="mt-2">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data}>
              <defs>
                <linearGradient id="barFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#A855F7" stopOpacity={0.95} />
                  <stop offset="100%" stopColor="#A855F7" stopOpacity={0.25} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 12, fill: "#8A97A6" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12, fill: "#8A97A6" }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.04)" }}
                contentStyle={tooltipStyle}
                labelStyle={{ color: "#E8EDF2" }}
                formatter={(val) => [`${baseCurrency} ${Number(val).toFixed(2)}`, "Spent"]}
              />
              <Bar dataKey="amount" fill="url(#barFill)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

export default function Charts({ expenses, baseCurrency = "SGD" }) {
  if (expenses.length === 0) return null;
  return (
    <>
      <CategoryChart expenses={expenses} baseCurrency={baseCurrency} />
      <MonthlyChart expenses={expenses} baseCurrency={baseCurrency} />
    </>
  );
}