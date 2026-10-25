# Known Limitations

Written deliberately, without softening — this project's own driving theme
has been reporting real findings, including unflattering ones, rather than
inflating claims. Everything below is either an already-quantified result
from an earlier phase or a specific finding from this phase's hardening pass.

## 1. The production fallback verifier is measurably worse than the LLM verifier

`service.py::get_mkt_deps()` defaults to
`FallbackVerifier(LLMVerifier(), LocalVerifier())` — `LocalVerifier` only
runs when the Gemini API is unavailable (rate-limited, network error, no key
configured). Phase 5's evaluation quantified exactly how much that
degradation costs (`backend/app/modules/mkt/eval/results/README.md`):

- Overall answer-class accuracy: **0.727** (Local) vs **1.000** (LLM) on a
  154-item hand-labelled corpus.
- The gap is concentrated in `correct`-answer recall (0.625 vs 1.000):
  `LocalVerifier` systematically under-recognises short or non-lexically-
  overlapping correct answers, because general-domain NLI labels most
  correct technical paraphrase as "neutral" rather than "entailment," so
  entailment detection falls to an embedding-similarity threshold that
  under-rewards terse phrasing.
- That gap propagates end to end: the closed-loop experiment shows the
  belief engine's robust-vs-memorised separation (mean robustness-index gap)
  collapses from **0.94** under `FallbackVerifier` to **0.14** under
  `LocalVerifier` alone.

**Practical implication:** if the Gemini API goes down mid-demo or
mid-deployment, MKT keeps functioning (0.409 overall state accuracy is well
above the 0.25 chance rate for 4-way classification) but noticeably worse at
telling robust understanding from memorisation — the system degrades
gracefully, it does not degrade invisibly.

## 2. Plain (non-MKT) LLM generation paths share the same retry ceiling

`llm_gateway._call_with_retry` retries any Gemini call 3 times with
exponential backoff (1s, 2s, 4s) before giving up, and every one of
`_default_generate_first_question`, `_default_evaluate_answer`, and
`_default_generate_report` in `interview/service.py` catches the resulting
exception and falls back to a hand-written question/evaluation/score rather
than crashing the session. This was already true for MKT (Phase 5) and this
phase confirmed it also holds for the plain interview path — but the retry
budget (3 attempts, ~7s total) is short relative to the kind of outage that
produced the Phase 5 daily-quota 429s (a ~24h `retryDelay`). A sustained
outage during a live demo will exhaust retries in seconds and the interview
will continue on fallback text/scores for its remaining duration, not recover
mid-session. The demo script's fallback talking points account for this.

## 3. No database migration tooling

Every model in `app/modules/*/models.py` is created via SQLAlchemy's
`create_all()`. There is no Alembic (or equivalent) migration chain. A schema
change requires deleting the dev SQLite file and letting it regenerate —
acceptable for a capstone project with no production data to preserve, but a
real limitation if this were to grow past a single-developer dev database.

## 4. Aptitude module's question bank is self-determined, not PDF-sourced

The aptitude module's question set and topic weighting were authored directly
rather than extracted from a source syllabus PDF — Phase 11's session found
no such PDF present in its environment. The content is reasonable and
covers standard placement-aptitude topics, but it is not traceable to an
external authoritative source the way the resume-RAG content is.

## 5. Frontend bundle is not code-split

`npm run build` succeeds cleanly but emits Vite's chunk-size warning: the main
JS bundle is 871 kB (268 kB gzipped), over the 500 kB guideline. This is a
deferred Phase 13 item (dynamic `import()` / manual chunking was identified
but not implemented, to avoid last-phase scope creep into a non-functional
change). Functionally harmless — it only affects first-load time, not
correctness — but worth naming since a panel member may open browser devtools.

## 6. Three `alert()` calls remain in the frontend

`frontend1/src/pages/ChatInterviewPage.jsx` has 3 remaining `alert()` calls
for error/confirmation UX. Flagged in Phase 13's audit as a polish item
(replace with the existing toast/`LoadingState` pattern used elsewhere) and
deliberately left as-is this phase too, per the "no scope creep" constraint —
a native browser `alert()` will block the page and look out of place in a
live demo if it's triggered, so the demo script avoids the specific actions
that trigger it.

## 7. Hand-labelled verifier corpus targets known weak points, not adversarial cases

Phase 5's README already flags this, repeated here because it bears on how
the LLM verifier's 1.000 accuracy should be read in a defense: the 154-item
corpus was authored to probe the known failure modes of a lexical/embedding
pipeline (terse answers, paraphrase without lexical overlap) — exactly where
an LLM has the most headroom. A perfect score means "this corpus doesn't
contain an example that breaks the LLM verifier," not "the LLM verifier is
provably perfect." A harder, adversarially-phrased corpus (plausible-sounding
misconceptions, multi-hop reasoning) remains a natural follow-up, not
something this phase attempted.

## 8. BKT baseline is a textbook implementation, not a tuned one

The BKT comparison (Phase 8) deliberately used hand-set standard-literature
defaults rather than EM-fitted-on-this-population parameters, specifically so
the comparison wouldn't be "MKT vs a BKT secretly tuned on the same data it's
scored against." This is the right call for a fair comparison, but it does
mean the reported BKT numbers are a lower bound on what a more carefully
tuned BKT deployment could achieve — the headline comparison (MKT's accuracy,
calibration, and misconception detection) would still hold given BKT's
structural inability to represent a misconception as distinct from "unknown,"
but the size of the accuracy/calibration gap specifically could narrow
somewhat with per-population BKT tuning.

## 9. This phase's hardening pass found no new bugs

Checked and confirmed still correct (not modified, since none needed fixing):
`speechSynthesis` watchdog (`InterviewScreen.jsx`) always resolves even if
`onend`/`onerror` never fire; camera (`getUserMedia`) and face-detector
initialization failures are caught and logged without crashing the session;
speech-recognition start failures are caught; and session resumption via
`GET /interview/sessions/{id}` still reconstructs full state correctly after
all later phases' additions to `InterviewSession`/`InterviewTurn`. Full
regression (131/131 backend tests, clean frontend build) confirms nothing
regressed across Phases 4-14.
