from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    settings.DATABASE_URL,
    **{"connect_args": {"check_same_thread": False}} if _is_sqlite else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
