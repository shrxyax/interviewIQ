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


def test_core_cs_sheet_has_five_subjects_with_full_topic_lists(client):
    sheet = client.get("/sheets/core-cs").json()
    assert [s["id"] for s in sheet["topics"]] == [
        "core_cs.os", "core_cs.dbms", "core_cs.cn", "core_cs.oop", "core_cs.coa",
    ]
    assert all(len(s["notes"]) >= 12 for s in sheet["topics"])

    # The list carries summaries, not full bodies.
    first = sheet["topics"][0]["notes"][0]
    assert first["summary"] and "body_markdown" not in first


def test_core_cs_note_detail_and_navigation(client):
    sheet = client.get("/sheets/core-cs").json()
    notes = sheet["topics"][1]["notes"]

    middle = client.get(f"/sheets/core-cs/notes/{notes[1]['id']}").json()
    assert middle["subject"]["id"] == "core_cs.dbms"
    assert len(middle["body_markdown"]) > 500
    assert middle["prev"]["id"] == notes[0]["id"]
    assert middle["next"]["id"] == notes[2]["id"]
    assert middle["position"] == 2 and middle["total"] == len(notes)

    first = client.get(f"/sheets/core-cs/notes/{notes[0]['id']}").json()
    assert first["prev"] is None

    assert client.get("/sheets/core-cs/notes/core_cs.nope.n01").status_code == 404


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
