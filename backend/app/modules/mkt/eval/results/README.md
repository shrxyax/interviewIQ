# Verifier validation and closed-loop results

This directory holds the empirical results for Phase 5: measuring the one
link in the MKT pipeline that `simulate.py`'s offline benchmark never
touches — real answer text → `assess_answer()` (verifier + symbolic layer)
→ answer class → Bayesian belief update.

`simulate.py` samples probe outcomes directly from the theta emission
tables, so its "EIG beats random" and "metamorphic probes separate
memorisation from robustness" results assume the observation model
(verifier → outcome) is accurate. This phase tests that assumption against
154 hand-labelled answers quoting the real seeded probe templates, every
answer paraphrasing (not quoting) the ground-truth statements so the
measurement is of semantic verification, not string overlap.

Reproduce with (from `backend/`):

```bash
python -m app.modules.mkt.eval.run_verifier_eval --verifier local  --out results/local.json
python -m app.modules.mkt.eval.run_verifier_eval --verifier llm    --out results/llm.json --sleep 3
python -m app.modules.mkt.eval.run_closed_loop    --verifier local    --out results/closed_loop_local.json
python -m app.modules.mkt.eval.run_closed_loop    --verifier fallback --out results/closed_loop_fallback.json --sleep 3
```

`--sleep` paces real Gemini calls at one every N seconds; cached calls (by
prompt hash, in the `llm_calls` table) skip the wait entirely, so an
interrupted run can always be safely rerun.

**Model note:** `GEMINI_MODEL` (`backend/.env`) is set to
`gemini-3.5-flash-lite`, not the `gemini-3.5-flash` default in
`app/core/config.py`. The default model's free tier turned out to be a hard
**20 requests/day** cap (discovered empirically: a run would hit 429 on
item 1 and the server's own `retryDelay` was ~24h — not a 5-req/min limit
as originally assumed), and that quota was already exhausted from an
earlier attempt. `gemini-3.5-flash-lite` sits on a separate, much more
permissive free quota and completed the full 154-item run at 3s spacing
with zero 429s. If you rerun this from scratch on a fresh key, check
whichever model you configure for its *daily*, not just per-minute, limit.

## 1. Verifier accuracy on the hand-labelled corpus (154 items)

### LocalVerifier (NLI cross-encoder + embedding similarity, no LLM)

| | precision | recall | support |
|---|---|---|---|
| empty | 0.526 | 0.909 | 11 |
| partial | 0.000 | — (0 expected) | 0 |
| wrong | 0.635 | 0.855 | 55 |
| correct | **0.917** | **0.625** | 88 |

- Overall answer-class accuracy: **0.727**
- Metamorphic-probe accuracy (robust/memoriser personas, non-base probes): **0.705**
- Pushback false-claim accuracy: **0.758**

Confusion matrix (rows = expected, columns = predicted):

| expected ↓ | empty | partial | wrong | correct |
|---|---|---|---|---|
| empty | 10 | 0 | 1 | 0 |
| wrong | 3 | 0 | 47 | 5 |
| correct | 6 | 1 | 26 | 55 |

### LLMVerifier (Gemini 3.5 Flash-Lite, structured output, one call per item)

| | precision | recall | support |
|---|---|---|---|
| empty | 1.000 | 1.000 | 11 |
| partial | — (0 expected) | — | 0 |
| wrong | 1.000 | 1.000 | 55 |
| correct | 1.000 | 1.000 | 88 |

- Overall answer-class accuracy: **1.000** (154/154)
- Metamorphic-probe accuracy (robust/memoriser personas, non-base probes): **1.000**
- Pushback false-claim accuracy: **1.000**

