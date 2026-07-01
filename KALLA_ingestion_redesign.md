# KALLA — Ingestion Redesign: Design Lock (for confirmation)

*Draft for gate-by-gate confirmation. Companion to `KALLA_state_and_plan.md` and `KALLA_AI_pipeline_upgrade.md`. Nothing here is implemented yet; the open decisions in §7 must be resolved before any code.*

---

## 0. Thesis

This is **not three scanners** (bank statement, PayNow screenshot, recurring). It is **one source-agnostic ingestion pipeline** with an idempotent dedup core, onto which each source plugs as a thin adapter. The level-up signal is the pipeline + dedup over an event-sourced ledger — not any individual parser. It extends the ports-and-adapters seam already proven for FX/OCR.

The thesis stays "a model, not a record." Ingestion is where it gets tested: bulk, overlapping, third-party-controlled data must land in the immutable log **exactly once** and **without ever letting an attacker move a number.**

---

## 1. The pipeline (shared path)

Every source is an `IngestionAdapter` — a port, parallel to `FXProvider`/`OCRProvider` — implementing `parse(raw) -> list[CandidateTxn]`. `CandidateTxn` is a normalized DTO: `occurred_at, amount, currency, direction(in|out), counterparty_raw, source_ref, source_type, confidence, raw_excerpt`.

The adapter is the only source-specific code. Everything after is shared:

1. **parse** — adapter-specific (CSV row → DTO, OCR → DTO, etc.)
2. **normalize** — currency, date, sign/direction, counterparty cleanup; amounts parsed by **deterministic code, never the LLM** (Property A)
3. **dedup** — compute idempotency key; mark exact dupes, flag near-dupes (§2)
4. **enrich** — categorize + merchant resolution via the **boxed** LLM layer (Properties A–C)
5. **stage** — write to a **separate staging table** as pending candidates (Property D); the immutable ledger is *not* touched yet
6. **review** — human confirms / edits / rejects in the UI
7. **post** — confirmed candidates → existing `post_entry` → immutable ledger, tagged with `batch_id` + source provenance

Adapters stay thin; the value is concentrated in dedup (§2) and the review gate (Property D). This is the part nobody copies from a tutorial.

---

## 2. The dedup / idempotency core (the correctness heart)

The moment ingestion goes bulk + overlapping (re-upload a statement that overlaps last month; scan a PayNow transfer already in the ledger; the same txn arriving via *two* sources), it must not double-count. Event sourcing makes the question clean: *is this key already in the append-only log?*

**Two-key strategy:**

- **Source-native ID** when the source provides one — PayNow transaction ID, bank-statement reference number. Strongest; exact; per-source.
- **Content hash** fallback / cross-source key — `hash(normalized_date, amount_rounded, currency, direction, counterparty_hash)`. Source-native IDs don't collide across sources, so the content hash is what catches the *same* transaction arriving via PayNow screenshot **and** bank statement. Keyed on the *native* `(amount, currency)` rather than `amount_base`: a single real transaction has one native currency, so cross-source copies share it, and this keeps the dedup key free of any FX dependency or rounding drift.

**Hash hygiene (anti-manipulation).** The key is anchored on fields an attacker does **not** control — date, amount, direction — plus the *salted* `counterparty_hash` (Property J2), never the raw memo/reference free text. Attacker-controlled descriptors are excluded from the key entirely, so a crafted descriptor cannot force a collision (suppressing a real entry) or a non-collision (double-counting).

**Resolution policy (v1, deliberately conservative):**

- Exact source-native match → **auto-skip** (no-op append), surfaced in review as "already imported." Auto-skip fires *only* on a source-native ID, which the counterparty does not control.
- Content-hash match across sources → **flag for human review**, never auto-merge. Worst case of any residual hash manipulation is a spurious review flag, never a silent suppression. Fuzzy cross-source matching (spelling variants, timing windows) is genuinely hard; v1 flags, it does not auto-resolve. Honest scope > silent wrong merges.

