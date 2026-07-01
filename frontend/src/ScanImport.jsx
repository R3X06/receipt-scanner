import { useState } from "react";
import { useAuth } from "./AuthContext";
import { scanImage, createImport } from "./api";
import { CATEGORIES, CURRENCIES } from "./constants";
import ImportReview from "./ImportReview";
import ReceiptUpload from "./ReceiptUpload";

import { Card, CardContent } from "@/components/ui/card";
import { Upload, Image as ImageIcon, FileText, Table2 } from "lucide-react";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

function detectType(file) {
  const name = (file.name || "").toLowerCase();
  const t = file.type || "";
  if (t === "text/csv" || name.endsWith(".csv")) return "csv";
  if (t === "application/pdf" || name.endsWith(".pdf")) return "pdf";
  if (t.startsWith("image/")) return "image";
  return "unknown";
}

export default function ScanImport({ onExpenseAdded, onDone }) {
  const { token } = useAuth();
  const [mode, setMode] = useState("pick"); // pick | loading | review | receipt
  const [error, setError] = useState("");
  const [batch, setBatch] = useState(null);
  const [receiptDraft, setReceiptDraft] = useState(null);
  const [attested, setAttested] = useState(false);
  const [inputKey, setInputKey] = useState(0);

  function reset() {
    setMode("pick");
    setBatch(null);
    setReceiptDraft(null);
  }

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    const kind = detectType(file);
    setInputKey((k) => k + 1); // allow re-selecting the same file

    if (kind === "unknown") {
      setError("Unsupported file. Upload an image, PDF, or CSV.");
      return;
    }
    if ((kind === "csv" || kind === "pdf") && !attested) {
      setError("Please confirm you're authorised to import this file first.");
      return;
    }

    setMode("loading");
    try {
      if (kind === "csv" || kind === "pdf") {
        const b = await createImport(token, file, kind, attested);
        setBatch(b);
        setMode("review");
      } else {
        const res = await scanImage(token, file, attested);
        if (res.kind === "paynow") {
          setBatch(res.batch);
          setMode("review");
        } else {
          setReceiptDraft({
            merchant: res.merchant === "Unknown" ? "" : res.merchant || "",
            amount: res.amount ? String(res.amount) : "",
            date: res.date || "",
            category: CATEGORIES.includes(res.category) ? res.category : "Other",
            currency: CURRENCIES.includes(res.currency) ? res.currency : "SGD",
            raw_ocr_text: res.raw_ocr_text || "",
            parsed_ok: res.parsed_ok,
          });
          setMode("receipt");
        }
      }
    } catch (err) {
      setError(err.message);
      setMode("pick");
    }
  }

  if (mode === "review" && batch) {
    return (
      <ImportReview
        batch={batch}
        onClose={onDone}
        onPosted={() => onExpenseAdded?.()}
      />
    );
  }

  if (mode === "receipt" && receiptDraft) {
    return (
      <ReceiptUpload
        initialDraft={receiptDraft}
        onExpenseAdded={(exp) => {
          onExpenseAdded?.(exp);
          onDone?.();
        }}
      />
    );
  }

  const loading = mode === "loading";

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-3">
        <div>
          <h2 className="text-base font-medium">Scan or import</h2>
          <p className="text-sm text-muted-foreground">
            A receipt or PayNow screenshot, a bank statement PDF, or a CSV export
          </p>
        </div>

        <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm">
          <input
            type="checkbox"
            checked={attested}
            onChange={(e) => setAttested(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-[#A855F7]"
          />
          <span className="text-muted-foreground">
            I'm authorised to import this data (required for statements &amp; transfers).
          </span>
        </label>

        <label
          className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-white/15 px-6 py-8 text-center text-sm text-muted-foreground transition-colors ${
            loading ? "cursor-default" : "cursor-pointer hover:border-primary/40 hover:bg-white/[0.02]"
          }`}
        >
          <Upload className="h-6 w-6 opacity-70" />
          {loading ? "Reading…" : "Click to upload — image, PDF, or CSV"}
          <input
            key={inputKey}
            type="file"
            accept="image/*,application/pdf,.pdf,.csv,text/csv"
            onChange={handleFile}
            className="hidden"
            disabled={loading}
          />
        </label>

        <div className="flex justify-center gap-5 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1"><ImageIcon className="h-3.5 w-3.5" /> Receipt / PayNow</span>
          <span className="inline-flex items-center gap-1"><FileText className="h-3.5 w-3.5" /> PDF statement</span>
          <span className="inline-flex items-center gap-1"><Table2 className="h-3.5 w-3.5" /> CSV</span>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
