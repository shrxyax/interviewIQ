import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.core.models import Resume
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _register(client, username):
    r = client.post("/auth/register", json={"username": username, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_resume(user_id: int) -> int:
    with SessionLocal() as db:
        resume = Resume(user_id=user_id, filename="resume.pdf", pages=2, chunks=10)
        db.add(resume)
        db.commit()
        return resume.id


CONTEXT_BODY = {
    "target_role": "Frontend Engineer",
    "company": "Flipkart",
    "experience_level": "junior",
    "interview_type": "technical",
    "duration_minutes": 30,
}


def test_create_context_without_resume(client):
    headers = _register(client, "ctx_user_1")

    r = client.post("/interview/context", json=CONTEXT_BODY, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["target_role"] == "Frontend Engineer"
    assert body["company"] == "Flipkart"
    assert body["interview_type"] == "technical"
    assert body["resume_id"] is None
    assert body["status"] == "active"


def test_create_context_with_owned_resume(client):
    r = client.post("/auth/register", json={"username": "ctx_user_2", "password": "secret123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    with SessionLocal() as db:
        from app.core.models import User

        user = db.query(User).filter_by(username="ctx_user_2").first()
        resume_id = _make_resume(user.id)

    body = {**CONTEXT_BODY, "resume_id": resume_id}
    r = client.post("/interview/context", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["resume_id"] == resume_id


def test_create_context_rejects_someone_elses_resume(client):
    r1 = client.post("/auth/register", json={"username": "ctx_owner", "password": "secret123"})
    owner_headers = {"Authorization": f"Bearer {r1.json()['access_token']}"}

    with SessionLocal() as db:
        from app.core.models import User

        owner = db.query(User).filter_by(username="ctx_owner").first()
        resume_id = _make_resume(owner.id)

    r2 = client.post("/auth/register", json={"username": "ctx_intruder", "password": "secret123"})
    intruder_headers = {"Authorization": f"Bearer {r2.json()['access_token']}"}

    body = {**CONTEXT_BODY, "resume_id": resume_id}
    r = client.post("/interview/context", json=body, headers=intruder_headers)
    assert r.status_code == 400

    # Sanity: the owner can use their own resume fine.
    r = client.post("/interview/context", json=body, headers=owner_headers)
    assert r.status_code == 200


def test_get_context_is_private(client):
    headers = _register(client, "ctx_owner_2")
    created = client.post("/interview/context", json=CONTEXT_BODY, headers=headers).json()

    r = client.get(f"/interview/context/{created['context_id']}", headers=headers)
    assert r.status_code == 200
    assert r.json()["context_id"] == created["context_id"]

    other_headers = _register(client, "ctx_stranger")
    r = client.get(f"/interview/context/{created['context_id']}", headers=other_headers)
    assert r.status_code == 404


def test_rejects_invalid_interview_type(client):
    headers = _register(client, "ctx_user_invalid")
    body = {**CONTEXT_BODY, "interview_type": "not_a_real_type"}

    r = client.post("/interview/context", json=body, headers=headers)
    assert r.status_code == 422
