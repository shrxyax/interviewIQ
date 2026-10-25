from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
import os
import shutil
from sqlalchemy.orm import Session

from app.core.auth import get_user_or_guest
from app.core.db import get_db
from app.core.models import Resume, User
from app.services.pdf_loader import extract_pdf_text
from app.services.chunker import chunk_pages
from app.services.embeddings import generate_embeddings
from app.services.vector_store import save_to_faiss

router = APIRouter()

UPLOAD_DIR = "app/uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
):
    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed."
        )

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    # Save uploaded file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Step 1: Extract text
    pages = extract_pdf_text(file_path)

    # Step 2: Chunk pages
    chunks = chunk_pages(pages)

    

    texts = [chunk["text"] for chunk in chunks]

    embeddings = generate_embeddings(texts)

    print("Embedding shape:", embeddings.shape)

    stored = save_to_faiss(embeddings, chunks)

    resume = Resume(
        user_id=user.id,
        filename=file.filename,
        pages=len(pages),
        chunks=len(chunks),
    )
    db.add(resume)
    db.commit()

    return {
        "message": "Upload successful",
        "filename": file.filename,
        "resume_id": resume.id,
        "pages": len(pages),
        "chunks": len(chunks),
        "all_chunks": chunks,
        "embedding_shape": list(embeddings.shape),
        "stored_vectors": stored
    }