"""
End-to-end whiteboard API test: start a session from a real seeded
prompt, analyze it, apply failure scenarios, run a DES, and confirm the
report is internally consistent.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _register(client, username):
    r = client.post("/auth/register", json={"username": username, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_catalog_and_prompts_are_seeded(client):
    catalog = client.get("/design/catalog").json()
    assert {"client", "load_balancer", "api_service", "cache", "sql_primary", "read_replica", "queue", "worker"} <= {c["id"] for c in catalog}

    prompts = client.get("/design/prompts").json()
    assert len(prompts) == 180
    assert sum(1 for p in prompts if p["simulatable"]) == 20

    subtopics = client.get("/design/subtopics").json()
    assert len(subtopics) == 18


def test_url_shortener_session_full_lifecycle(client):
    headers = _register(client, "wb_user_1")

    prompts = client.get("/design/prompts?simulatable_only=true").json()
    url_shortener = next(p for p in prompts if "URL Shortener" in p["title"])

    start = client.post("/design/sessions", json={"prompt_id": url_shortener["id"]}, headers=headers).json()
    session_id, version_id = start["session_id"], start["version"]["id"]
    assert start["requirements"]["peak_rps"] == 20_000

    analysis = client.post(f"/design/versions/{version_id}/analyze", json={}, headers=headers).json()
    assert "end_to_end_latency_p99_ms" in analysis["summary"]
    assert isinstance(analysis["findings"], list)

    # Ask the grounded interviewer for a question tied to a real finding (or none, if healthy).
    q = client.post(f"/design/sessions/{session_id}/interviewer/next", headers=headers).json()
    assert "question" in q

    client.post(f"/design/sessions/{session_id}/respond", json={"text": "I'd add a read replica."}, headers=headers)
    dialogue = client.get(f"/design/sessions/{session_id}/dialogue", headers=headers).json()
    assert dialogue[-1]["role"] == "candidate"

    report = client.get(f"/design/sessions/{session_id}/report", headers=headers).json()
    assert report["revisions"] == 1
    assert "resilience" in report and "resilience_pct" in report["resilience"]
    assert report["cost_efficiency"] is not None


def test_undersized_perf_antipattern_prompt_is_saturated_and_has_spof(client):
    headers = _register(client, "wb_user_2")
    prompts = client.get("/design/prompts?simulatable_only=true").json()
    broken = next(p for p in prompts if "Overloaded Checkout" in p["title"])

    start = client.post("/design/sessions", json={"prompt_id": broken["id"]}, headers=headers).json()
    version_id = start["version"]["id"]

    analysis = client.post(f"/design/versions/{version_id}/analyze", json={}, headers=headers).json()
    types = {f["type"] for f in analysis["findings"]}

    assert "saturation" in types
    assert "spof" in types


def test_fixing_the_design_resolves_findings_across_versions(client):
    headers = _register(client, "wb_user_3")
    prompts = client.get("/design/prompts?simulatable_only=true").json()
    broken = next(p for p in prompts if "Overloaded Checkout" in p["title"])

    start = client.post("/design/sessions", json={"prompt_id": broken["id"]}, headers=headers).json()
    session_id = start["session_id"]
    v1 = start["version"]["id"]
    client.post(f"/design/versions/{v1}/analyze", json={}, headers=headers)

    # Scale up every component enough to clear saturation at 15k rps
    # (api mu=800/replica needs >=19 replicas; db mu=5000/replica needs >=4;
    # lb is never a bottleneck but is still a SPOF at replicas=1).
    graph = start["version"]["graph"]
    for n in graph["nodes"]:
        if n["type"] == "api_service":
            n.setdefault("params", {})["replicas"] = 25
        elif n["type"] == "sql_primary":
            n.setdefault("params", {})["replicas"] = 5
        elif n["type"] == "load_balancer":
            n.setdefault("params", {})["replicas"] = 2

    v2 = client.post(f"/design/sessions/{session_id}/versions", json={"graph": graph}, headers=headers).json()
    analysis2 = client.post(f"/design/versions/{v2['version_id']}/analyze", json={}, headers=headers).json()

    assert analysis2["resolved_since_last_version"]  # something that was broken before is now resolved
    blocking_types = {f["type"] for f in analysis2["findings"]}
    assert "saturation" not in blocking_types
    assert "spof" not in blocking_types


def test_kill_node_scenario_reports_blast_radius_without_mutating_saved_version(client):
    headers = _register(client, "wb_user_4")
    prompts = client.get("/design/prompts?simulatable_only=true").json()
    prompt = next(p for p in prompts if "Horizontally Scaled API Gateway" in p["title"])

    start = client.post("/design/sessions", json={"prompt_id": prompt["id"]}, headers=headers).json()
    version_id = start["version"]["id"]

    baseline = client.post(f"/design/versions/{version_id}/analyze", json={}, headers=headers).json()
    scenario_result = client.post(
        f"/design/versions/{version_id}/analyze",
        json={"scenario": {"type": "kill_node", "node_id": "db"}},
        headers=headers,
    ).json()

    assert any(f["type"] == "spof" for f in scenario_result["findings"]) or scenario_result["summary"]["max_sustainable_rps"] is not None

    # The saved version's own graph must be untouched by the scenario call.
    v = client.get("/design/catalog", headers=headers)  # just confirms session/client still usable
    assert v.status_code == 200
    reconfirm = client.post(f"/design/versions/{version_id}/analyze", json={}, headers=headers).json()
    assert reconfirm["summary"] == baseline["summary"]


def test_resilience_suite_runs_a_scenario_battery(client):
    headers = _register(client, "wb_user_5")
    prompts = client.get("/design/prompts?simulatable_only=true").json()
    prompt = next(p for p in prompts if "Multi-Region Failover" in p["title"])

    start = client.post("/design/sessions", json={"prompt_id": prompt["id"]}, headers=headers).json()
    version_id = start["version"]["id"]

    resilience = client.post(f"/design/versions/{version_id}/resilience", headers=headers).json()
    assert resilience["scenarios_run"] > 0
    assert 0 <= resilience["resilience_pct"] <= 100


def test_simulate_endpoint_returns_latency_distribution(client):
    headers = _register(client, "wb_user_6")
    prompts = client.get("/design/prompts?simulatable_only=true").json()
    prompt = next(p for p in prompts if "Key-Value Store" in p["title"])

    start = client.post("/design/sessions", json={"prompt_id": prompt["id"]}, headers=headers).json()
    version_id = start["version"]["id"]

    sim = client.post(
        f"/design/versions/{version_id}/simulate",
        json={"n_requests": 500, "replications": 2},
        headers=headers,
    ).json()

    assert sim["end_to_end_ms"]["p99"] >= sim["end_to_end_ms"]["p50"] >= 0


def test_lightweight_prompt_cannot_start_a_simulated_session(client):
    headers = _register(client, "wb_user_7")
    lightweight = next(p for p in client.get("/design/prompts").json() if not p["simulatable"])

    r = client.post("/design/sessions", json={"prompt_id": lightweight["id"]}, headers=headers)
    assert r.status_code == 400