Confusion matrix is perfectly diagonal (11/11 empty, 55/55 wrong, 88/88
correct, 0 off-diagonal entries). Spot-checked a random sample of
predictions against the underlying answer text by hand to rule out a
measurement bug (e.g. a cache key collision or an eval-harness shortcut) —
the classifications are genuine and non-trivial: terse answers that
`LocalVerifier` missed (*"A min-heap, which is how you'd normally back a
priority queue."*, *"No [pushback accepted]. Discarding half the range is
only valid if order tells you which half the target is in..."*) are
correctly labelled.

A clean 1.000 on a 154-item corpus should be read as "this corpus doesn't
contain an example that breaks the LLM verifier," not as "the LLM verifier
is literally perfect" — the corpus was authored to probe the known
weak points of a lexical/embedding pipeline (terse answers, paraphrase
without lexical overlap), which happen to be exactly where an LLM's
semantic understanding has the most headroom over `LocalVerifier`. A
harder corpus (adversarial misconceptions phrased to sound correct,
multi-hop reasoning) would be a natural next test to find where the LLM
verifier's own ceiling is.

### Local vs LLM

| | LocalVerifier | LLMVerifier |
|---|---|---|
| Overall accuracy | 0.727 | **1.000** |
| Metamorphic-probe accuracy (R/M only) | 0.705 | **1.000** |
| Pushback false-claim accuracy | 0.758 | **1.000** |
| `correct` recall | 0.625 | **1.000** |
| `correct` precision | 0.917 | **1.000** |

The gap is entirely in `correct` recall (§2) — `LocalVerifier`'s precision
on `correct` is already decent (0.917); it just under-recognises correct
answers that are short or phrased without lexical overlap. The LLM
verifier has no such gap on this corpus. This is the expected direction
and size of the gap for a cross-encoder-NLI-plus-embedding heuristic versus
an LLM doing the same semantic-entailment task directly.

## 2. The characterized failure mode

`LocalVerifier`'s `correct` recall is only 0.625 against 0.917 precision —
when it's wrong about `correct`, it's almost never claiming something is
correct when it isn't; it's failing to recognise correct answers. 26 of 88
truly-correct answers were misclassified as `wrong`. Reading those 26:

- **Short, terse correct answers** get no credit: *"A min-heap."*,
  *"DFS."*, *"Dijkstra's algorithm."* — too little text for the embedding
  similarity check to clear its 0.80 threshold against the full
  `must_entail` statement, and NLI (used only for contradiction detection)
  never gets a chance to vote `supported`.
- **Synonymous technical phrasing without lexical overlap**, e.g.
  *"the cost grows... you drop constants and lower-order terms"* for a
  statement about asymptotic big-O notation, or *"every key collides into
  one chain, so lookup becomes a linear scan"* for a statement about
  worst-case hash table degradation.

This matches `consistency.py`'s own documented rationale for why
`LocalVerifier` uses NLI only for contradiction: general-domain NLI models
label most correct technical paraphrase as "neutral" rather than
"entailment," so entailment detection is left to embedding similarity,
which itself under-rewards short answers and non-overlapping phrasing.
This is a genuine, explainable limitation of a no-LLM fallback, not a bug —
reported honestly rather than papered over with looser thresholds.

## 3. Closed-loop: does verifier noise corrupt the final belief?

`run_closed_loop.py` takes the 22 (concept, persona) episodes where persona
is `robust` or `memoriser` (11 concepts × 2 personas, 5 probes each: base +
4 metamorphic relations), runs every answer through the **real**
`assess_answer()`, derives outcomes the same way `service.py::submit_answer`
does (`BASE_OUTCOME` / `relation_outcome`, including real embedding
similarity for `mr_constraint`), and feeds those real outcomes into
`belief.update()` in probe order, starting from the uniform prior. This is
the one experiment that measures the full pipeline end to end rather than
its two halves (`simulate.py` and the verifier corpus) separately.

### With LocalVerifier

| persona | n | MAP-state accuracy | mean robustness index |
|---|---|---|---|
| robust | 11 | **0.091** | 0.183 |
| memoriser | 11 | 0.727 | 0.044 |

Overall: 9/22 (0.409).

This is a real, informative negative result: `LocalVerifier`'s recall gap on
`correct` (§2) is not cosmetic — it propagates. A robust episode needs 4–5
consecutive `correct` verdicts across the base probe and all 4 metamorphic
probes to land on `CONSISTENT_CORRECT` outcomes and pull the belief toward
`ROBUST`; losing even one or two of those five to a false `wrong` turns the
transition into `INCONSISTENT` (the relation table's own "memorisation
signature," since `(correct, wrong) → INCONSISTENT`), which looks exactly
like genuine brittleness under transformation. 10 of 11 robust episodes
ended up classified as `memorised`, `misconceived`, or `absent` for this
reason — not because the engine's Bayesian math is wrong (`test_belief.py`
and `test_simulation.py` cover that in isolation and still pass), but
because `LocalVerifier`'s false negatives on `correct` are indistinguishable,
from the belief engine's point of view, from a candidate who actually
contradicts themselves under paraphrase/constraint/inversion/pushback.
Memoriser episodes fare much better (0.727) because a memoriser's *expected*
behaviour is to fail metamorphic probes — the verifier's conservative bias
happens to agree with the correct label there.

### With FallbackVerifier (LLM primary, Local secondary — production config)

| persona | n | MAP-state accuracy | mean robustness index |
|---|---|---|---|
| robust | 11 | **1.000** | 0.994 |
| memoriser | 11 | **1.000** | 0.058 |

Overall: 22/22 (**1.000**). With the LLM doing the verification (it never
needed to fall back to Local on this corpus), the belief engine recovers
essentially perfect separation: robust episodes end with mean robustness
index 0.994 (nearly all "known" probability mass attributed to robust
understanding) and memoriser episodes end at 0.058 (nearly all attributed
to memorisation) — a gap of ~0.94 on a [0, 1] scale, versus 0.183 vs 0.044
(a gap of ~0.14) under `LocalVerifier`.

This is the end-to-end result the earlier phases could only assume:
`simulate.py` already showed the belief engine's math correctly separates
states when fed clean theta-sampled outcomes, and this phase shows that,
with `FallbackVerifier` in its production LLM-primary configuration, real
verifier output on real answer text reproduces that separation almost
exactly. The 0.94 RI gap with the LLM versus the 0.14 RI gap with
`LocalVerifier` alone is a direct, quantified measure of how much the
fallback path costs when the LLM is unavailable — not nothing (an outage
would noticeably blur robust-vs-memorised detection), but not catastrophic
either (0.409 overall accuracy is well above the 0.25 chance rate for a
4-way state classification).

## 4. Takeaways

- The symbolic/belief layers (`belief.py`, `selection.py`, `simulate.py`)
  are validated and correct in isolation (Phase 4, `test_simulation.py`,
  `test_belief.py`).
- The verifier → answer-class link, measured here for the first time
  against real text, is the weaker half of the pipeline when running on
  `LocalVerifier` alone (0.727 accuracy, 0.625 recall on `correct`) but
  essentially solved by `LLMVerifier` on this corpus (1.000 accuracy).
- That gap propagates end to end: the closed-loop experiment shows the
  belief engine's robust-vs-memorised separation collapses from a 0.94 mean
  robustness-index gap (`FallbackVerifier`, production config) to a 0.14
  gap (`LocalVerifier` alone) — real, quantified evidence that verifier
  quality, not just the Bayesian update math, determines whether the MKT
  engine can tell "robust understanding" from "memorisation" in practice.
- This is exactly why `service.py::get_mkt_deps()` defaults to
  `FallbackVerifier(LLMVerifier(), LocalVerifier())` rather than
  `LocalVerifier` alone — `LocalVerifier` is the degraded path for when the
  LLM is unavailable, and this phase quantifies, for the first time, how
  much degradation that fallback costs: noticeably worse, but still far
  better than chance.
- The 100% LLM accuracy should be read with its caveat from §1: this
  corpus targets the known weak points of a lexical/embedding verifier, not
  adversarial cases designed to break an LLM. A natural follow-up is a
  harder corpus (plausible-sounding misconceptions, multi-hop reasoning)
  aimed at finding the LLM verifier's own failure modes.
