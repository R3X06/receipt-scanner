import { useState } from "react";
import { useAuth } from "./AuthContext";
import {
  getImport,
  editCandidate,
  rejectCandidate,
  confirmImport,
  deleteImport,
} from "./api";
import { CATEGORIES } from "./constants";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  ArrowUpRight,
  ArrowDownLeft,
  X,
  Pencil,
  AlertTriangle,
  CheckCircle2,
  Copy,
} from "lucide-react";

const AMBER = "#F0B14B";
const SOURCE_LABEL = { csv: "Bank statement (CSV)", pdf: "Bank statement (PDF)", paynow: "PayNow transfer" };

function money(c) {
  const n = Number(c.amount || 0).toFixed(2);
  return `${c.direction === "out" ? "\u2212" : "+"}${n}${c.currency ? " " + c.currency : ""}`;
}

export default function ImportReview({ batch: initialBatch, onClose, onPosted }) {
  const { token } = useAuth();
  const [batch, setBatch] = useState(initialBatch);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [result, setResult] = useState(null);

  const cands = batch.candidates || [];
  const pending = cands.filter((c) => c.status === "pending");
  const duplicates = cands.filter((c) => c.status === "duplicate");

  async function refresh() {
    try {
      setBatch(await getImport(token, batch.id));
    } catch (e) {
      setError(e.message);
    }
  }

  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const onReject = (id) => run(async () => { await rejectCandidate(token, id); await refresh(); });
  const onCategory = (id, category) => run(async () => { await editCandidate(token, id, { category }); await refresh(); });
  const onConfirm = () => run(async () => {
    const res = await confirmImport(token, batch.id);
    setResult(res);
    onPosted?.();
  });
  const onDiscard = () => run(async () => { await deleteImport(token, batch.id); onClose?.(); });
  const saveEdit = (patch) => run(async () => { await editCandidate(token, editing.id, patch); setEditing(null); await refresh(); });

  // ---- result screen (after confirm) ----
  if (result) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-primary">
          <CheckCircle2 className="h-5 w-5" />
          <h2 className="text-base font-medium">Import posted</h2>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm space-y-1">
          <div>{result.posted} transaction{result.posted === 1 ? "" : "s"} added to your ledger.</div>
          {result.skipped_duplicate > 0 && (
            <div className="text-muted-foreground">{result.skipped_duplicate} skipped as duplicates.</div>
          )}
          {result.fx_failed > 0 && (
            <div style={{ color: AMBER }}>{result.fx_failed} left pending (exchange rate unavailable) — retry later.</div>
          )}
        </div>
        <Button onClick={onClose} className="w-full font-medium">Done</Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-base font-medium">Review import</h2>
        <p className="text-sm text-muted-foreground">
          {SOURCE_LABEL[batch.source_type] || batch.source_type} · {pending.length} to add
          {duplicates.length > 0 ? ` · ${duplicates.length} duplicate${duplicates.length === 1 ? "" : "s"}` : ""}
        </p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="max-h-[52vh] space-y-2 overflow-y-auto glass-scroll pr-1">
        {cands.map((c) => {
          const dup = c.status === "duplicate";
          const rejected = c.status === "rejected";
          const flagged = c.review_flag === "possible_duplicate";
          const fxFailed = c.review_flag === "fx_failed";
          return (
            <div
              key={c.id}
              className={`rounded-xl border border-white/10 bg-white/[0.03] p-3 ${
                dup || rejected ? "opacity-50" : ""
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {c.direction === "out" ? (
                      <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                    ) : (
                      <ArrowDownLeft className="h-4 w-4 shrink-0 text-primary" />
                    )}
                    <span className="truncate text-sm font-medium">
                      {c.counterparty_label || c.counterparty_masked || "—"}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {c.date || "no date"} · <span className="tabular-nums">{money(c)}</span>
                  </div>

                  {flagged && (
                    <div className="mt-1 inline-flex items-center gap-1 text-xs" style={{ color: AMBER }}>
                      <Copy className="h-3 w-3" /> Possible duplicate
                    </div>
                  )}
                  {fxFailed && (
                    <div className="mt-1 inline-flex items-center gap-1 text-xs" style={{ color: AMBER }}>
                      <AlertTriangle className="h-3 w-3" /> Rate unavailable
                    </div>
                  )}
                  {dup && <div className="mt-1 text-xs text-muted-foreground">Already imported — skipped</div>}
                  {rejected && <div className="mt-1 text-xs text-muted-foreground">Rejected</div>}
                </div>

                {!dup && !rejected && (
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-foreground"
                      onClick={() => setEditing(c)}
                      disabled={busy}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      onClick={() => onReject(c.id)}
                      disabled={busy}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>

              {!dup && !rejected && (
                <div className="mt-2">
                  <Select value={c.category || "Other"} onValueChange={(v) => onCategory(c.id, v)} disabled={busy}>
                    <SelectTrigger className="h-8 w-full text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map((cat) => (
                        <SelectItem key={cat} value={cat}>{cat}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          );
        })}
        {cands.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">Nothing to review.</p>
        )}
      </div>

      <div className="flex gap-2 pt-1">
        <Button
          variant="outline"
          onClick={onDiscard}
          disabled={busy}
          className="border-white/15 bg-transparent hover:bg-white/5"
        >
          Discard
        </Button>
        <Button onClick={onConfirm} disabled={busy || pending.length === 0} className="flex-1 font-medium">
          {busy ? "Working…" : `Add ${pending.length} to ledger`}
        </Button>
      </div>

      {editing && (
        <EditDialog
          candidate={editing}
          busy={busy}
          onCancel={() => setEditing(null)}
          onSave={saveEdit}
        />
      )}
    </div>
  );
}

function EditDialog({ candidate, busy, onCancel, onSave }) {
  const [f, setF] = useState({
    amount: String(candidate.amount ?? ""),
    date: candidate.date || "",
    direction: candidate.direction || "out",
    category: candidate.category || "Other",
    counterparty_label: candidate.counterparty_label || "",
  });
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  return (
    <Dialog open onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="border-white/10 bg-white/[0.04] backdrop-blur-xl">
        <DialogTitle>Edit transaction</DialogTitle>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Label</Label>
            <Input value={f.counterparty_label} onChange={(e) => set("counterparty_label", e.target.value)} placeholder="Name this transaction" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Amount</Label>
              <Input type="number" step="0.01" min="0" value={f.amount} onChange={(e) => set("amount", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Direction</Label>
              <Select value={f.direction} onValueChange={(v) => set("direction", v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="out">Money out</SelectItem>
                  <SelectItem value="in">Money in</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Date</Label>
              <Input value={f.date} onChange={(e) => set("date", e.target.value)} placeholder="YYYY-MM-DD" />
            </div>
            <div className="space-y-2">
              <Label>Category</Label>
              <Select value={f.category} onValueChange={(v) => set("category", v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((cat) => (<SelectItem key={cat} value={cat}>{cat}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <Button variant="outline" onClick={onCancel} disabled={busy} className="border-white/15 bg-transparent hover:bg-white/5">Cancel</Button>
            <Button
              onClick={() => onSave({
                amount: parseFloat(f.amount),
                date: f.date,
                direction: f.direction,
                category: f.category,
                counterparty_label: f.counterparty_label,
              })}
              disabled={busy}
              className="flex-1 font-medium"
            >
              Save
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
