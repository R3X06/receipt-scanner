# KALLA — State of the Project & Forward Plan

*Revision 2 — reflects auth hardening (Gate 1), cross-user reference validation (Gate 2), the full test + provider-abstraction + CI workstream as **complete**. Companion to `KALLA_AI_pipeline_upgrade.md`.*

---

## 0. The one-sentence thesis (unchanged)

**KALLA's edge is that it has a financial *model*, not just a *record*.** The level-up is the pivot from **descriptive** (what did I spend) to **predictive + prescriptive** (what's coming, and what should I do). Every decision is judged against that thesis.

---

## 1. What shipped this cycle (the headline change)

The project moved from "no tests on a correctness-critical finance ledger" to **a tested, provider-abstracted, CI-gated backend**. Concretely:

- **Gate 1 — industry-standard auth.** Argon2id hashing with transparent bcrypt->Argon2id rehash-on-login (OWASP baseline params); password bounds (min 8 / max 128) + `EmailStr` format validation at signup; environment-aware JWT secret that **hard-fails in production** if missing/default; JWT identity switched from email to immutable `user.id`.
- **Gate 2 — cross-user reference validation.** `update_entry` now rejects a `from_account_id` the caller doesn't own (400), closing the one residual referential-integrity hole. (Every other client-supplied id path was already guarded.)
- **Test suite — 167 cases, green.** Allocation engine (incl. randomized conservation), derivation layer (balances/cashflow/reconciliation/emergency), provider seam, and endpoint security (Gate 1 + Gate 2 invariants).
- **Provider abstraction.** `providers.py` — `FXProvider`/`OCRProvider` Protocols + default adapters + a swappable registry. The engine and endpoints route FX/OCR through it; tests inject network-free fakes. (LLM port deferred to the AI-pipeline rework.)
- **CI.** GitHub Actions runs `ruff` + `pytest` on push **and** PR; visible status checks per commit.

---

## 2. How the app is built (factual stack)

- **Backend:** FastAPI + SQLAlchemy. Postgres in prod (Railway), SQLite locally.
- **Frontend:** React + Vite on Vercel. Plain JavaScript (not TypeScript).
- **External services (now behind ports):** Frankfurter FX, Google Vision OCR, OpenAI insights.
- **Auth:** Argon2id + JWT (`sub` = `user.id`), env-gated secret.
- **Quality gates:** pytest (167), ruff, GitHub Actions CI.
- **Layering:** `models` (schema) / `ledger` (engine) / `providers` (ports) / `main` (transport) / `ai` / `fx` / `ocr` / `auth`.

---

## 3. How the app is designed (the architecture that matters)

The differentiating design choices, now each backed by tests:

| Concept | Where it lives | Test coverage |
|---|---|---|
| **Event sourcing** | `LedgerEntry` immutable log; balances never stored | balances/net-worth derivation tests |
| **Single source of truth / derived state** | `account_balances`, `cashflow`, allocations all recomputed | Tier 2 derivation suite |
| **Double-entry bookkeeping** | `from`/`to`, `NULL` = "the World" | income/expense/transfer cases |
| **Strategy pattern** | waterfall/proportional/even two-pass engine | allocation suite (all strategies) |
| **Orthogonal refining flags** | `wallet_linked`, `inferred` | unlinked-expense + inferred-income cases |
| **Temporal modeling** | `date` vs `occurred_at` | reconciliation backdating invariant |
| **Ports & adapters** | `providers.py` registry | provider swap/redirect tests |

**OOP framing (for interviews):** inheritance + abstraction via the ORM/DTO layers, composition via ORM relationships, duck-typed polymorphism at the AI boundary — but the core engine is deliberately functional, because event-sourced derivation reads more naturally as pure functions over a log. The functional core is *why* the engine was so cheaply and thoroughly testable.

**Honest scoping:** event-sourcing-*inspired* (immutable log + derived state), not full CQRS — no event versioning, snapshots, or projection-rebuild.

---

## 4. Present pieces (what works, now verified)

Unified double-entry ledger; two-pass allocation engine; derived emergency fund (singleton, derived target); goal pace tracking; FX conversion; wallet reconciliation; receipt OCR + manual entry + AI categorize/insights/ask; live deployment (Railway + Vercel); seeded demo account. **Plus the new quality spine:** Argon2id auth, cross-user reference validation, 167-test suite, provider ports, CI.

---

## 5. Missing pieces (the remaining gap to "excellent"), reordered

The three biggest prior gaps — **no tests, no CI, the security bug — are now closed.** What remains:

