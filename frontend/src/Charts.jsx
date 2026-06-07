import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from "recharts";

const COLORS = ["#4f46e5", "#7c3aed", "#db2777", "#ea580c", "#ca8a04", "#16a34a", "#0891b2"];

function CategoryChart({ expenses }) {
  const data = expenses.reduce((acc, e) => {
    const existing = acc.find(item => item.name === e.category);
    if (existing) {
      existing.value += e.amount;
    } else {
      acc.push({ name: e.category, value: parseFloat(e.amount.toFixed(2)) });
    }
    return acc;
  }, []);

  if (data.length === 0) return null;

  return (
    <div style={{
      background: "white",
      borderRadius: "12px",
      padding: "1.5rem",
      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
      marginBottom: "1.5rem",
    }}>
      <h2 style={{ fontSize: "16px", marginBottom: "1rem" }}>Spending by category</h2>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={90}
            paddingAngle={3}
            dataKey="value"
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(val) => `$${val.toFixed(2)}`} />
        </PieChart>
      </ResponsiveContainer>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "0.5rem" }}>
        {data.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "13px" }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: COLORS[i % COLORS.length] }} />
            <span>{item.name}: ${item.value.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MonthlyChart({ expenses }) {
  const data = expenses.reduce((acc, e) => {
    if (!e.date) return acc;
    const month = e.date.substring(0, 7);
    const existing = acc.find(item => item.month === month);
    if (existing) {
      existing.amount += e.amount;
    } else {
      acc.push({ month, amount: parseFloat(e.amount.toFixed(2)) });
    }
    return acc;
  }, []).sort((a, b) => a.month.localeCompare(b.month));

  if (data.length === 0) return null;

  return (
    <div style={{
      background: "white",
      borderRadius: "12px",
      padding: "1.5rem",
      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
      marginBottom: "1.5rem",
    }}>
      <h2 style={{ fontSize: "16px", marginBottom: "1rem" }}>Monthly totals</h2>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="month" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val) => `$${val.toFixed(2)}`} />
          <Bar dataKey="amount" fill="#4f46e5" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Charts({ expenses }) {
  if (expenses.length === 0) return null;

  return (
    <>
      <CategoryChart expenses={expenses} />
      <MonthlyChart expenses={expenses} />
    </>
  );
}