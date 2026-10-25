# Live Demo Script

Target slot: **12 minutes** demo + buffer for panel questions (adjust timings
proportionally for a shorter/longer slot). Sign-in/onboarding is assumed
already done before the clock starts — do that setup before the panel is
watching.

Pre-demo checklist (do this 10 minutes before, not live):
- Backend running (`uvicorn app.main:app --reload`), frontend running
  (`npm run dev`), both reachable.
- A test Gemini call succeeded in the last few minutes (open `/mkt` once,
  confirm it responds) — catches a dead API key or an exhausted daily quota
  *before* the panel is watching, not during.
- Browser devtools console open on a second monitor/tab so you (not the
  panel) can see any error the moment it happens.
- Have a resume PDF already uploaded on the demo account, so the interview
  step doesn't spend time on a file picker.

## 1. Full interview with an MKT turn (0:00–5:00)

1. Go to `/` (chat/interview entry), start a **Technical** interview for a
   role that matches the uploaded resume.
2. Answer the opening question normally (~30–45s, keep it natural-length —
   long answers slow the demo down).
3. Continue until an MKT-driven turn appears. **Narrate while it's
   generating**: "this question isn't just LLM small talk — it's drawn from
   the metamorphic probe bank, and the answer feeds a Bayesian belief update
   over four states: robust, memorised, misconceived, absent."
4. Answer it well (genuinely correct, ideally in your own words rather than
   quoting the textbook phrasing, since that's the harder case the verifier
   is actually built to handle).
5. Finish the interview (end it early via the UI's end/submit action if the
   full flow would run long — 3-4 answered turns is enough to have a
   non-trivial report).

**If Gemini is slow/rate-limited here:** say so out loud immediately —
"that's a live API call, not a bug" — and keep talking through what's
happening while it resolves. Do not sit in silence. If it's still stuck after
~15s, this is the one moment to fall back to narrating the *pre-captured*
numbers in `backend/app/modules/mkt/eval/results/README.md` instead of
waiting live.

## 2. Final report → Evidence Trail (5:00–7:30)

1. Open the final report. Go straight to the **Knowledge-Depth** section —
   this is the MKT-informed part, not the generic communication/technical
   scores every interview tool has.
2. Immediately open the **Evidence Trail** (`EvidenceTimeline`) alongside it
   and point at the turn you just answered: "this is the actual probe type,
   the verifier's classification, and the belief state transition for that
   exact answer — not a black box."
3. One sentence connecting them: the report's summary number is backed by
   the trail's per-turn evidence, which is itself backed by the Phase 5
   verifier-accuracy numbers you'll show next.

## 3. Standalone `/mkt` demo — mechanism (7:30–10:00)

1. Navigate to `/mkt`. This is the deeper, non-interview-embedded view of the
   same engine.
2. Pick a concept, show a probe being selected (point out it's chosen by
   expected information gain, not asked round-robin) and answer it with a
   deliberately *inconsistent* second answer if time allows — this is the
   one thing the live interview demo can't easily show on purpose (you don't
   want to fake wrong answers in front of the panel during your own
   interview), but it's the exact scenario that separates "robust" from
   "memorised."
3. Point at the belief distribution updating live after the answer.

## 4. BKT comparison — why this is a contribution (10:00–12:00)

Don't run `compare.py` live — it takes real time for no visual payoff. Show
the numbers already in `backend/app/modules/mkt/baselines/results/README.md`
(have it open in a second tab) and say, in order:

1. "Same adaptive-selection procedure, same probe budget, MKT vs. standard
   Bayesian Knowledge Tracing from the literature: **0.958 vs 0.875**
   accuracy, even on BKT's own 2-state task."
2. "MKT is also better calibrated — when it says 73% confident, that number
   means something; BKT is systematically underconfident in its mid-range."
3. Close with the structural point, not just the numbers: "BKT has no bit of
   state for 'consistently wrong in a specific way' — it cannot represent a
   misconception as distinct from not knowing, at any accuracy level. That's
   not something BKT does worse, it's something BKT's model can't do at all."

## Fallback talking points if Gemini is slow/rate-limited during the demo

- Say it out loud, once, factually: "this depends on a live Gemini call; if
  it's slow I'll narrate through it rather than wait in silence."
- If a turn's generation stalls past ~10-15s: switch to narrating the
  pre-computed Phase 5/8 results (both READMEs, keep them open in tabs
  beforehand) while the request either completes in the background or the
  interview's own fallback (hand-written question/score) kicks in — it will,
  within ~7s of retries, per `LIMITATIONS.md` §2.
- If the interview's answer-evaluation step falls back (you'll see a generic
  "reviewed, but detailed evaluation was unavailable" message), don't try to
  hide it — say what it is: "that's the LLM fallback path, exactly the
  degradation `LocalVerifier`'s 0.727-vs-1.000 accuracy gap quantifies in the
  report." Turning an unplanned failure into the limitations talking point is
  better than pretending it didn't happen.
- Have the `/mkt` page open and already warmed up (one earlier call made) as
  the lowest-risk fallback demo if the full interview flow is having
  problems — it's less code path, fewer places to fail.

## What NOT to do live

- Don't trigger `ChatInterviewPage`'s remaining `alert()` paths (see
  `LIMITATIONS.md` §6) — avoid the specific error/cancel actions that raise
  them; a blocking native dialog mid-demo looks worse than it is.
- Don't resize the browser window drastically or inspect the >500 kB bundle
  warning live unless asked — it's a known, named limitation
  (`LIMITATIONS.md` §5), not something to spotlight unprompted.
- Don't run `python -m app.modules.mkt.baselines.compare` or the verifier
  eval scripts live — they're reproducible (see `REPRODUCE.md`) but add
  minutes for no visual payoff during a timed slot.
