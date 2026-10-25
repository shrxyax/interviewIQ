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


def test_dsa_sheet_is_seeded_with_progress(client):
    headers = _register(client, "content_user_1")
    sheet = client.get("/sheets/dsa", headers=headers).json()

    assert sheet["total"] > 100
    assert sheet["solved"] == 0
    assert len(sheet["topics"]) == 15

    first_problem = sheet["topics"][0]["problems"][0]
    assert first_problem["status"] == "unsolved"

    r = client.post(f"/sheets/dsa/problems/{first_problem['id']}/status", json={"status": "solved"}, headers=headers)
    assert r.status_code == 200

    sheet2 = client.get("/sheets/dsa", headers=headers).json()
    assert sheet2["solved"] == 1


def test_core_cs_sheet_has_five_topics(client):
    sheet = client.get("/sheets/core-cs").json()
    assert len(sheet["topics"]) == 5
    assert all(len(t["notes"]) >= 3 for t in sheet["topics"])


def test_companies_and_readiness(client):
    headers = _register(client, "content_user_2")
    companies = client.get("/companies").json()
    assert any(c["id"] == "google" for c in companies)

    readiness = client.get("/companies/google/readiness", headers=headers).json()
    assert readiness["readiness_pct"] == 0.0  # fresh user, nothing solved yet
    assert len(readiness["weakest_areas"]) == 5

    plan = client.get("/companies/google/plan", headers=headers).json()
    assert len(plan) > 0
    assert "reason" in plan[0]


def test_readiness_improves_after_solving_weighted_problems(client):
    headers = _register(client, "content_user_3")
    before = client.get("/companies/google/readiness", headers=headers).json()["readiness_pct"]

    sheet = client.get("/sheets/dsa", headers=headers).json()
    graphs_topic = next(t for t in sheet["topics"] if t["id"] == "dsa_sheet.graphs")

    for p in graphs_topic["problems"]:
        client.post(f"/sheets/dsa/problems/{p['id']}/status", json={"status": "solved"}, headers=headers)

    after = client.get("/companies/google/readiness", headers=headers).json()["readiness_pct"]
    assert after > before
