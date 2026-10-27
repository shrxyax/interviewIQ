import faiss
import pickle
import numpy as np

from app.core.models import Resume
from app.services.embeddings import generate_embeddings

INDEX_PATH = "app/vector_db/faiss.index"
METADATA_PATH = "app/vector_db/metadata.pkl"

MIN_SCORE = 0.35


def latest_resume(db, user_id: int) -> Resume | None:
    """The user's most recently uploaded resume, if any."""

    return db.query(Resume).filter_by(user_id=user_id).order_by(Resume.id.desc()).first()


def _belongs(chunk: dict, resume_id: int, filename: str | None) -> bool:
    if "resume_id" in chunk:
        return chunk["resume_id"] == resume_id

    # Chunks indexed before uploads were tagged with their resume.
    return filename is not None and chunk.get("filename") == filename


def retrieve(
    query: str,
    k: int = 5,
    resume_id: int | None = None,
    filename: str | None = None,
    min_score: float = MIN_SCORE,
):
    """
    Retrieve the top-k chunks most relevant to `query`.

    The index is shared by every upload, so pass the resume to search
    (`resume_id`, plus its `filename` to match chunks indexed before
    uploads were tagged); without it every resume is searched.
    """

    # Load FAISS index
    index = faiss.read_index(INDEX_PATH)

    # Load chunk metadata
    with open(METADATA_PATH, "rb") as f:
        metadata = pickle.load(f)

    # Convert question into embedding. bge-small expects queries to carry
    # this instruction prefix (not used for the stored passages) to get
    # scores comparable to the passage embeddings.
    query_embedding = generate_embeddings(
        [f"Represent this sentence for searching relevant passages: {query}"]
    )

    # Filtering happens after the search, so rank everything (the index
    # holds a few resumes' worth of chunks; exact search over it is cheap).
    scores, indices = index.search(
        np.array(query_embedding, dtype=np.float32),
        index.ntotal if resume_id is not None else k,
    )

    results = []
    seen_texts = set()

    for score, idx in zip(scores[0], indices[0]):

        if idx == -1 or score < min_score:
            continue

        chunk = metadata[idx]

        if resume_id is not None and not _belongs(chunk, resume_id, filename):
            continue

        # The same file uploaded twice is indexed twice.
        if chunk["text"] in seen_texts:
            continue
        seen_texts.add(chunk["text"])

        chunk = chunk.copy()
        chunk["score"] = float(score)
        results.append(chunk)

        if len(results) == k:
            break

    return results
