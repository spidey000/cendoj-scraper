"""SQLAlchemy models for the Cendoj scraper database."""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

Base = declarative_base()


classCollection(Base):
    """Represents a collection of sentences (e.g., a year or court)."""
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    url = Column(String, nullable=False)
    total_sentences = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sentences = relationship("Sentence", back_populates="collection")


class Sentence(Base):
    """Represents a single court sentence."""
    __tablename__ = "sentences"

    id = Column(Integer, primary_key=True)
    cendoj_id = Column(String, nullable=False, unique=True)  # Official Cendoj identifier
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    pdf_url = Column(String, nullable=False)
    court = Column(String, nullable=False)
    date = Column(String)  # Could be parsed to datetime if consistent format
    summary = Column(Text)
    pdf_path = Column(String)  # Local path to downloaded PDF
    collection_name = Column(String, ForeignKey("collections.name"))
    downloaded = Column(Boolean, default=False)
    download_attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    collection = relationship("Collection", back_populates="sentences")


class DownloadLog(Base):
    """Logs download attempts and outcomes for auditing/resilience."""
    __tablename__ = "download_logs"

    id = Column(Integer, primary_key=True)
    sentence_id = Column(String, nullable=False)
    url = Column(String, nullable=False)
    success = Column(Boolean, default=False)
    error_message = Column(Text)
    attempts = Column(Integer, default=1)
    downloaded_at = Column(DateTime, default=datetime.utcnow)
