import pytest

from app.modules.mkt.consistency import (
    A_EMPTY,
    CORRECT,
    WRONG,
    assess_answer,
    complexities_in,
    is_empty,
    normalise_complexity,
    relation_outcome,
)
from app.modules.mkt.states import (
    CAPITULATED,
    CONSISTENT_CORRECT,
    CONSISTENT_WRONG,
    INCONSISTENT,
    MR_CONSTRAINT,
    MR_PARAPHRASE,
    MR_PUSHBACK,
)
from tests.fakes import SubstringVerifier


V = SubstringVerifier()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("log n", "logn"),
        ("log(n)", "logn"),
        ("n log n", "nlogn"),
        ("n²", "n^2"),
        ("V + E", "v+e"),
    ],
)
def test_normalise_complexity(raw, expected):
    assert normalise_complexity(raw) == expected


def test_complexities_in_text_and_words():
    assert complexities_in("It runs in O(log n) time") == {"logn"}
    assert complexities_in("lookups are constant time") == {"1"}
    assert complexities_in("O((V + E) log V)") == {"(v+e)logv"}


def test_is_empty():
    assert is_empty("")
    assert is_empty("I don't know")
    assert not is_empty("Dijkstra")
    assert not is_empty("I'm not sure but I think it halves the range each step and needs sorted input to work")


def test_correct_answer_and_misconception():
    spec = {"must_entail": ["halves the range", "runs in o(log n) time"]}
    good, _ = assess_answer("q", "It halves the range and runs in O(log n) time", spec, ["works on unsorted arrays"], V)
    bad, _ = assess_answer("q", "It halves the range and works on unsorted arrays", spec, ["works on unsorted arrays"], V)

    assert good.answer_class == CORRECT
    assert bad.answer_class == WRONG
    assert bad.misconceptions_hit == ["works on unsorted arrays"]


def test_symbolic_complexity_upgrades_not_addressed():
    spec = {"must_entail": ["Binary search runs in O(log n) time"]}
    result, _ = assess_answer("q", "Each step is cheap so overall O(log(n))", spec, [], V)

    assert result.answer_class == CORRECT
    assert result.verdicts["Binary search runs in O(log n) time"]["source"] == "complexity"


def test_keyword_layer_for_inversion():
    spec = {"must_entail": ["The algorithm is Dijkstra's algorithm"], "keywords": ["dijkstra"]}
    result, _ = assess_answer("q", "Dijkstra", spec, [], V)

    assert result.answer_class == CORRECT


def test_irrelevant_answer_is_absent_signature():
    spec = {"must_entail": ["uses a priority queue"]}
    result, _ = assess_answer("q", "It is a famous algorithm from the 1950s", spec, [], V)

    assert result.answer_class == A_EMPTY


def test_memorisation_signature():
    spec = {"must_entail": ["dijkstra may give incorrect results"], "must_not_entail": ["dijkstra still works"]}
    transformed, _ = assess_answer("q", "dijkstra still works, it picks the closest node", spec, [], V)

    outcome, _ = relation_outcome(MR_CONSTRAINT, CORRECT, transformed)
    assert outcome == INCONSISTENT


def test_misconception_signature():
    spec = {"must_entail": ["x"], "must_not_entail": ["dijkstra still works"]}
    transformed, _ = assess_answer("q", "dijkstra still works", spec, [], V)

    outcome, _ = relation_outcome(MR_CONSTRAINT, WRONG, transformed)
    assert outcome == CONSISTENT_WRONG


def test_paraphrase_self_contradiction():
    spec = {"must_entail": ["uses a queue"]}
    transformed, _ = assess_answer(
        "q", "it uses a queue. not visits nodes level by level", spec, [], V,
        extra_statements=["visits nodes level by level"],
    )

    outcome, reasons = relation_outcome(MR_PARAPHRASE, CORRECT, transformed, prior_claims_contradicted=1)
    assert outcome == INCONSISTENT
    assert any("contradicted" in r for r in reasons)


def test_pushback_outcomes():
    spec = {"must_entail": ["dijkstra can fail with negative weights"], "false_claim": "dijkstra works with negative weights"}

    caved, _ = assess_answer("q", "yes, dijkstra works with negative weights", spec, [], V)
    held, _ = assess_answer("q", "no, not dijkstra works with negative weights", spec, [], V)

    assert relation_outcome(MR_PUSHBACK, CORRECT, caved)[0] == CAPITULATED
    assert relation_outcome(MR_PUSHBACK, CORRECT, held)[0] == CONSISTENT_CORRECT


def test_unchanged_answer_under_constraint_change():
    spec = {"must_entail": ["bellman-ford"]}
    transformed, _ = assess_answer("q", "it picks the closest unvisited node", spec, [], V)

    outcome, reasons = relation_outcome(MR_CONSTRAINT, CORRECT, transformed, answer_similarity=0.97)
    assert outcome == INCONSISTENT
    assert any("did not adapt" in r for r in reasons)
