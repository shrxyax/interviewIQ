import faiss
import pickle
import numpy as np

from app.services.embeddings import generate_embeddings

INDEX_PATH = "app/vector_db/faiss.index"
METADATA_PATH = "app/vector_db/metadata.pkl"


def retrieve(query: str, k: int = 5):
    """
    Retrieve top-k most relevant chunks.
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

    # Search
    scores, indices = index.search(
        np.array(query_embedding, dtype=np.float32),
        k
    )

    results = []

    for score, idx in zip(scores[0], indices[0]):

        if idx == -1:
            continue

        if score < 0.35:
            continue

        chunk = metadata[idx].copy()

        chunk["score"] = float(score)

        results.append(chunk)

    return results