**Statement reconciliation as a correctness check:** bank statements carry a running balance. Imported deltas can be verified against the statement's balance column to catch a missed or doubled line — reuses the existing reconciliation concept and turns dedup into something *provable*, not asserted.

This is the interview-gold problem: idempotent bulk ingestion over an immutable log, with a reconciliation invariant.

---

## 3. Locked security properties

Two distinct threat models. New sources are what make both real: statement descriptors, PayNow references, and email bodies are **third-party-controlled text**, not the user's own.

### Threat model 1 — prompt injection (parsed fields → LLM)

Solved by architecture that caps blast radius, **not** by an injection detector (detectors are bypassable and lower-value).

**Property A — Deterministic money math invariant.** The LLM never produces a number that gets stored. Amounts, balances, dedup keys, allocation are all computed in Python. A successful injection can yield a *wrong label*, never a wrong ledger entry. The statement parser must extract amounts deterministically; it may not delegate amount-parsing to the model.

**Property B — Closed-vocabulary / schema-constrained outputs + field sanitization.** Category output is validated against the `CATEGORIES` allowlist (already done in `suggest_category`) → worst case `Other`. The current gap is the **free-text `merchant`** from `extract_fields`, which is stored and later re-fed into the insights/ask JSON (second-order injection). Lock: sanitize `merchant` at the storage boundary — hard length cap, strip newlines/control chars and delimiter sequences, reject prose-shaped values. This breaks the second-order chain.

**Property C — Delimit and label untrusted input.** In categorize/extract, fence the OCR/descriptor text and instruct the model it is *data to classify, never instructions to follow*. Combined with A+B, not relied on alone.

**Property D — Human-review queue as backstop.** Bulk imports land as **pending candidates in a separate staging table**, never auto-posted. A mislabel from injection is caught by a human before it reaches the ledger. `A` + `D` together = blast radius is "user sees a weird suggested category on a pending row and fixes it." The staging table also keeps the immutable ledger pure — pending candidates are *proposals*, not ledger truth, so they must not live in `LedgerEntry`.

### Threat model 2 — PII handling (the data itself)

Statements carry account numbers, names, full financial history. Different problem: protect at rest, in transit, in logs.

**Property E — Storage minimization.** Don't retain the raw statement/OCR blob long-term. `LedgerEntry.raw_ocr_text` is fine for one receipt, a liability for a full statement. Keep parsed lines; purge the source artifact after confirmation (retention window in §7).

**Property F — Redact before the LLM.** Only `merchant descriptor + amount + date` is needed for categorization. A regex pre-pass masks long digit runs (account/card numbers) before any AI call. Account numbers are noise to the model and PII you shouldn't ship.

**Property G — In-house enrichment first.** No external enrichment (Ntropy/Context.dev/etc.) in v1 — calling out ships a user's whole financial history to a third party (a real consent step) and is a weaker portfolio story than building detection in-house. If ever added, send only the minimal descriptor string, never amounts/balances/account numbers.

**Property H — Logging hygiene.** Structured `extra={}` context logs metadata only — counts, lengths, error types — never statement text, merchant PII, or identity-linked amounts. Fix the existing leak in `ocr.py` (`extra={"response": str(data)[:300]}` can log OCR content).

**Property I — Deletion + provenance.** `batch_id` already groups entries from one import — that's the cascade-delete handle. "Delete this statement import" → remove all entries with that `batch_id` + purge the artifact. A working delete path + a one-line retention policy is a strong privacy signal.

**Unifying frame:** Model 1 = *the LLM can be lied to, so never let it decide anything that matters.* Model 2 = *the data is radioactive, so minimize, redact, never log or ship it.* Both are design decisions, not features — which is why they belong in this lock.

### Threat model 3 — abuse of the data itself (Properties J–M)

