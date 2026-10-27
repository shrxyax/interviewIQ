"""
Resume search stays within one resume (the FAISS index is shared by every
upload), and chat still answers from the resume when the LLM is down.
No model is loaded: embeddings are faked with fixed vectors.
"""

import faiss
import numpy as np
import pickle
import pytest
from fastapi.testclient import TestClient

from app.api import chat
from app.main import app
from app.services import retriever


def _unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def shared_index(tmp_path, monkeypatch):
    chunks = [
        {"text": "Alice: React developer at Acme.", "filename": "alice.pdf", "page": 1, "resume_id": 1},
        {"text": "Bob: Java backend engineer.", "filename": "bob.pdf", "page": 1, "resume_id": 2},
        {"text": "Bob: Java backend engineer.", "filename": "bob.pdf", "page": 1, "resume_id": 2},
        {"text": "Old upload of Alice without a tag.", "filename": "alice.pdf", "page": 2},
    ]
    vectors = np.stack([_unit(1, 0.1), _unit(1, 0), _unit(1, 0), _unit(0.9, 0.3)])

    index = faiss.IndexFlatIP(2)
    index.add(vectors)
    faiss.write_index(index, str(tmp_path / "faiss.index"))
    with open(tmp_path / "metadata.pkl", "wb") as f:
        pickle.dump(chunks, f)

    monkeypatch.setattr(retriever, "INDEX_PATH", str(tmp_path / "faiss.index"))
    monkeypatch.setattr(retriever, "METADATA_PATH", str(tmp_path / "metadata.pkl"))
    monkeypatch.setattr(retriever, "generate_embeddings", lambda texts: np.stack([_unit(1, 0)]))


def test_retrieval_only_returns_the_requested_resume(shared_index):
    texts = [c["text"] for c in retriever.retrieve("experience", k=5, resume_id=1, filename="alice.pdf")]

    assert texts == ["Alice: React developer at Acme.", "Old upload of Alice without a tag."]


def test_duplicate_chunks_from_re_uploads_are_returned_once(shared_index):
    texts = [c["text"] for c in retriever.retrieve("experience", k=5, resume_id=2, filename="bob.pdf")]

    assert texts == ["Bob: Java backend engineer."]


# --------------------------------------------------------------------------
# /chat
# --------------------------------------------------------------------------

CHUNKS = [
    {
        "text": "EXPERIENCE\n• Research Intern at DRDO, implemented the ChaCha20 cipher in\nPython and verified it.\n"
        "EDUCATION\n• B.Tech in Computer Science at VIT Vellore",
        "filename": "me.pdf",
        "page": 1,
        "score": 0.6,
    }
]


class _Resume:
    id = 7
    filename = "me.pdf"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(chat, "latest_resume", lambda db, user_id: _Resume())
    monkeypatch.setattr(chat, "retrieve", lambda question, k=5, resume_id=None, filename=None, min_score=0.35: CHUNKS)

    def fake_embed(texts):
        # The query is most similar to lines mentioning "intern".
        return np.stack([_unit(1, 0)] + [_unit(1, 0) if "Intern" in t else _unit(0, 1) for t in texts[1:]])

    monkeypatch.setattr(chat, "generate_embeddings", fake_embed)

    with TestClient(app) as c:
        yield c


def test_chat_answers_from_the_resume_when_the_llm_is_unavailable(client, monkeypatch):
    def quota_exhausted(*args, **kwargs):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(chat, "generate_text", quota_exhausted)

    r = client.post("/chat", json={"question": "What internships have I done?"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fallback"] is True
    assert "AI model is unavailable" in body["answer"]
    # The PDF's wrapped line is rejoined into one bullet.
    assert "- **Experience:** Research Intern at DRDO, implemented the ChaCha20 cipher in Python and verified it." in body["answer"]
    assert "B.Tech" not in body["answer"]


def test_chat_uses_the_llm_answer_when_available(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", lambda prompt, task: "You interned at DRDO.")

    body = client.post("/chat", json={"question": "Internships?"}).json()

    assert body == {"answer": "You interned at DRDO.", "sources": [{"filename": "me.pdf", "page": 1, "score": 0.6}], "fallback": False}


def test_chat_without_a_resume_says_to_upload_one(client, monkeypatch):
    monkeypatch.setattr(chat, "latest_resume", lambda db, user_id: None)

    r = client.post("/chat", json={"question": "Anything?"})

    assert r.status_code == 409
    assert "Upload your resume" in r.json()["detail"]


def test_fallback_prefers_the_section_the_question_asks_about(monkeypatch):
    # Equal embedding scores everywhere: only the section hint decides.
    monkeypatch.setattr(chat, "generate_embeddings", lambda texts: np.stack([_unit(1, 0)] * len(texts)))

    excerpts = chat._resume_excerpts("Where did I study?", CHUNKS, limit=1)

    assert excerpts == [("Education", "B.Tech in Computer Science at VIT Vellore")]


def test_chat_sends_recent_history_and_allows_general_questions(client, monkeypatch):
    prompts = []
    monkeypatch.setattr(chat, "generate_text", lambda prompt, task: prompts.append(prompt) or "ok")

    history = [{"role": "user", "content": f"Old question {i}"} for i in range(12)]
    history.append({"role": "assistant", "content": "A deadlock is a circular wait."})

    r = client.post("/chat", json={"question": "Give me an example of that", "history": history})

    assert r.status_code == 200, r.text
    prompt = prompts[0]
    assert "Assistant: A deadlock is a circular wait." in prompt
    assert "Old question 11" in prompt and "Old question 4" not in prompt  # only the last 8 turns
    assert "Candidate: Give me an example of that" in prompt
    # General questions are answered, not refused for being outside the resume.
    assert "Answer ONLY using the context" not in prompt
    assert "answer from your own knowledge" in prompt
