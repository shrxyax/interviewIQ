"""
Phrases one interviewer question grounded in the top unresolved finding.
The LLM receives only the finding's structured facts, never asked to
invent or judge the design itself; it only puts the finding into words.
"""

from app.modules.whiteboard.findings import Finding


_PROMPT = """You are a system-design interviewer. A candidate's design was just
analysed by an automated engine (queueing theory + graph analysis), which
found this specific, measured problem:

Finding type: {type}
Component: {node_label}
Metric: {metric} = {value} (threshold: {threshold})
Plain description: {message}

Ask the candidate ONE short, natural interview question that surfaces this
exact problem and invites them to respond to it. Do not restate the raw
numbers mechanically; speak like a real interviewer would. Do not suggest
a solution. Output ONLY the question.
"""


def grounded_question(finding: Finding, node_label: str | None) -> str:
    prompt = _PROMPT.format(
        type=finding.type,
        node_label=node_label or finding.node_id or "the system",
        metric=finding.metric,
        value=finding.value,
        threshold=finding.threshold,
        message=finding.message,
    )

    try:
        from app.core.llm_gateway import generate_text

        text = generate_text(prompt, task="whiteboard_question", temperature=0.6).strip()
        if text:
            return text
    except Exception as exc:
        print(f"Grounded question generation failed, using fallback: {exc}")

    return finding.message + " What would you change?"
