const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function signup(email, password) {
  const res = await fetch(`${API_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Signup failed");
  return data;
}

export async function login(email, password) {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Login failed");
  return data;
}

export async function getMe(token) {
  const res = await fetch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Not authenticated");
  return data;
}

export async function askAI(token, question) {
  const res = await fetch(`${API_URL}/ai/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "AI request failed");
  return data;
}

export async function getInsights(token) {
  const res = await fetch(`${API_URL}/ai/insights`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "AI request failed");
  return data;
}

export async function suggestCategory(token, payload) {
  const res = await fetch(`${API_URL}/ai/categorize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "AI request failed");
  return data;
}

export async function extractFields(token, payload) {
  const res = await fetch(`${API_URL}/ai/extract`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "AI request failed");
  return data;
}

// ledger expense entry -> the legacy shape the UI components expect
function toLegacyExpense(e) {
  return {
    id: e.id,
    amount: e.amount,
    amount_base: e.amount_base,
    currency: e.currency || "SGD",
    category: e.category || "Other",
    merchant: e.counterparty || "Unknown",
    date: e.date || e.fx_date || "",
    fx_date: e.fx_date || e.date || "",
    note: e.note || "",
    from_account_id: e.from_account_id || null,
    from_name: e.from || null,
    wallet_linked: e.wallet_linked != null ? e.wallet_linked : true,
    funding_source: e.from_type === "goal" ? "savings" : "spending",
  };
}

export async function createExpense(token, expense) {
  const res = await fetch(`${API_URL}/ledger/expense`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      amount: expense.amount,
      merchant: expense.merchant,
      date: expense.date,
      category: expense.category,
      currency: expense.currency,
      from_account_id: expense.from_account_id || null,
      occurred_at: expense.occurred_at || null,
      wallet_linked: expense.wallet_linked != null ? expense.wallet_linked : true,
      raw_ocr_text: expense.raw_ocr_text || "",
      parsed_ok: expense.parsed_ok != null ? expense.parsed_ok : true,
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to create expense");
  // map raw entry -> legacy; use the form's hints so the savings pill is right immediately
  return toLegacyExpense({ ...data, from: expense.from_name, from_type: expense.from_type });
}

export async function getExpenses(token, filters = {}) {
  const res = await fetch(`${API_URL}/ledger/entries?limit=1000`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to fetch expenses");
  let list = (data.entries || []).filter((e) => e.kind === "expense").map(toLegacyExpense);
  if (filters.category) list = list.filter((e) => e.category === filters.category);
  if (filters.start) list = list.filter((e) => (e.fx_date || e.date) >= filters.start);
  if (filters.end) list = list.filter((e) => (e.fx_date || e.date) <= filters.end);
  return list;
}

export async function updateExpense(token, id, expense) {
  const res = await fetch(`${API_URL}/ledger/entries/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      amount: expense.amount,
      merchant: expense.merchant,
      date: expense.date,
      category: expense.category,
      currency: expense.currency,
      from_account_id: expense.from_account_id || null,
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to update expense");
  return toLegacyExpense({ ...data, from: expense.from_name, from_type: expense.from_type });
}

export async function deleteExpense(token, id) {
  const res = await fetch(`${API_URL}/ledger/entries/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to delete expense");
  return data;
}

export async function updateMe(token, payload) {
  const res = await fetch(`${API_URL}/users/me`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to update profile");
  return data;
}

export async function getCashflow(token) {
  const res = await fetch(`${API_URL}/ledger/cashflow`, { headers: { Authorization: `Bearer ${token}` } });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to fetch cash flow");
  return data;
}

export async function addLedgerIncome(token, payload) {
  const res = await fetch(`${API_URL}/ledger/income`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to add income");
  return data;
}

export async function getCategories(token) {
  const res = await fetch(`${API_URL}/categories`, { headers: { Authorization: `Bearer ${token}` } });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to fetch categories");
  return data;
}

export async function updateCategories(token, updates) {
  const res = await fetch(`${API_URL}/categories`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ updates }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to update categories");
  return data;
}
export async function getGoals(token) {
  const res = await fetch(`${API_URL}/goals`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to load goals");
  return data;
}

export async function savingsDeposit(token, payload) {
  const res = await fetch(`${API_URL}/ledger/savings/deposit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to add to savings");
  return data;
}

export async function savingsWithdraw(token, payload) {
  const res = await fetch(`${API_URL}/ledger/savings/withdraw`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to withdraw");
  return data;
}

export async function createGoalConfig(token, payload) {
  const res = await fetch(`${API_URL}/goals`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to create goal");
  return data;
}

export async function updateGoalConfig(token, id, payload) {
  const res = await fetch(`${API_URL}/goals/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to update goal");
  return data;
}

export async function deleteGoalConfig(token, id) {
  const res = await fetch(`${API_URL}/goals/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to delete goal");
  return data;
}

export async function getReconciliation(token) {
  const res = await fetch(`${API_URL}/ledger/reconciliation`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to load reconciliation");
  return data;
}

export async function setWalletLink(token, id, walletLinked) {
  const res = await fetch(`${API_URL}/ledger/entries/${id}/wallet-link`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ wallet_linked: walletLinked }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to update wallet link");
  return data;
}
export async function getAccounts(token) {
  const res = await fetch(`${API_URL}/accounts`, { headers: { Authorization: `Bearer ${token}` } });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to fetch accounts");
  return data; // { accounts:[{type,name,balance,...}], net_worth, currency }
}

export async function getEntries(token) {
  const res = await fetch(`${API_URL}/ledger/entries?limit=1000`, { headers: { Authorization: `Bearer ${token}` } });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to fetch entries");
  return data.entries || [];
}

export async function deleteEntry(token, id) {
  return deleteExpense(token, id); // generic /ledger/entries/{id} DELETE
}

export async function reorderGoals(token, order) {
  const res = await fetch(`${API_URL}/goals/reorder`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ order }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to reorder goals");
  return data; // returns the fresh goals_view
}

export async function configureEmergency(token, payload) {
  const res = await fetch(`${API_URL}/goals/emergency`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to update emergency fund");
  return data; // fresh goals_view
}