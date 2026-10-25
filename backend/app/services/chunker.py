

def split_text(text: str, chunk_size: int = 500, overlap: int = 100):
    """
    Split a string into overlapping chunks.
    """

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunks.append(text[start:end])

        start += chunk_size - overlap

    return chunks

import re

HEADINGS = [
    "Education",
    "Technical Skills",
    "Experience",
    "Projects",
    "Certifications",
    "Campus Leadership"
]


def split_resume(text):
    """
    Split a resume into sections based on headings.
    """

    pattern = "|".join(re.escape(h) for h in HEADINGS)

    parts = re.split(f"({pattern})", text)

    chunks = []

    current = ""

    for part in parts:

        if part.strip() in HEADINGS:

            if current.strip():
                chunks.append(current.strip())

            current = part

        else:

            current += "\n" + part

    if current.strip():
        chunks.append(current.strip())

    return chunks


def chunk_pages(pages):
    """
    Convert PDF pages into chunks while preserving metadata.

    Returns:
    [
        {
            "chunk_id": 1,
            "filename": "...",
            "page": 1,
            "text": "..."
        }
    ]
    """

    all_chunks = []

    chunk_id = 1

    for page in pages:

        if "Projects" in page["text"] and "Education" in page["text"]:
            chunks = split_resume(page["text"])
        else:
            chunks = split_text(page["text"])


        for chunk in chunks:

            if chunk.strip() == "":
                continue

            all_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "filename": page["filename"],
                    "page": page["page"],
                    "text": chunk,
                }
            )

            chunk_id += 1

    return all_chunks