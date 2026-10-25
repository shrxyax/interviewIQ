from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


connect_args = (
    {"check_same_thread": False}
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
