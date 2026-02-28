"""Database engine and session management."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cendoj.storage.schemas import Base

# Global variables (initialized in init_db)
_engine = None
_SessionLocal = None


def init_db(db_path: str = "data/cendoj.db"):
    """Initialize database engine and create tables."""
    global _engine, _SessionLocal

    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # SQLite database URL
    database_url = f"sqlite:///{db_path}"

    # Create engine
    _engine = create_engine(
        database_url,
        echo=False,  # Set True for SQL logging
        connect_args={"check_same_thread": False}  # Allow multithreading
    )

    # Create session factory
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    # Create tables
    Base.metadata.create_all(bind=_engine)

    return _engine


def get_session():
    """Get a new database session."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()


def get_engine():
    """Get the database engine."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine
