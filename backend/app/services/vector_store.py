import faiss
import numpy as np
import pickle
import os

VECTOR_DB_DIR = "app/vector_db"

os.makedirs(VECTOR_DB_DIR, exist_ok=True)

INDEX_PATH = os.path.join(VECTOR_DB_DIR, "faiss.index")
METADATA_PATH = os.path.join(VECTOR_DB_DIR, "metadata.pkl")


def save_to_faiss(embeddings, chunks):
    """
    Append embeddings and metadata to the existing FAISS index, creating
    it if this is the first upload.
    """

    dimension = embeddings.shape[1]

    if os.path.exists(INDEX_PATH) and os.path.exists(METADATA_PATH):
        index = faiss.read_index(INDEX_PATH)

        with open(METADATA_PATH, "rb") as f:
            metadata = pickle.load(f)
    else:
        index = faiss.IndexFlatIP(dimension)
        metadata = []

    index.add(np.array(embeddings, dtype=np.float32))

    metadata.extend(chunks)

    faiss.write_index(index, INDEX_PATH)

    with open(METADATA_PATH, "wb") as f:
        pickle.dump(metadata, f)

    return len(metadata)