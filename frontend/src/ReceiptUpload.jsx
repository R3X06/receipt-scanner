import { useState } from "react";
import { useAuth } from "./AuthContext";
import { CATEGORIES, CURRENCIES } from "./constants";
import { createExpense, extractFields } from "./api";

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
import { Upload, CheckCircle2, AlertTriangle } from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

export default function ReceiptUpload({ onExpenseAdded, initialDraft = null }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [inputKey, setInputKey] = useState(0);

  const [draft, setDraft] = useState(initialDraft);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  async function handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    setError("");
    setSaveError("");
    setDraft(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_URL}/ocr`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "OCR failed");

      let merchant = data.merchant === "Unknown" ? "" : data.merchant || "";
      let category = CATEGORIES.includes(data.category) ? data.category : "Other";

      try {
        const ex = await extractFields(token, { raw_text: data.raw_ocr_text });
        if (ex?.merchant) merchant = ex.merchant;
        if (ex?.category && CATEGORIES.includes(ex.category)) category = ex.category;
      } catch {
        // best-effort — keep the OCR fallbacks
      }

      setDraft({
        merchant,
        amount: data.amount ? String(data.amount) : "",
        date: data.date || "",
        category,
        currency: CURRENCIES.includes(data.currency) ? data.currency : "SGD",
        raw_ocr_text: data.raw_ocr_text || "",
        parsed_ok: data.parsed_ok,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setInputKey((prev) => prev + 1);
    }
  }

  function updateField(field, value) {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSave() {
    if (!draft) return;

    const amountNum = parseFloat(draft.amount);
    if (isNaN(amountNum) || amountNum <= 0) {
      setSaveError("Please enter a valid amount.");
      return;
    }
    if (!draft.merchant.trim()) {
      setSaveError("Please enter a merchant.");
      return;
    }

    setSaving(true);
    setSaveError("");
    try {
      const saved = await createExpense(token, {
        amount: amountNum,
        merchant: draft.merchant.trim(),
        date: draft.date,
        category: draft.category,
        currency: draft.currency,
        raw_ocr_text: draft.raw_ocr_text,
        parsed_ok: draft.parsed_ok,
      });
      onExpenseAdded(saved);
      setDraft(null);
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function handleDiscard() {
    setDraft(null);
    setSaveError("");
  }

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-3">
        <div>
          <h2 className="text-base font-medium">Scan a receipt</h2>
          <p className="text-sm text-muted-foreground">
            Take a photo or upload an image of your receipt
          </p>
        </div>

        {!draft && (
          <label
            className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-white/15 px-6 py-8 text-center text-sm text-muted-foreground transition-colors ${
              loading ? "cursor-default" : "cursor-pointer hover:border-primary/40 hover:bg-white/[0.02]"
            }`}
          >
            <Upload className="h-6 w-6 opacity-70" />
            {loading ? "Scanning..." : "Click to upload receipt"}
            <input
              key={inputKey}
              type="file"
              accept="image/*"
              onChange={handleUpload}
              className="hidden"
              disabled={loading}
            />
          </label>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {draft && (
          <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div
              className={`flex items-center gap-2 text-sm font-medium ${
                draft.parsed_ok ? "text-primary" : "text-[#F0B14B]"
              }`}
            >
              {draft.parsed_ok ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <AlertTriangle className="h-4 w-4" />
              )}
              {draft.parsed_ok
                ? "Receipt scanned — review and edit before saving"
                : "Couldn't read this clearly — please check every field"}
            </div>

            <div className="space-y-2">
              <Label>Merchant</Label>
              <Input
                value={draft.merchant}
                onChange={(e) => updateField("merchant", e.target.value)}
                placeholder="Merchant name"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Amount</Label>
                <Input
                  type="number"
                  value={draft.amount}
                  onChange={(e) => updateField("amount", e.target.value)}
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                />
              </div>
              <div className="space-y-2">
                <Label>Currency</Label>
                <Select value={draft.currency} onValueChange={(v) => updateField("currency", v)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Date</Label>
                <Input
                  type="text"
                  value={draft.date}
                  onChange={(e) => updateField("date", e.target.value)}
                  placeholder="As printed on receipt"
                />
              </div>
              <div className="space-y-2">
                <Label>Category</Label>
                <Select value={draft.category} onValueChange={(v) => updateField("category", v)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {draft.raw_ocr_text && (
              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground">Show scanned text</summary>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-md border border-white/10 bg-black/20 p-2 text-xs text-muted-foreground">
                  {draft.raw_ocr_text}
                </pre>
              </details>
            )}

            {saveError && <p className="text-sm text-destructive">{saveError}</p>}

            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={handleDiscard}
                disabled={saving}
                className="border-white/15 bg-transparent hover:bg-white/5"
              >
                Discard
              </Button>
              <Button onClick={handleSave} disabled={saving} className="flex-1 font-medium">
                {saving ? "Saving..." : "Save expense"}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}