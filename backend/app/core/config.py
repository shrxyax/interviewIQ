import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings:
    """
    Central configuration, read once from environment variables.
    Every value has a development default so the app runs locally
    with only GEMINI_API_KEY set.
    """

    # SQLite for development. Swap for PostgreSQL in production, e.g.
    # postgresql+psycopg://user:pass@localhost/interviewiq
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BACKEND_DIR / 'interviewiq.db').as_posix()}",
    )

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    # Text models, tried in order: each has its own free-tier daily quota,
    # so when one runs out requests move on to the next instead of failing.
    gemini_models: list[str] = [
        m.strip()
        for m in os.getenv(
            "GEMINI_MODELS",
            f"{os.getenv('GEMINI_MODEL', 'gemini-3.5-flash')},gemini-3.5-flash-lite",
        ).split(",")
        if m.strip()
    ]
    gemini_model: str = gemini_models[0]
    # Voice for reading interview questions aloud (browser speech is
    # unreliable on some systems, so the backend renders real audio).
    # Tried in order; each has its own (small) free-tier daily quota.
    gemini_tts_models: list[str] = [
        m.strip()
        for m in os.getenv("GEMINI_TTS_MODELS", "gemini-3.8-flash-lite-tts,gemini-3.8-flash-tts").split(",")
        if m.strip()
    ]
    gemini_tts_voice: str = os.getenv("GEMINI_TTS_VOICE", "Charon")
    # Voice for the offline fallback (macOS `say -v`); empty = system default.
    local_tts_voice: str = os.getenv("LOCAL_TTS_VOICE", "Samantha")

    jwt_secret: str = os.getenv("JWT_SECRET", "dev-only-change-me")
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = int(os.getenv("JWT_EXPIRY_MINUTES", "10080"))

    # Small NLI cross-encoder; runs on CPU. Use
    # cross-encoder/nli-deberta-v3-base for higher accuracy.
    nli_model: str = os.getenv(
        "NLI_MODEL",
        "cross-encoder/nli-deberta-v3-xsmall",
    )


settings = Settings()
