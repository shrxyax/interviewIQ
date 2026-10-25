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


def test_start_attempt_returns_question_set_without_answers(client):
    headers = _register(client, "apt_1")
    r = client.post("/aptitude/attempts", headers=headers).json()
    assert len(r["questions"]) >= 15
    assert {"quantitative", "logical", "verbal"} <= {q["category"] for q in r["questions"]}
    for q in r["questions"]:
        assert "correct_index" not in q
        assert "explanation" not in q


def test_submit_all_correct_scores_full_marks(client):
    headers = _register(client, "apt_2")
    started = client.post("/aptitude/attempts", headers=headers).json()
    attempt_id = started["attempt_id"]

    # Fetch the full seeded bank server-side via a second start is wasteful; instead
    # read correct answers from the detail endpoint isn't available pre-submit, so
    # we submit using known seed answers (mirrors the seed file's correct_index).
    answers = {
        "apt.quant.1": 1, "apt.quant.2": 1, "apt.quant.3": 1, "apt.quant.4": 0,
        "apt.quant.5": 1, "apt.quant.6": 2, "apt.quant.7": 2,
        "apt.logical.1": 2, "apt.logical.2": 0, "apt.logical.3": 0, "apt.logical.4": 0,
        "apt.logical.5": 1, "apt.logical.6": 0, "apt.logical.7": 0,
        "apt.verbal.1": 0, "apt.verbal.2": 0, "apt.verbal.3": 1, "apt.verbal.4": 1,
        "apt.verbal.5": 0, "apt.verbal.6": 1, "apt.verbal.7": 1,
    }
    r = client.post(f"/aptitude/attempts/{attempt_id}/submit", json={"answers": answers}, headers=headers).json()
    assert r["score"] == r["total"] == 21
    assert r["category_breakdown"]["quantitative"]["correct"] == 7
    assert r["category_breakdown"]["logical"]["correct"] == 7
    assert r["category_breakdown"]["verbal"]["correct"] == 7


def test_submit_all_wrong_scores_zero(client):
    headers = _register(client, "apt_3")
    started = client.post("/aptitude/attempts", headers=headers).json()
    attempt_id = started["attempt_id"]
    answers = {q["id"]: 99 for q in started["questions"]}  # out-of-range index never matches

    r = client.post(f"/aptitude/attempts/{attempt_id}/submit", json={"answers": answers}, headers=headers).json()
    assert r["score"] == 0


def test_unanswered_questions_count_as_wrong(client):
    headers = _register(client, "apt_4")
    started = client.post("/aptitude/attempts", headers=headers).json()
    attempt_id = started["attempt_id"]

    r = client.post(f"/aptitude/attempts/{attempt_id}/submit", json={"answers": {}}, headers=headers).json()
    assert r["score"] == 0
    assert r["total"] == 21


def test_cannot_submit_same_attempt_twice(client):
    headers = _register(client, "apt_5")
    started = client.post("/aptitude/attempts", headers=headers).json()
    attempt_id = started["attempt_id"]

    client.post(f"/aptitude/attempts/{attempt_id}/submit", json={"answers": {}}, headers=headers)
    r = client.post(f"/aptitude/attempts/{attempt_id}/submit", json={"answers": {}}, headers=headers)
    assert r.status_code == 400


def test_get_attempt_after_submit_reveals_correct_answers(client):
    headers = _register(client, "apt_6")
    started = client.post("/aptitude/attempts", headers=headers).json()
    attempt_id = started["attempt_id"]
    client.post(f"/aptitude/attempts/{attempt_id}/submit", json={"answers": {}}, headers=headers)

    r = client.get(f"/aptitude/attempts/{attempt_id}", headers=headers).json()
    assert r["status"] == "submitted"
    assert all("correct_index" in q for q in r["questions"])


def test_cannot_access_another_users_attempt(client):
    headers_a = _register(client, "apt_7a")
    headers_b = _register(client, "apt_7b")
    started = client.post("/aptitude/attempts", headers=headers_a).json()
    attempt_id = started["attempt_id"]

    r = client.get(f"/aptitude/attempts/{attempt_id}", headers=headers_b)
    assert r.status_code == 404


def test_attempt_history_is_listed(client):
    headers = _register(client, "apt_8")
    started = client.post("/aptitude/attempts", headers=headers).json()
    client.post(f"/aptitude/attempts/{started['attempt_id']}/submit", json={"answers": {}}, headers=headers)

    history = client.get("/aptitude/attempts", headers=headers).json()
    assert len(history) == 1
    assert history[0]["status"] == "submitted"