Models 1–2 cover injection and at-rest/logging. This third group covers *misuse*: surveilling third parties, exfiltrating others' data, weaponizing the pipeline, and the breach blast-radius. The tight solution is one spine plus three small bolt-ons — five of six abuse vectors collapse into a single decision: **hold as little as possible, for as short as possible, reachable only by its owner.**

**Property J — Minimization spine (the load-bearing decision).** Two storage "nevers":

- **J1 — Raw artifacts never durable.** The uploaded PDF/CSV/screenshot is parsed *in memory*; only extracted candidate fields are written to staging. Source bytes die with the request (or a short signed-URL TTL if a re-review window is needed, default ≤ 24h). There is no bucket of statements to exfiltrate and no PII silently retained in backups past the retention policy.
- **J2 — Counterparty identity never persisted raw.** A PayNow screenshot exposes the *other* party's name and an NRIC/phone-linked identifier — a third party who never consented. Persist only: a **user-supplied label**, a **salted one-way `counterparty_hash`** for dedup/matching, and a **masked display** fallback (`transfer ••• 8821`). The raw name and any NRIC/phone-linked identifier are dropped at parse time. The third party's identity is simply not in the database to leak, subpoena, or stare at.

J alone guts four vectors — PayNow counterparty leak, breach blast-radius, re-identification, and most PDPA/NRIC exposure — because a breach now yields minimized, owner-scoped, mostly-self data instead of a social graph with phone numbers.

**Property K — One ownership primitive, applied uniformly.** Not ad-hoc `if row.user_id == me` per endpoint (exactly how the original mutation gap arose). A single `get_owned(model, id, user)` accessor that *structurally cannot* return another user's row, used for every `ImportCandidate` / `ImportBatch` read and mutation. Artifacts (if any transient ones exist) are reachable only via **signed, expiring URLs** — never predictable paths. The staging table is the system's highest-value target (raw, un-purged, pending PII), so this scoping is non-negotiable on the new surface.

**Property L — Batch cap + per-user import rate limit.** One control kills two abuses: *denial-of-wallet* (a malicious user uploads a 100k-line CSV or a flood of images and runs up the OpenAI/Vision bill) and DB flooding. Default: per-file line cap and a per-user imports-per-hour limit, both refused loudly (reusing the fail-loud + structured-logging pattern from Phase B).

**Property M — Upload attestation.** A single gate at upload ("this is my account / I am authorized to process this") records consent for PDPA hygiene. Note: the *technical* harm-reduction is already done by J; M is the consent record, not the control.

**What closes for free** (no new property needed): *dedup manipulation* is contained by §2 hash hygiene + the source-native-only auto-skip; *prompt injection* is contained by Properties A–D.

**What is deliberately cut** (tight means cutting): app-layer field encryption (managed Postgres at-rest + minimization is proportionate — no encryption-theater), external enrichment (already out; itself an exfil vector), a full consent-management system (one attestation gate suffices), and the seductive "store the counterparty's name for convenience" — that convenience *is* the liability.

**Posture (documented, not engineered) for this scale.** For a portfolio with a handful of real users — not a regulated fintech — J–M are all built (each is cheap and genuinely exploitable now). The residual is *documented* as a stated posture: operator-access discipline (the operator can technically see all data; minimization + "we don't retain raw artifacts" is the control, not a promise), backup retention alignment with the purge policy, and an explicit PDPA stance. Reasoning about operator risk and choosing minimization over encryption-theater is itself the portfolio signal.

---

## 4. Data-model deltas (design level, no SQL yet)

