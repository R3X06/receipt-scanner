import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { updateMe, getCategories, updateCategories, resendVerification } from "./api";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

const OCCUPATIONS = [
  { value: "none", label: "Not set" },
  { value: "full_time", label: "Full-time work" },
  { value: "part_time", label: "Part-time work" },
  { value: "student", label: "Student" },
];

const AVATARS = ["🦊", "🐼", "🐱", "🦉", "🐧", "🦋", "🌿", "⭐", "🔥", "🍜"];

function ToggleRow({ label, hint, checked, onChange }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <p className="text-sm">{label}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        aria-pressed={checked}
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors ${
          checked ? "border-primary/40 bg-primary/80" : "border-white/15 bg-white/[0.06]"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full transition-all ${
            checked ? "translate-x-6 bg-white" : "translate-x-1 bg-white/40"
          }`}
        />
      </button>
    </div>
  );
}

function EmailVerificationStatus({ token, verified }) {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function resend() {
    setSending(true);
    setError("");
    try {
      await resendVerification(token);
      setSent(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  if (verified) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
        <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />
        <p className="text-sm">Email verified</p>
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
          <p className="text-sm text-amber-200">Email not verified</p>
        </div>
        <Button size="sm" variant="outline" onClick={resend} disabled={sending || sent}
          className="shrink-0 border-white/15 bg-transparent hover:bg-white/5">
          {sent ? "Sent ✓" : sending ? "Sending…" : "Resend email"}
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

function CategoryTags({ token }) {
  const [cats, setCats] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getCategories(token).then((d) => setCats(d.categories || [])).catch(() => {});
  }, [token]);

  const setKind = (name, kind) =>
    setCats((cs) => cs.map((c) => (c.name === name ? { ...c, kind } : c)));

  async function save() {
    setSaving(true);
    setSaved(false);
    try {
      await updateCategories(token, cats.map((c) => ({ name: c.name, kind: c.kind })));
      setSaved(true);
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  const opts = [["essential", "Essential"], ["discretionary", "Wants"], [null, "—"]];

  return (
    <div className="space-y-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <p className="text-sm font-medium">Category types</p>
      <p className="text-xs text-muted-foreground">Essentials set your emergency-fund coverage (months you could cover if income stopped).</p>
      {cats.map((c) => (
        <div key={c.name} className="flex items-center justify-between gap-2">
          <span className="truncate text-sm">{c.name}</span>
          <div className="flex shrink-0 gap-0.5 rounded-full border border-white/10 p-0.5">
            {opts.map(([val, label]) => (
              <button key={label} type="button" onClick={() => setKind(c.name, val)}
                className={`rounded-full px-2 py-0.5 text-xs ${c.kind === val ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                {label}
              </button>
            ))}
          </div>
        </div>
      ))}
      <Button size="sm" onClick={save} disabled={saving} className="w-full">
        {saving ? "Saving…" : saved ? "Saved ✓" : "Save category types"}
      </Button>
    </div>
  );
}

export default function Settings({ onClose }) {
  const { token, user, setUser } = useAuth();

  const [form, setForm] = useState({
    display_name: user?.display_name || "",
    avatar: user?.avatar || "",
    primary_currency: user?.primary_currency || "SGD",
    monthly_budget: user?.monthly_budget != null ? String(user.monthly_budget) : "",
    occupation: user?.occupation || "none",
    goals: user?.goals || "",
    feature_pay_yourself_first: user?.feature_pay_yourself_first ?? true,
    feature_pace_tracking: user?.feature_pace_tracking ?? true,
    pyf_percent: user?.pyf_percent != null ? String(user.pyf_percent) : "",
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
        goals: form.goals,
        feature_pay_yourself_first: form.feature_pay_yourself_first,
        feature_pace_tracking: form.feature_pace_tracking,
        pyf_percent: form.pyf_percent === "" ? null : parseFloat(form.pyf_percent),
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
    <Card className={`${GLASS} glass-scroll max-h-[85vh] overflow-y-auto rounded-2xl`}>
      <CardContent className="space-y-4">
        <div>
          <h2 className="text-base font-medium">Settings</h2>
          <p className="text-sm text-muted-foreground">Your profile and how KALLA works for you.</p>
        </div>

        <EmailVerificationStatus token={token} verified={user?.email_verified} />

        <div className="space-y-2">
          <Label>Display name</Label>
          <Input value={form.display_name} onChange={(e) => setField("display_name", e.target.value)} placeholder={emailPrefix || "Your name"} />
        </div>

        <div className="space-y-2">
          <Label>Avatar</Label>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setField("avatar", "")}
              className={`flex h-10 w-10 items-center justify-center rounded-full border text-sm font-semibold transition-colors ${form.avatar === "" ? "border-primary bg-primary/10 text-primary" : "border-white/15 bg-white/[0.04] text-muted-foreground hover:text-foreground"}`}
              aria-label="Use initials">Aa</button>
            {AVATARS.map((emoji) => (
              <button key={emoji} type="button" onClick={() => setField("avatar", emoji)}
                className={`flex h-10 w-10 items-center justify-center rounded-full border text-lg transition-colors ${form.avatar === emoji ? "border-primary bg-primary/10" : "border-white/15 bg-white/[0.04] hover:bg-white/[0.08]"}`}>
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
              <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Monthly budget</Label>
            <Input type="number" step="0.01" min="0" placeholder="e.g. 1500" value={form.monthly_budget} onChange={(e) => setField("monthly_budget", e.target.value)} />
          </div>
        </div>

        <div className="space-y-2">
          <Label>Occupation</Label>
          <Select value={form.occupation} onValueChange={(v) => setField("occupation", v)}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>{OCCUPATIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">Monthly income is calculated automatically from your recorded income — no need to enter it.</p>
        </div>

        <div className="space-y-2">
          <Label>Goals</Label>
          <textarea rows={3} placeholder="e.g. Save 20% of income, cut down on dining out" value={form.goals} onChange={(e) => setField("goals", e.target.value)}
            className="flex min-h-20 w-full rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary" />
          <p className="text-xs text-muted-foreground">Your goals are used to personalise your AI insights.</p>
        </div>

        <div className="space-y-1 rounded-xl border border-white/10 bg-white/[0.03] p-3">
          <p className="text-sm font-medium">Smart features</p>
          <ToggleRow label="Pay yourself first" hint="Suggest moving a set % into savings when income arrives" checked={form.feature_pay_yourself_first} onChange={(v) => setField("feature_pay_yourself_first", v)} />
          {form.feature_pay_yourself_first && (
            <div className="flex items-center gap-2 pb-1 pl-1">
              <Input type="number" min="0" max="100" step="1" placeholder="%" value={form.pyf_percent} onChange={(e) => setField("pyf_percent", e.target.value)} className="h-8 w-20" />
              <span className="text-xs text-muted-foreground">% of income to set aside</span>
            </div>
          )}
          <ToggleRow label="Goal pace tracking" hint="Show 'need X/mo' on goals with deadlines" checked={form.feature_pace_tracking} onChange={(v) => setField("feature_pace_tracking", v)} />
        </div>

        <CategoryTags token={token} />

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-2">
          <Button variant="outline" onClick={onClose} disabled={saving} className="border-white/15 bg-transparent hover:bg-white/5">Cancel</Button>
          <Button onClick={save} disabled={saving} className="flex-1 font-medium">{saving ? "Saving..." : "Save"}</Button>
        </div>
      </CardContent>
    </Card>
  );
}