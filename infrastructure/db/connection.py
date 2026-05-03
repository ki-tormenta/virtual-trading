from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    _connect_args: dict = {"check_same_thread": False}
else:
    # Supabase / PostgreSQL は SSL 必須
    _connect_args = {"sslmode": "require"}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
