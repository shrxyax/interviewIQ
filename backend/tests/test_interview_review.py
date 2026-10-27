"""
The built-in reviewer that scores answers and writes the report when the LLM
is unavailable. No embedder is passed, so relevance uses keyword overlap
and no model is loaded.
"""

from app.modules.interview import review


QUESTION = "What is the difference between a process and a thread?"
STRONG = (
    "A process is an independent program with its own memory, whereas a thread runs inside a process and "
    "shares its memory. Because threads share memory, switching between them is cheaper, but they need locks. "
    "For example, my chat server used a thread pool for requests."
)
WEAK = "Umm I like basically made a website and I think it was like nice maybe."


def test_a_strong_answer_outscores_a_weak_one_with_specific_feedback():
    strong = review.review_answer(QUESTION, STRONG, "technical")
    weak = review.review_answer(QUESTION, WEAK, "technical")

    assert strong.score >= 8
    assert weak.score <= 3
    assert "What worked" in strong.text
    assert "drifts" in weak.text


def test_a_few_words_are_too_short_to_evaluate():
    result = review.review_answer(QUESTION, "threads share memory", "technical")

    assert result.score == 1
    assert "too short" in result.text


def test_story_questions_are_checked_for_star_structure():
    result = review.review_answer(
        "Tell me about a time you disagreed with a teammate.",
        "We disagreed about the database for a project and talked about it for a while with the whole team there.",
        "hr",
    )

    assert "STAR" in result.text


def test_report_has_real_scores_and_feedback():
    history = [
        {"question": QUESTION, "answer": STRONG, "score": None},
        {"question": QUESTION, "answer": WEAK, "score": None},
    ]

    report = review.build_report("technical", "Backend Engineer", history)

    assert 0 < report["overall_score"] < 100
    assert report["strengths"] and report["areas_for_improvement"]
    assert "question 1" in report["final_feedback"] and "question 2" in report["final_feedback"]


def test_mkt_feedback_names_covered_and_missing_points():
    spec = {"must_entail": ["Big-O describes growth", "Constant factors are ignored"]}
    assessment = {
        "verdicts": {"Big-O describes growth": {"label": "supported"}},
        "misconceptions_hit": ["Big-O gives the exact running time"],
    }

    text = review.mkt_feedback("Big-O notation", "base", "partial", spec, assessment)

    assert "You covered: Big-O describes growth" in text
    assert "Missing: Constant factors are ignored" in text
    assert "misconception" in text
