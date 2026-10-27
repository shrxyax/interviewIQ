from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


# SQLite allows one writer at a time. An interview answer can hold the write
# lock while it waits on the LLM, so other requests wait up to 30s for it
# (the driver's default of 5s led to "database is locked" errors).
connect_args = (
    {"check_same_thread": False, "timeout": 30}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(settings.database_url, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """
    FastAPI dependency: one database session per request.
    """

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Create all tables. Model modules must be imported first so
    their tables are registered on Base.metadata.
    """

    import app.core.models  # noqa: F401
    import app.modules.aptitude.models  # noqa: F401
    import app.modules.coding.models  # noqa: F401
    import app.modules.content.models  # noqa: F401
    import app.modules.interview.models  # noqa: F401
    import app.modules.mkt.models  # noqa: F401
    import app.modules.whiteboard.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
