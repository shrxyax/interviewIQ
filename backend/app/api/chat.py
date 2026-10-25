from fastapi import APIRouter
from pydantic import BaseModel

from app.services.retriever import retrieve
from app.services.prompt import build_prompt
from app.core.llm_gateway import generate_text

router = APIRouter()


class ChatRequest(BaseModel):
    question: str


@router.post("/chat")
def chat(request: ChatRequest):

    # Retrieve relevant chunks
    chunks = retrieve(request.question)

    # Build prompt
    prompt = build_prompt(request.question, chunks)

    # Ask Gemini
    answer = generate_text(prompt, task="chat")

    sources = []

    for chunk in chunks:

        sources.append(
            {
                "filename": chunk["filename"],
                "page": chunk["page"],
                "score": round(chunk["score"], 3)
            }
        )

    return {
        "answer": answer,
        "sources": sources
    }