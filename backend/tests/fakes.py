import numpy as np

from app.modules.mkt.consistency import (
    CONTRADICTED,
    NOT_ADDRESSED,
    SUPPORTED,
    Verdict,
    Verification,
    split_propositions,
)


class SubstringVerifier:
    """
    Deterministic stand-in for the LLM/NLI verifier:
    a statement is SUPPORTED if it appears verbatim in the answer and
    CONTRADICTED if the answer contains "NOT <statement>".
    """

    name = "fake"

    def verify(self, question, answer, statements):
        lower = answer.lower()
        verdicts = {}

        for s in statements:
            key = s.lower()

            if f"not {key}" in lower:
                verdicts[s] = Verdict(CONTRADICTED, s, "fake")
            elif key in lower:
                verdicts[s] = Verdict(SUPPORTED, s, "fake")
            else:
                verdicts[s] = Verdict(NOT_ADDRESSED)

        return Verification(split_propositions(answer), verdicts)


def fake_embed(texts):
    """
    Bag-of-characters embedding: identical texts get similarity 1.
    """

    vecs = []

    for t in texts:
        v = np.zeros(64)
        for ch in t.lower():
            v[ord(ch) % 64] += 1
        norm = np.linalg.norm(v)
        vecs.append(v / norm if norm else v)

    return np.asarray(vecs)