1. **Observability / silent failure modes.** The silent FX fallback that coerces stored amounts should fail loud (logged, refused). No structured logging or error tracking yet. *Now the top remaining backend gap.*
2. **JavaScript, not TypeScript.** A typed frontend is the "excellent"-bar differentiator; bigger lift, lower urgency than packaging.
3. **Scale story (articulated).** Folding the whole log per read won't scale; the mitigation (snapshot/cache keyed on state hash) is designed in the AI doc but unbuilt. A *known* gap reads as maturity — be able to articulate the tradeoff.
4. **Packaging (Phase 5).** Mobile responsiveness, README with screenshots, demo video. *Highest-leverage next step* — the repo is now worth showing.
5. **Lower-priority:** in-repo architecture doc/ADRs, rate limiting (deferred Gate 2 of the auth track), no real users yet.

---

## 6. How to enhance it (the level-up) — unchanged direction

- **Adaptability:** ports-and-adapters **done for FX/OCR**; strategy registry and pluggable ingestion remain as cheap, high-signal additions when wanted.
- **Optimization:** materialized projections / snapshotting (designed, unbuilt); composite DB indexes `(user_id, occurred_at)` / `(user_id, date)` (~15 min); SQL aggregation is a *known tradeoff*, not a recommendation at this scale.
- **Purpose (the differentiation):** **scenario simulation** — run the existing deterministic allocation engine over hypothetical inputs ("cut dining 20% -> when does the emergency fund fill?"). Impossible to copy without the engine, and now sitting on a *tested* engine so it can be built with confidence. Then forecasting, then the "provably honest AI" identity (the parked AI-pipeline doc).

---

## 7. Sequencing (revised — Phase B is done)

**Phase A — finish packaging (NOW)**
1. Phase 5 mobile responsiveness
2. README with screenshots
3. Demo video

**Phase B — cross the bar to "excellent" — COMPLETE**
- ~~Fix cross-user write bug~~ -> Gate 2 done
- ~~Ledger/allocation test suite + provider abstraction~~ -> done (167 tests, `providers.py`)
- ~~CI~~ -> done (ruff + pytest on push/PR)
- Remaining sub-item: **fail-loud on the FX path + basic logging** (small; fold into Phase A or a quick observability pass)

**Phase C — one level-up feature**
4. **Scenario simulation** — build exactly one, on the now-tested engine.

**Then:** the parked AI pipeline upgrade (its own doc).

> The discipline still holds: one well-built simulation feature on a tested, provider-abstracted, CI-gated codebase is an *excellent* project. Don't half-build three.

---

## 8. Resume / interview framing (strengthened by this cycle)

- Lead with the **event-sourced ledger + allocation engine**, now **"with a 167-case test suite proving the conservation and allocation invariants"** — correctness you can demonstrate, not assert.
- **"Hardened auth to OWASP baseline: Argon2id with transparent rehash-on-login, fail-closed JWT secrets, immutable-id identity."**
- **"Found and fixed a cross-tenant write vulnerability"** (Gate 2).
- **"Ports-and-adapters provider layer enabling network-free, mock-injected tests"** — design maturity + testability in one line.
- **"CI gating every push and PR with lint + tests."**
- **Scenario simulation over a deterministic allocation model** — the differentiator nobody else has (next to build).
- Methodology, stated defensibly: *"converged on a disciplined gate-by-gate incremental process under real constraints."*
- GPA mitigation (unchanged): OSS contributions to the stack, the ledger-design technical post, referrals + startups without hard GPA cutoffs, real users for traction.

---

## 9. Deferred / parked (conscious, not dropped)

- **Auth track, later:** rate limiting + breached-password check (Gate 2 of auth); password reset + email verification (needs a domain + transactional email provider, e.g. Resend); **TOTP MFA** (RFC 6238, no email infra needed — the cheap, high-signal flex if time allows). None are "next"; all are post-packaging differentiators.
- **AI insights pipeline upgrade:** full design in `KALLA_AI_pipeline_upgrade.md`. LLM provider port to be introduced *with* that rework, not before.
- **Deprecation cleanup (cosmetic):** `declarative_base()` import + `datetime.utcnow()` usages; two-line fix, or silence via `filterwarnings` in `pytest.ini`.

---

## 10. Open question to resolve next

Pick the next concrete move:
- (a) **Phase 5 packaging** — start with the README (architecture + screenshots + the tested-engine story), or mobile responsiveness, or the demo video; or
- (b) **the quick observability pass** — make the silent FX fallback fail loud + add basic structured logging (small, closes the top remaining backend gap); or
- (c) **scope scenario simulation** gate-by-gate — API shape + what it reuses from the allocation engine — to line up Phase C.
