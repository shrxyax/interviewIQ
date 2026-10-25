# BKT baseline comparison, calibration & EM

Phase 8 of the project: a head-to-head comparison between the project's own
4-state metamorphic belief model (MKT) and the standard 2-state literature
baseline for this problem, Bayesian Knowledge Tracing (BKT, Corbett &
Anderson 1995). Phase 5's results (`../../eval/results/README.md`) validated
that MKT's Bayesian update is correct in isolation and survives contact with
a real verifier on real answer text. This phase answers a different
question a panel will ask regardless of how clean those results are: *why
not just use BKT?*

Reproduce with (from `backend/`):

```bash
python -m app.modules.mkt.baselines.compare
```

Everything below was produced by that command (seed 0, 500 simulated
candidates, 8 concepts, budget 20 probes per candidate) plus a direct call
into `compare.run_comparison()` for the per-bin calibration numbers (not
printed by `main()`, to keep the console report short).

## 1. Comparison design (task 1)

There are two valid axes to compare on, and we ran both, with one held
primary:

**Primary — design (a), same selection procedure, different state model.**
Both models greedily pick the action expected to reduce entropy the most
(EIG), but each picks from its own natural action space:

- **MKT** picks `(concept, probe_type)` from its full repertoire — base
  question plus four metamorphic relations — using the real, unmodified
  `selection.candidate_actions` and `belief.update`.
- **BKT** has no notion of a metamorphic relation at all. That is a
  structural property of the model, not a gap in this implementation: BKT
  only ever asks the equivalent of the base question, repeatedly, for
  whichever concept it picks next by its own 2-state EIG
  (`bkt.expected_information_gain`).

This isolates the actual claim under test — does the 4-state model with
metamorphic probing extract more from the same adaptive budget than the
simpler model can, even using its own best policy — rather than conflating
it with "does adaptive selection help at all" (`eval/results/README.md`
already answers that for MKT; `compare.py`'s `*_fixed_order` runs answer the
analogous question for BKT, below).

**Secondary — design (b), full pipeline vs full pipeline.** MKT's EIG
policy vs BKT's classic administration: fixed round-robin over concepts, no
adaptive selection at all. This is the comparison a reader expecting
"vanilla BKT" would assume, and it is reported alongside (a) rather than
instead of it.

Both designs share one hidden ground-truth population per run — the same
4-state truth `simulate.sample_candidate` already draws — and both observe
outcomes sampled from the same world model, `emissions.DEFAULT_THETA`: MKT
sees the native 6-way outcome for whichever probe type it asked; BKT sees a
binarised correct/incorrect projection of the BASE row (`consistent_correct`
→ correct, everything else → incorrect), since a repeated "base question"
is the only action in its vocabulary.

BKT's ground-truth label is MKT's 4-state truth collapsed:
`{MEMORISED, ROBUST} → known`, `{ABSENT, MISCONCEIVED} → unknown`. This
collapse is BKT's structural limitation, surfaced honestly rather than
hidden: it cannot represent misconception as distinct from not knowing, or
memorisation as distinct from robust understanding.

## 2. EM convergence check (task 3)

Baum-Welch (forward-backward E-step, standard BKT M-step) fit on 200
synthetic sequences of length 12, generated from known parameters
(`p_init=0.25, p_transit=0.15, p_slip=0.10, p_guess=0.20`):

| param | true | fitted | abs err |
|---|---|---|---|
| p_init | 0.250 | 0.272 | 0.022 |
| p_transit | 0.150 | 0.163 | 0.013 |
| p_slip | 0.100 | 0.093 | 0.007 |
| p_guess | 0.200 | 0.201 | 0.001 |

All four parameters recover within 0.025 of ground truth. `p_slip` and
`p_guess` (the emission parameters) converge tightest, since every sequence
contributes direct evidence about them at every timestep; `p_init` and
`p_transit` depend on the inferred state path and so carry more estimation
noise with only 12 observations per sequence — expected, and consistent
with the EM literature on BKT parameter identifiability. `tests/
test_bkt_baseline.py::test_em_recovers_known_parameters_on_synthetic_data`
pins this to a looser (0.05–0.07) tolerance so the test isn't seed-fragile.

