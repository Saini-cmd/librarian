import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://librarian:librarian@localhost:5432/librarian",
)

# Pool sizing is env-tunable (DB_POOL_SIZE / DB_MAX_OVERFLOW) so a busier
# multi-user deployment can raise the ceiling without a code change. Pipelines
# never hold a connection across their whole run (the session is opened only
# for the finalize step), so steady-state usage is short-lived connections.
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from core import models  # noqa: F401  register models with Base

    Base.metadata.create_all(bind=engine)
