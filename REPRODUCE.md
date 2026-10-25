# Reproducing InterviewIQ

This document is the single source of truth for getting the project running
from a clean checkout and for rerunning the two empirical results the
project's core contribution (metamorphic knowledge testing, MKT) rests on.

## 1. Setup

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
```

Create `backend/.env` (not committed):

```
GEMINI_API_KEY=<your Gemini API key>
GEMINI_MODEL=gemini-3.5-flash-lite
```

Notes on these two values, both read by `app/core/config.py`:

- `GEMINI_API_KEY` is required. Without it, `llm_gateway._get_client()` raises
  `LLMUnavailable` on first use — the app itself still starts, but every
  LLM-backed feature (question generation, answer evaluation, MKT verification,
  final report) falls back to its degraded path (see `LIMITATIONS.md`).
- `GEMINI_MODEL` defaults to `gemini-3.5-flash` if unset, but that model's free
  tier has a hard **20 requests/day** cap, discovered empirically during Phase
  5's evaluation runs. `gemini-3.5-flash-lite` sits on a separate, more
  permissive quota and is what this project actually ran on — set it
  explicitly.

All other settings have working defaults and don't need to be set for local
development:

| variable | default | purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<repo>/backend/interviewiq.db` | swap for a Postgres URL in production |
| `JWT_SECRET` | `dev-only-change-me` | **must** be overridden outside local dev |
| `JWT_EXPIRY_MINUTES` | `10080` (7 days) | session token lifetime |
| `NLI_MODEL` | `cross-encoder/nli-deberta-v3-xsmall` | small CPU cross-encoder used by `LocalVerifier`'s fallback NLI check |

The SQLite database is created automatically on first run via
SQLAlchemy's `create_all()` — there is **no migration tool** in this project.
If you change any model in `app/modules/*/models.py`, the simplest path is to
delete `backend/interviewiq.db` and let it regenerate; this is a known,
accepted limitation of a capstone-scale project, not an oversight (see
`LIMITATIONS.md`).

Start the backend:

```bash
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend1
npm install
npm run dev       # dev server
npm run build     # production build, used for the regression check below
```

The frontend expects the backend at the URL configured in
`frontend1/src/services/*` (default: `http://localhost:8000`).

## 2. Running the test suite

```bash
cd backend
python -m pytest -q
```

At the time of writing this is **131 tests, all passing** (0 failures), covering
every module added across all 14 phases: auth/session, interview state machine
and resumability, MKT belief/selection/simulation, the BKT baseline comparison,
the verifier corpus, communication and emotion analysis, aptitude, coding/
whiteboard, and the evidence-trail API.

## 3. Reproducing the two key empirical results

Both commands below are run from `backend/` and both write their output to
files already checked into the repo (`app/modules/mkt/eval/results/` and
`app/modules/mkt/baselines/results/`) — rerunning them should reproduce
numbers close to (LLM calls are not bit-for-bit deterministic) what's reported
in those directories' `README.md` files.

### Phase 5 — verifier validation and closed-loop pipeline test

```bash
python -m app.modules.mkt.eval.run_verifier_eval --verifier local  --out results/local.json
python -m app.modules.mkt.eval.run_verifier_eval --verifier llm    --out results/llm.json --sleep 3
python -m app.modules.mkt.eval.run_closed_loop    --verifier local    --out results/closed_loop_local.json
python -m app.modules.mkt.eval.run_closed_loop    --verifier fallback --out results/closed_loop_fallback.json --sleep 3
```

`--sleep N` paces real Gemini calls at one call every N seconds; this matters
because of the daily-quota issue above. Calls are cached by prompt hash in the
`llm_calls` table, so an interrupted run can always be safely rerun without
re-spending quota on already-answered items.

Full write-up: `backend/app/modules/mkt/eval/results/README.md`.

### Phase 8 — BKT baseline comparison, calibration & EM

```bash
python -m app.modules.mkt.baselines.compare
```

This is fully offline (simulated candidates, no LLM calls), seeded (seed 0),
and deterministic. Full write-up:
`backend/app/modules/mkt/baselines/results/README.md`.

## 4. Confirming the frontend build

```bash
cd frontend1
npm run build
```

Expected: a clean `vite build` with one benign warning (the main JS chunk is
>500 kB, see `LIMITATIONS.md` — not a build failure).

## 5. Dependency sync check

`backend/requirements.txt` and `frontend1/package.json` were checked against
every import actually used across all 14 phases, including Phase 9b's
`@mediapipe/tasks-vision` (emotion detection) — both files are in sync with
what's installed and imported as of this phase.
