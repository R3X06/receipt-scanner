import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from "recharts";

const COLORS = ["#4f46e5", "#7c3aed", "#db2777", "#ea580c", "#ca8a04", "#16a34a", "#0891b2"];

// Converted base-currency amount, with a fallback for any older rows.
const baseAmount = (e) => (e.amount_base != null ? e.amount_base : e.amount);

// Month bucket from fx_date (ISO), then raw date, then created_at.
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
      const existing = acc.find(item => item.name === e.category);
      if (existing) existing.value += baseAmount(e);
      else acc.push({ name: e.category, value: baseAmount(e) });
      return acc;
    }, [])
    .map(d => ({ ...d, value: parseFloat(d.value.toFixed(2)) }));

  if (data.length === 0) return null;

  return (
    <div style={{
      background: "white",
      borderRadius: "12px",
      padding: "1.5rem",
      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
      marginBottom: "1.5rem",
    }}>
      <h2 style={{ fontSize: "16px", marginBottom: "2px" }}>Spending by category</h2>
      <p style={{ fontSize: "12px", color: "#888", marginBottom: "1rem" }}>Converted to {baseCurrency}</p>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={60} outerRadius={90} paddingAngle={3} dataKey="value">
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
          <Tooltip formatter={(val) => `${baseCurrency} ${val.toFixed(2)}`} />
        </PieChart>
      </ResponsiveContainer>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "0.5rem" }}>
        {data.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "13px" }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: COLORS[i % COLORS.length] }} />
            <span>{item.name}: {baseCurrency} {item.value.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MonthlyChart({ expenses, baseCurrency }) {
  const data = expenses
    .reduce((acc, e) => {
      const month = monthKey(e);
      if (!month) return acc;
      const existing = acc.find(item => item.month === month);
      if (existing) existing.amount += baseAmount(e);
      else acc.push({ month, amount: baseAmount(e) });
      return acc;
    }, [])
    .map(d => ({ ...d, amount: parseFloat(d.amount.toFixed(2)) }))
    .sort((a, b) => a.month.localeCompare(b.month));

  if (data.length === 0) return null;

  return (
    <div style={{
      background: "white",
      borderRadius: "12px",
      padding: "1.5rem",
      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
      marginBottom: "1.5rem",
    }}>
      <h2 style={{ fontSize: "16px", marginBottom: "2px" }}>Monthly totals</h2>
      <p style={{ fontSize: "12px", color: "#888", marginBottom: "1rem" }}>Converted to {baseCurrency}</p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="month" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val) => `${baseCurrency} ${val.toFixed(2)}`} />
          <Bar dataKey="amount" fill="#4f46e5" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
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