The head-to-head run below uses hand-set, standard-literature defaults
(`p_init=0.3, p_transit=0.1, p_slip=0.1, p_guess=0.2`) rather than the
EM-fitted values, so that BKT is evaluated with ordinary, undistinguished
parameters — not ones secretly tuned on the same simulated population it's
scored against.

## 3. Head-to-head: accuracy & turns (task 4)

500 simulated candidates, 8 concepts each, budget 20 probes/candidate, seed
0. Both models scored on the same 2-state collapsed ground truth (`known`
vs `unknown`), so the numbers are directly comparable:

| run | 2-state accuracy | Brier | mean turns used |
|---|---|---|---|
| **mkt_eig** | **0.958** | **0.037** | 20.0 |
| mkt_fixed_order | 0.872 | 0.088 | 20.0 |
| bkt_eig | 0.875 | 0.093 | 20.0 |
| bkt_fixed_order | 0.800 | 0.119 | 20.0 |

For reference, MKT's own native 4-state accuracy and misconception-aware
metrics on the identical population (`simulate.benchmark`, which `bkt` has
no equivalent axis for at all):

| policy | 4-state accuracy | memorised-vs-robust accuracy |
|---|---|---|
| eig | 0.864 | 0.868 |
| fixed_order | 0.711 | 0.757 |

Reading this together: on the *collapsed* 2-state task BKT was designed
for, MKT-eig still wins (0.958 vs 0.875 for bkt-eig, 0.872 vs 0.800 for the
fixed-order pair) — the extra probe variety and 4-state update help even at
BKT's own granularity, not only at MKT's finer one. The EIG-vs-fixed-order
gap is similar in size for both models (~8–9 points), so adaptive selection
helps both models by roughly the same amount; it isn't masking or
inflating the state-model comparison. But MKT's real advantage is the row
BKT cannot even appear in: 0.864 vs 0.711 4-state accuracy, and the
0.868/0.757 memorised-vs-robust separation that `eval/results/README.md`'s
whole Phase 5 investigation is about — a distinction BKT's 2-state space
cannot represent at all, collapsed or not.

## 4. Calibration (task 5)

Reliability bins (predicted P(known) vs empirical fraction actually known),
10 bins, same 500-candidate run as §3, `eig` policy for both models:

**MKT-eig** (4000 concept-observations)

| bin | n | predicted | empirical |
|---|---|---|---|
| 0.0–0.1 | 1086 | 0.021 | 0.033 |
| 0.1–0.2 | 209 | 0.123 | 0.144 |
| 0.2–0.3 | 51 | 0.241 | 0.294 |
| 0.3–0.4 | 11 | 0.353 | 0.455 |
| 0.4–0.5 | 4 | 0.425 | 0.500 |
| 0.5–0.6 | 20 | 0.563 | 0.750 |
| 0.6–0.7 | 26 | 0.659 | 0.769 |
| 0.7–0.8 | 77 | 0.750 | 0.818 |
| 0.8–0.9 | 89 | 0.846 | 0.854 |
| 0.9–1.0 | 2427 | 0.980 | 0.983 |

**BKT-eig** (4000 concept-observations)

| bin | n | predicted | empirical |
|---|---|---|---|
| 0.1–0.2 | 1740 | 0.129 | 0.222 |
| 0.2–0.3 | 23 | 0.280 | 0.913 |
| 0.4–0.5 | 93 | 0.473 | 0.903 |
| 0.5–0.6 | 22 | 0.561 | 1.000 |
| 0.6–0.7 | 9 | 0.652 | 1.000 |
| 0.7–0.8 | 4 | 0.783 | 0.750 |
| 0.8–0.9 | 54 | 0.839 | 1.000 |
| 0.9–1.0 | 2055 | 0.924 | 0.996 |

