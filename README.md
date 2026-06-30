# KALLA

**A personal-finance and receipt-scanning app built on an event-sourced, double-entry ledger.**

[![CI](https://github.com/R3X06/receipt-scanner/actions/workflows/ci.yml/badge.svg)](https://github.com/R3X06/receipt-scanner/actions/workflows/ci.yml)

KALLA tracks spending, savings, and goals on top of an immutable accounting ledger — every balance is *derived* from a log of events, never stored and mutated. Scan a receipt, log income, set savings goals, and the system computes balances, cash-flow, an emergency-fund target, and a goal-by-goal savings allocation from first principles.

**Live demo:** https://receipt-scanner-r3-x.vercel.app — sign in with `demo@demo.com` / `demo1234`

<!-- TODO: add 2–3 screenshots (dashboard, goals/allocation view, receipt scan) and/or a short demo GIF here -->
<!-- ![Dashboard](docs/dashboard.png) -->

---

## Why it's built this way (the interesting part)

Most personal-finance apps store a `balance` column and mutate it on every transaction. KALLA deliberately doesn't. The design choices below are the point of the project:

- **Event-sourced ledger.** The single source of truth is an append-only `LedgerEntry` log. Balances, net worth, cash-flow, and goal allocations are all *recomputed* from that log on read. Nothing is stored that could drift out of sync with the events that produced it.
- **Double-entry bookkeeping as the domain model.** Every entry has a `from` and `to` account; `NULL` on a side means "the World" (income if `from` is null, an expense if `to` is null). Money is conserved by construction.
- **A two-pass savings-allocation engine.** Goals are *derived claims* over the savings balance, not accounts that hold money. Pass 1 funds each goal's reserve senior-first (the emergency fund is always most senior); pass 2 splits the remainder by a chosen strategy — **waterfall**, **proportional** (deadline-weighted), or **even** — capping each goal at its target and re-spreading any overflow.
- **A derived emergency fund.** Its target isn't typed in; it's computed as `coverage_months × average essential monthly spend`, so it tracks real spending automatically.
- **Orthogonal flags, not schema forks.** `wallet_linked` and `inferred` change how an entry is *interpreted* during derivation (e.g. an expense paid from untracked money, or a declared opening balance) without multiplying entry types.
- **Temporal modelling.** `date` (the calendar day, for FX and reporting) is separate from `occurred_at` (the precise event time that orders the running wallet), so back-dated entries reconcile correctly.
- **Ports & adapters.** FX and OCR sit behind provider interfaces with a swappable registry, so the external services can be replaced — and mocked in tests — without touching the core.

There are deeper write-ups in [`KALLA_AI_pipeline_upgrade.md`](KALLA_AI_pipeline_upgrade.md) and `KALLA_state_and_plan.md`.

---

## Architecture

```
React + Vite (Vercel)
        │  HTTPS / JWT (Bearer)
        ▼
FastAPI (Railway)
 ├── main.py        transport / endpoints
 ├── auth.py        Argon2id + JWT
 ├── ledger.py      the engine: derivation + two-pass allocation (pure functions)
 ├── providers.py   FX / OCR ports + swappable registry
 ├── fx.py          currency conversion (Frankfurter)
 ├── ocr.py         receipt OCR (Google Vision) + parsing
 ├── ai.py          spending insights (OpenAI)
 └── models.py      SQLAlchemy schema (the immutable LedgerEntry log)
        │
        ▼
PostgreSQL (prod) · SQLite (local)
```

The core engine (`ledger.py`) is intentionally **functional** — derivation over an immutable log reads most naturally as pure functions, which is also why it's so thoroughly testable. OOP is concentrated where it fits: the SQLAlchemy/Pydantic data layer.

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI, SQLAlchemy, Pydantic v2 |
| Database | PostgreSQL (prod), SQLite (local) |
| Frontend | React, Vite, Tailwind v4, shadcn/ui |
| Auth | Argon2id (passlib + argon2-cffi), JWT |
| External | Google Vision (OCR), OpenAI (insights), Frankfurter (FX) |
| Quality | pytest, ruff, GitHub Actions CI |
| Hosting | Railway (API), Vercel (web) |

---

## Testing & quality

- **170 automated tests** covering the correctness-critical core: the allocation engine (including a randomized **conservation** property — money is never created or destroyed by the split), balance/cash-flow/reconciliation derivation, the provider seam, and endpoint-level security.
- **CI on every push and PR** runs `ruff` + `pytest` (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).
- **Security:** auth follows the OWASP baseline — Argon2id hashing with transparent rehash-on-login, password policy at signup, a JWT secret that hard-fails in production if unset, and identity keyed on an immutable user id. Cross-tenant writes are rejected.
- **Fail-closed external calls:** a currency conversion that can't reach a rate is refused (logged, `503`) rather than silently storing a wrong amount.

Run the suite:

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

---

## Running locally

### Backend (FastAPI)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Environment variables (a `.env` in `backend/` works via python-dotenv):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres URL in prod; defaults to local SQLite if unset |
| `JWT_SECRET` | JWT signing key — **required in production** (the app refuses to start otherwise) |
| `ENVIRONMENT` | `production` enables strict secret checks + JSON logs; defaults to `development` |
| `LOG_LEVEL` | Logging level (default `INFO`) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins (default `http://localhost:5173`) |
| `GOOGLE_VISION_API_KEY` | Receipt OCR |
| `OPENAI_API_KEY` | AI spending insights |

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` to the backend URL (defaults to `http://localhost:8000`).

---

## Project structure

```
receipt-scanner/
├── backend/        FastAPI app, ledger engine, tests
│   ├── tests/      pytest suite (170 tests)
│   └── ...
├── frontend/       React + Vite client
└── .github/workflows/ci.yml
```

---

## Status

Active portfolio project. Backend is feature-complete and tested; current work is on packaging (mobile polish, demo) and a scenario-simulation feature that runs the allocation engine over hypothetical inputs ("if I cut dining 20%, when does the emergency fund fill?").
