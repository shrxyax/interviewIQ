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
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

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