- **`ImportCandidate` (new staging table)** — pending pre-confirmation. Fields: `id, user_id, batch_id, source_type, source_ref, idempotency_key, parsed fields (date/amount/currency/direction/category), counterparty_label, counterparty_hash, counterparty_masked, confidence, status(pending|confirmed|rejected|duplicate)`. **No raw name, no NRIC/phone-linked identifier, no raw artifact** (Properties J1/J2). Keeps the ledger immutable; candidates are proposals.
- **`ImportBatch` (new)** — one import event: `id, user_id, source_type, imported_at, status, counts, attested(bool)`. No durable `artifact_ref` (J1); any transient artifact is a signed expiring URL only. Extends the existing `batch_id` notion into a first-class record.
- **`idempotency_key` on `LedgerEntry`** — indexed, scoped per user, set at post time. (Open decision §7: column-on-ledger vs separate dedup table.)
- **Provenance on posted entries** — `source_type`, `imported_at` (reuses `batch_id`).

---

## 5. Source adapters (prioritized)

1. **CSV / bank statement (file)** — the backbone; every SG bank (DBS/OCBC/UOB) exports CSV. Dedup matters most here. **Build first.** PDF statement parsing (pdfplumber/Camelot, or the existing AI-extract layer) is a stretch on top, not v1-critical.
2. **PayNow screenshot (OCR)** — reuses Google Vision; source-native transaction ID is a clean idempotency key; **proves the abstraction generalizes beyond files.** Build second.
3. **Recurring subscriptions** — *not an adapter.* Pure derivation over the now-richer ledger: cluster by normalized merchant + near-constant amount + regular cadence, surface candidates. No external API. Falls out once 1–2 are in.
4. **Email receipts (Gmail)** — large real-world source (Grab, Shopee, airlines). Deferred.
5. **SMS / bank transaction alerts** — near-real-time capture. Deferred.

The SG API reality (confirmed): Plaid has no SG retail coverage; SGFinDex is the real infra but gated to regulated financial-planning apps (OAuth2 + Singpass + partner onboarding). So file/OCR/derivation in-house is both the only realistic path **and** the stronger portfolio signal.

---

## 6. Sequencing & scope discipline

The "build one feature, don't half-build three" rule applies *inside* this redesign:

1. Build the **pipeline + dedup core + review queue + security Properties A–I once.**
2. **CSV/statement adapter** end-to-end (parse → dedup → review → post).
3. **PayNow adapter** — proves generalization.
4. **Recurring detection** as a derivation.
5. **Defer** email/SMS, PDF statements, external enrichment.

The pipeline *is* the feature; adapters are proofs that the abstraction holds. Recurring detection is a near-free dividend of a richer ledger.

---

## 7. Locked decisions (gate resolved)

All ten confirmed. These are now binding for implementation.

1. **Idempotency storage** — ✅ `idempotency_key` as an indexed column on `LedgerEntry`. Dedup is "key exists in the log."
2. **Cross-source duplicates** — ✅ exact source-native ID → auto-skip; content-hash match → flag for human review. No silent merges.
3. **Staging** — ✅ separate `ImportCandidate` table. Pending candidates are proposals, never ledger truth; preserves the immutable-ledger invariant.
4. **Raw-artifact retention** — ✅ purge on resolution (subsumed by #9: artifacts are never durable to begin with).
5. **First adapter** — ✅ CSV / bank statement first. PayNow second.
6. **Enrichment** — ✅ in-house only for v1. No external enrichment.
7. **PDF statements** — ✅ deferred behind CSV.
8. **Counterparty handling** — ✅ drop raw name + NRIC/phone-linked identifier at parse; persist only label + salted hash + masked display (Property J2).
9. **Raw-artifact lifetime** — ✅ die-with-request; no durable storage. Add a signed-URL TTL window only if review UX later demands it.
10. **Batch cap + rate limit** — ✅ per-file line cap + per-user imports/hour (Property L); exact numbers set at implementation.

**Implementation order (gate-by-gate, validate at each step):**
data model (`ImportCandidate` / `ImportBatch` / `idempotency_key` + `get_owned` primitive) → ingestion pipeline → dedup core → CSV adapter → review UI → PayNow adapter → recurring detection.