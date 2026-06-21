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

export async function createExpense(token, expense) {
  const res = await fetch(`${API_URL}/expenses`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(expense),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to create expense");
  return data;
}

export async function getExpenses(token, filters = {}) {
  const params = new URLSearchParams();
  if (filters.start) params.append("start_date", filters.start);
  if (filters.end) params.append("end_date", filters.end);
  if (filters.category) params.append("category", filters.category);
  const qs = params.toString();

  const res = await fetch(`${API_URL}/expenses${qs ? `?${qs}` : ""}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to fetch expenses");
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

export async function updateExpense(token, id, expense) {
  const res = await fetch(`${API_URL}/expenses/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(expense),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to update expense");
  return data;
}

export async function deleteExpense(token, id) {
  const res = await fetch(`${API_URL}/expenses/${id}`, {
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

export async function getSavings(token) {
  const res = await fetch(`${API_URL}/savings`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to fetch savings");
  return data;
}

export async function addSaving(token, payload) {
  const res = await fetch(`${API_URL}/savings`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to add savings entry");
  return data;
}

export async function deleteSaving(token, id) {
  const res = await fetch(`${API_URL}/savings/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to delete savings entry");
  return data;
}