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


TWO_SUM_CORRECT = """
def solve(nums, target):
    seen = {}
    for i, n in enumerate(nums):
        if target - n in seen:
            return [seen[target - n], i]
        seen[n] = i
"""

TWO_SUM_WRONG = """
def solve(nums, target):
    return [0, 0]
"""

INFINITE_LOOP = """
def solve(nums, target):
    while True:
        pass
"""

UNSAFE_CODE = """
import os
def solve(nums, target):
    os.system("echo hacked")
    return [0, 1]
"""


def test_problems_are_seeded(client):
    problems = client.get("/code/problems").json()
    assert len(problems) >= 15
    assert any(p["id"] == "code.two_sum" for p in problems)


def test_problem_detail_has_statement_and_starter(client):
    p = client.get("/code/problems/code.two_sum").json()
    assert "Two Sum" in p["title"]
    assert "def solve" in p["starter_code"]
    assert len(p["sample_tests"]) >= 1


def test_run_against_sample_tests(client):
    r = client.post("/code/problems/code.two_sum/run", json={"code": TWO_SUM_CORRECT}).json()
    assert r["passed"] == r["total"]
    assert all(res["status"] == "ok" for res in r["results"])


def test_submit_correct_solution_gets_ac(client):
    headers = _register(client, "coder_1")
    r = client.post("/code/problems/code.two_sum/submit", json={"code": TWO_SUM_CORRECT}, headers=headers).json()
    assert r["verdict"] == "AC"
    assert r["passed"] == r["total"]


def test_submit_wrong_solution_gets_wa(client):
    headers = _register(client, "coder_2")
    r = client.post("/code/problems/code.two_sum/submit", json={"code": TWO_SUM_WRONG}, headers=headers).json()
    assert r["verdict"] == "WA"
    assert r["passed"] < r["total"]


def test_submit_infinite_loop_gets_tle(client):
    headers = _register(client, "coder_3")
    r = client.post("/code/problems/code.two_sum/submit", json={"code": INFINITE_LOOP}, headers=headers).json()
    assert r["verdict"] == "TLE"


def test_submit_unsafe_code_is_blocked(client):
    headers = _register(client, "coder_4")
    r = client.post("/code/problems/code.two_sum/submit", json={"code": UNSAFE_CODE}, headers=headers).json()
    assert r["verdict"] == "UNSAFE"


def test_submission_history_is_recorded(client):
    headers = _register(client, "coder_5")
    client.post("/code/problems/code.two_sum/submit", json={"code": TWO_SUM_CORRECT}, headers=headers)
    client.post("/code/problems/code.two_sum/submit", json={"code": TWO_SUM_WRONG}, headers=headers)

    subs = client.get("/code/problems/code.two_sum/submissions", headers=headers).json()
    assert len(subs) == 2
    assert {s["verdict"] for s in subs} == {"AC", "WA"}


def test_hidden_tests_are_not_leaked_in_submit_response(client):
    headers = _register(client, "coder_6")
    p = client.get("/code/problems/code.two_sum").json()
    r = client.post("/code/problems/code.two_sum/submit", json={"code": TWO_SUM_CORRECT}, headers=headers).json()
    assert len(r["visible_results"]) == len(p["sample_tests"])
    assert r["total"] > len(p["sample_tests"])  # hidden tests exist and were run, just not shown in detail
