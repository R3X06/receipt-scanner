import { useState } from "react";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";
import { updateMe } from "./api";

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

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

const OCCUPATIONS = [
  { value: "none", label: "Not set" },
  { value: "full_time", label: "Full-time work" },
  { value: "part_time", label: "Part-time work" },
  { value: "student", label: "Student" },
];

const AVATARS = ["🦊", "🐼", "🐱", "🦉", "🐧", "🦋", "🌿", "⭐", "🔥", "🍜"];

export default function Settings({ onClose }) {
  const { token, user, setUser } = useAuth();

  const [form, setForm] = useState({
    display_name: user?.display_name || "",
    avatar: user?.avatar || "",
    primary_currency: user?.primary_currency || "SGD",
    monthly_budget: user?.monthly_budget != null ? String(user.monthly_budget) : "",
    occupation: user?.occupation || "none",
    monthly_income: user?.monthly_income != null ? String(user.monthly_income) : "",
    goals: user?.goals || "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    setSaving(true);
    setError("");
    try {
      const updated = await updateMe(token, {
        display_name: form.display_name.trim() || null,
        avatar: form.avatar || null,
        primary_currency: form.primary_currency,
        monthly_budget: form.monthly_budget === "" ? null : parseFloat(form.monthly_budget),
        occupation: form.occupation === "none" ? null : form.occupation,
        monthly_income: form.monthly_income === "" ? null : parseFloat(form.monthly_income),
        goals: form.goals,
      });
      setUser(updated);
      onClose?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const emailPrefix = (user?.email || "").split("@")[0];

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-4">
        <div>
          <h2 className="text-base font-medium">Settings</h2>
          <p className="text-sm text-muted-foreground">Your profile and how KALLA works for you.</p>
        </div>

        <div className="space-y-2">
          <Label>Display name</Label>
          <Input
            value={form.display_name}
            onChange={(e) => setField("display_name", e.target.value)}
            placeholder={emailPrefix || "Your name"}
          />
        </div>

        <div className="space-y-2">
          <Label>Avatar</Label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setField("avatar", "")}
              className={`flex h-10 w-10 items-center justify-center rounded-full border text-sm font-semibold transition-colors ${
                form.avatar === ""
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-white/15 bg-white/[0.04] text-muted-foreground hover:text-foreground"
              }`}
              aria-label="Use initials"
            >
              Aa
            </button>
            {AVATARS.map((emoji) => (
              <button
                key={emoji}
                type="button"
                onClick={() => setField("avatar", emoji)}
                className={`flex h-10 w-10 items-center justify-center rounded-full border text-lg transition-colors ${
                  form.avatar === emoji
                    ? "border-primary bg-primary/10"
                    : "border-white/15 bg-white/[0.04] hover:bg-white/[0.08]"
                }`}
              >
                {emoji}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label>Base currency</Label>
            <Select value={form.primary_currency} onValueChange={(v) => setField("primary_currency", v)}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Monthly budget</Label>
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="e.g. 1500"
              value={form.monthly_budget}
              onChange={(e) => setField("monthly_budget", e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label>Occupation</Label>
            <Select value={form.occupation} onValueChange={(v) => setField("occupation", v)}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {OCCUPATIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>
              Monthly income <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="Optional"
              value={form.monthly_income}
              onChange={(e) => setField("monthly_income", e.target.value)}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label>Goals</Label>
          <textarea
            rows={3}
            placeholder="e.g. Save 20% of income, cut down on dining out"
            value={form.goals}
            onChange={(e) => setField("goals", e.target.value)}
            className="flex min-h-20 w-full rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          />
          <p className="text-xs text-muted-foreground">Your goals are used to personalise your AI insights.</p>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={onClose}
            disabled={saving}
            className="border-white/15 bg-transparent hover:bg-white/5"
          >
            Cancel
          </Button>
          <Button onClick={save} disabled={saving} className="flex-1 font-medium">
            {saving ? "Saving..." : "Save"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}