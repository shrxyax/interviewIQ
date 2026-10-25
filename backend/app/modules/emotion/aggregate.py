"""
Phase 9b: emotion/affect signal aggregation for the final report.

Detection itself runs entirely client-side in the browser via MediaPipe's
FaceLandmarker (see frontend1/src/services/faceDetection.js) - this module
never touches a video frame or calls MediaPipe. The frontend already reduces
raw blendshapes into three explainable 0-1 proxies (engagement, stress_proxy,
positive_expression_proxy) per turn and sends only that small JSON along with
the answer; this module just averages what it's handed across a session.

These are heuristic proxies derived from facial-blendshape intensities, not a
clinical emotion classifier - framed that way in the final report too.
"""

PROXY_KEYS = ("engagement", "stress_proxy", "positive_expression_proxy")


def aggregate_session_emotion(turns: list) -> dict:
    """
    turns is a list of InterviewTurn rows (or any object exposing a
    .emotion_metrics attribute) that may or may not have emotion_metrics set
    (None when the camera was unavailable/denied for that turn).
    """

    samples = [t.emotion_metrics for t in turns if getattr(t, "emotion_metrics", None)]

    if not samples:
        return {"sample_count": 0, **{f"avg_{key}": None for key in PROXY_KEYS}}

    result = {"sample_count": len(samples)}

    for key in PROXY_KEYS:
        values = [s[key] for s in samples if s.get(key) is not None]
        result[f"avg_{key}"] = round(sum(values) / len(values), 4) if values else None

    return result
