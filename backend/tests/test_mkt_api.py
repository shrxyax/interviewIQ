"""
End-to-end API test with two scripted candidates who give identical,
correct answers to every canonical question:

- "robust" answers transformed probes correctly and holds under pushback;
- "memoriser" breaks under changed constraints and capitulates.

The conventional score cannot tell them apart; the robustness index must.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.main import app
from app.modules.mkt.models import ProbeTemplate
from app.modules.mkt.service import MKTDeps, get_mkt_deps
from app.modules.mkt.states import BASE, MR_PUSHBACK
from tests.fakes import SubstringVerifier, fake_embed


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_mkt_deps] = lambda: MKTDeps(verifier=SubstringVerifier(), embed=fake_embed)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def _register(client, username):
    r = client.post("/auth/register", json={"username": username, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _answer_for(turn, persona):
    with SessionLocal() as db:
        template = db.get(ProbeTemplate, _template_id(turn))
        spec = template.relation_spec

    correct = ". ".join(spec.get("must_entail", []))

    if persona == "robust" or turn["probe_type"] == BASE:
        if turn["probe_type"] == MR_PUSHBACK:
            return f"No. not {spec['false_claim']}. {correct}"
        return correct

    # Memoriser: canonical answers are fine, transformed ones are not.
    if turn["probe_type"] == MR_PUSHBACK:
        return f"Yes, {spec['false_claim']}"

    wrong = spec.get("must_not_entail")
    return ". ".join(wrong) if wrong else "I don't know"


def _template_id(turn):
    with SessionLocal() as db:
        return (
            db.query(ProbeTemplate.id)
            .filter_by(concept_id=turn["concept_id"], probe_type=turn["probe_type"], question=turn["question"])
            .scalar()
        )


def _run_session(client, headers, persona, concepts):
    r = client.post("/mkt/sessions", json={"concept_ids": concepts, "budget": 12}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    session_id, turn = data["session_id"], data["turn"]

    for _ in range(12):
        r = client.post(
            f"/mkt/sessions/{session_id}/answer",
            json={"turn_id": turn["turn_id"], "answer": _answer_for(turn, persona), "latency_ms": 1000},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()

        if body["completed"]:
            return session_id, body["report"]

        turn = body["turn"]

    pytest.fail("Session did not complete within budget.")


CONCEPTS = ["dsa.graph.dijkstra", "dsa.search.binary_search", "dsa.hashing.hash_table"]


def test_concept_graph_is_seeded(client):
    r = client.get("/concepts/graph?domain=dsa")
    assert r.status_code == 200
    graph = r.json()

    ids = {n["id"] for n in graph["nodes"]}
    assert "dsa.graph.dijkstra" in ids
    assert {"source": "dsa.heap.binary_heap", "target": "dsa.graph.dijkstra"} in graph["edges"]


def test_robust_and_memoriser_get_same_conventional_score_but_different_robustness(client):
    _, robust = _run_session(client, _register(client, "robust_user"), "robust", CONCEPTS)
    _, memoriser = _run_session(client, _register(client, "memo_user"), "memoriser", CONCEPTS)

    assert robust["conventional_score"] == memoriser["conventional_score"] == 1.0
    assert robust["mean_robustness_index"] > 0.8
    assert memoriser["mean_robustness_index"] < 0.3
    assert robust["capitulations"] == 0

    memo_states = {c["concept_id"]: c["most_likely"] for c in memoriser["concepts"] if c["probed"]}
    robust_states = {c["concept_id"]: c["most_likely"] for c in robust["concepts"] if c["probed"]}
    assert set(memo_states.values()) == {"memorised"}
    assert set(robust_states.values()) == {"robust"}


def test_trace_exposes_full_reasoning(client):
    headers = _register(client, "trace_user")
    session_id, _ = _run_session(client, headers, "robust", CONCEPTS[:1])

    trace = client.get(f"/mkt/sessions/{session_id}/trace", headers=headers).json()
    first, second = trace["turns"][0], trace["turns"][1]

    assert first["probe_type"] == BASE
    for key in ("assessment", "outcome", "reasons", "belief_before", "belief_after", "eig"):
        assert first[key] is not None

    # Probe pairing: the transformation follows its base question directly.
    assert second["concept_id"] == first["concept_id"]
    assert second["probe_type"] != BASE


def test_sessions_are_private(client):
    owner = _register(client, "owner_user")
    session_id, _ = _run_session(client, owner, "robust", CONCEPTS[:1])

    r = client.get(f"/mkt/sessions/{session_id}/trace", headers=_register(client, "other_user"))
    assert r.status_code == 404


def test_wrong_turn_is_rejected(client):
    headers = _register(client, "turn_user")
    data = client.post("/mkt/sessions", json={"concept_ids": CONCEPTS[:1]}, headers=headers).json()

    r = client.post(
        f"/mkt/sessions/{data['session_id']}/answer",
        json={"turn_id": data["turn"]["turn_id"] + 999, "answer": "x"},
        headers=headers,
    )
    assert r.status_code == 400


def test_beliefs_persist_across_sessions(client):
    headers = _register(client, "persist_user")
    _run_session(client, headers, "robust", CONCEPTS[:1])

    profile = client.get("/profile/beliefs", headers=headers).json()
    dijkstra = next(c for c in profile["concepts"] if c["id"] == "dsa.graph.dijkstra")
    assert dijkstra["most_likely"] == "robust"

    # A new session starts from the stored belief, not the uniform prior.
    data = client.post("/mkt/sessions", json={"concept_ids": CONCEPTS[:1]}, headers=headers).json()
    assert data["turn"]["belief"][3] > 0.5