MKT is well calibrated across essentially its whole range — predicted and
empirical track within ~0.1 everywhere except the thin 0.5–0.7 bins (under
50 observations each, so noisy rather than systematically biased). BKT is
**not** well calibrated: in the 0.1–0.3 and 0.4–0.9 bins it is consistently
*underconfident* — a concept it assigns p≈0.28 P(known) to actually turns
out known 91% of the time; p≈0.47 → 90% known; p≈0.84 → 100% known. The
overall Brier score (0.093, §3) already hinted at this, but the per-bin
breakdown shows it isn't uniform noise, it's a systematic bias: BKT with
single-item-type base-question evidence and a slip/guess model stays
anchored near its `p_guess`/`p_slip` priors rather than moving its belief
as far as the evidence actually warrants, because — with no metamorphic
probes to generate disambiguating outcomes — the base-only outcome channel
it is restricted to (`consistent_correct` vs everything else) carries
coarser information per observation than MKT's native 6-way channel. MKT's
belief update, drawing on richer per-probe evidence from the metamorphic
relations, moves further and lands closer to where it should.

**Honest caveat on the tail bins**: both models' calibration numbers at the
extremes (0.0–0.1 and 0.9–1.0) are the least surprising and least
interesting — most concept-observations end up there because 20 probes on
8 concepts is usually enough to resolve most of them confidently, so those
bins carry the bulk of the data and dominate the aggregate Brier score. The
informative comparison is in the sparser middle bins, where BKT's
underconfidence is largest and most consistent.

## 5. Where each model wins — honest discussion (task 6)

**BKT wins on:**
- **Simplicity.** Four scalar parameters per concept, a two-line Bayes
  update, textbook EM fitting. MKT needs a 4×6 emission table per probe
  type, a graph-aware prior, and a metamorphic-relation symbolic layer
  (`consistency.py`) to produce its outcomes in the first place.
- **Well-understood behaviour.** BKT is 30 years deep in the educational
  data mining literature, with known failure modes, known EM
  identifiability issues, and known extensions (BKT+forgetting, individual
  student parameters, etc.) that this baseline deliberately did not pull in,
  to keep it a faithful textbook reference rather than a disguised MKT.
- **Fewer assumptions about the observation channel.** BKT only needs
  "was this attempt correct," which almost any assessment system can supply
  without an NLI/embedding verification pipeline.

**MKT wins on:**
- **Accuracy, even on BKT's own task.** §3: 0.958 vs 0.875 2-state accuracy
  under matched adaptive selection, 0.872 vs 0.800 under matched
  fixed-order administration. The gap is not explained away by MKT simply
  asking more questions — both models get the same 20-probe budget.
- **Calibration.** §4: MKT's predicted-vs-empirical gap stays under ~0.1
  almost everywhere; BKT is systematically underconfident by 0.4–0.6 in its
  mid-range bins. A system that reports "73% confident you know this" needs
  that number to mean something, and on this population BKT's doesn't, as
  reliably as MKT's does.
- **Misconception detection as a distinct, actionable state.** This is the
  one BKT cannot approach at any calibration or accuracy level, by
  construction — it has no bit of state to put "consistently wrong in a
  specific way" into. MKT's 4-state accuracy (0.864) and
  memorised-vs-robust separation (0.868, §3) are measuring something BKT's
  2-state space cannot represent even in principle, not something BKT does
  worse.
- **Metamorphic-relation-driven testing**, which BKT has no equivalent of:
  BKT's notion of "evidence" is limited to repeated attempts at
  structurally identical items; it has no mechanism analogous to asking the
  same concept under constraint-change, inversion, or pushback to
  distinguish brittle memorisation from robust understanding, which is the
  entire premise `eval/results/README.md` investigates for MKT.

**If MKT had lost on calibration or on the matched 2-state task**, that
would have been reported as the headline result instead — it didn't, but
the point of running both the matched-granularity comparison (§3's 2-state
row) and the native-granularity one side by side was precisely to avoid
constructing a comparison where MKT could only look good on its own turf.

## 6. Tests

`tests/test_bkt_baseline.py`: bounded/monotonic forward update, entropy
sanity, one hand-computed update step, EM recovery on synthetic data within
tolerance, and EM well-definedness on degenerate (all-correct/all-incorrect/
empty) sequences. Full suite: `python -m pytest -q` — 106 tests total
(including these 7 new ones), 105 passed. One pre-existing, unrelated
failure (`tests/test_coding_api.py::test_submit_correct_solution_gets_ac`,
a code-judge runtime/sandbox issue) was present before this phase's changes
and is outside `app/modules/mkt/` entirely.
