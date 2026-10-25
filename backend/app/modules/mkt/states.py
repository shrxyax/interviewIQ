"""
Vocabularies shared by every part of the MKT engine.
"""

# Latent knowledge state of one concept.
ABSENT = "absent"              # cannot produce relevant correct content
MEMORISED = "memorised"        # correct on the canonical form, brittle under transformation
MISCONCEIVED = "misconceived"  # consistently holds a specific wrong model
ROBUST = "robust"              # correct and consistent under transformation

STATES = [ABSENT, MEMORISED, MISCONCEIVED, ROBUST]
S_A, S_M, S_X, S_R = range(4)


# Discrete outcome of one probe (base probe or transformed probe).
CONSISTENT_CORRECT = "consistent_correct"
PARTIAL = "partial"
INCONSISTENT = "inconsistent"
CONSISTENT_WRONG = "consistent_wrong"
EMPTY = "empty"
CAPITULATED = "capitulated"

OUTCOMES = [
    CONSISTENT_CORRECT,
    PARTIAL,
    INCONSISTENT,
    CONSISTENT_WRONG,
    EMPTY,
    CAPITULATED,
]
OUTCOME_INDEX = {o: i for i, o in enumerate(OUTCOMES)}


# Probe types. BASE is the canonical question; the rest are metamorphic
# relations applied to it.
BASE = "base"
MR_PARAPHRASE = "mr_paraphrase"    # reframe; answers must be equivalent
MR_CONSTRAINT = "mr_constraint"    # change a constraint; answer must change as predicted
MR_INVERSION = "mr_inversion"      # ask in reverse; must identify the concept
MR_PUSHBACK = "mr_pushback"        # assert a plausible false claim; must hold
MR_TRANSFER = "mr_transfer"        # same concept in a structurally analogous new context

PROBE_TYPES = [BASE, MR_PARAPHRASE, MR_CONSTRAINT, MR_INVERSION, MR_PUSHBACK, MR_TRANSFER]
METAMORPHIC_RELATIONS = PROBE_TYPES[1:]

# Relative time cost of asking each probe type (used to normalise EIG).
PROBE_COST = {
    BASE: 1.0,
    MR_PARAPHRASE: 1.0,
    MR_CONSTRAINT: 1.2,
    MR_INVERSION: 0.8,
    MR_PUSHBACK: 0.8,
    MR_TRANSFER: 1.2,
}
