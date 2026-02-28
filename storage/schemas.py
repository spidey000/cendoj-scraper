"""SQLAlchemy models for the Cendoj scraper database."""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json

Base = declarative_base()


class Collection(Base):
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


# ========== DISCOVERY TABLES ==========

class PDFLink(Base):
    """Represents a discovered PDF link."""
    __tablename__ = "pdf_links"

    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)  # original URL as discovered
    normalized_url = Column(String, nullable=False)  # normalized (lowercase, no query params)
    source_url = Column(String)  # page where this link was found
    discovery_session_id = Column(String, ForeignKey("discovery_sessions.id"))
    discovered_at = Column(DateTime, default=datetime.utcnow)
    validated_at = Column(DateTime)
    status = Column(String, default="discovered")  # discovered|validated|accessible|broken|blocked|downloaded
    http_status = Column(Integer)  # from HEAD request
    content_type = Column(String)
    content_length = Column(Integer)
    final_url = Column(String)  # after redirects
    redirect_count = Column(Integer, default=0)
    validation_error = Column(Text)
    attempts = Column(Integer, default=0)
    last_accessed = Column(DateTime)
    extraction_method = Column(String)  # css|xpath|deep_crawl|sitemap|regex|script_scan
    extraction_confidence = Column(Float, default=1.0)  # 0-1 confidence score
    metadata = Column(JSON)  # {"depth": 2, "site_key": "cendoj", "collection": "..."}

    __table_args__ = (
        Index('idx_pdf_links_normalized_url', 'normalized_url', unique=True),
        Index('idx_pdf_links_discovery_session', 'discovery_session_id'),
        Index('idx_pdf_links_status', 'status'),
        Index('idx_pdf_links_discovered_at', 'discovered_at'),
    )


class DiscoverySession(Base):
    """Tracks a discovery/scraping session."""
    __tablename__ = "discovery_sessions"

    id = Column(String, primary_key=True)  # UUID
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    mode = Column(String)  # shallow|deep|full
    max_depth = Column(Integer, default=0)  # 0 = unlimited
    total_pages_visited = Column(Integer, default=0)
    total_links_found = Column(Integer, default=0)
    new_links = Column(Integer, default=0)
    duplicates_skipped = Column(Integer, default=0)
    status = Column(String, default="running")  # running|completed|failed|interrupted|cancelled
    interrupted_at = Column(JSON)  # {"current_url": "...", "queue_size": 123, "depth": 2}
    config_snapshot = Column(JSON)  # config used
    proxy_used = Column(String)  # last proxy
    user_agent = Column(String)  # last UA
    errors = Column(Integer, default=0)
    validation_accessible = Column(Integer, default=0)
    validation_broken = Column(Integer, default=0)
    validation_blocked = Column(Integer, default=0)

    __table_args__ = (
        Index('idx_discovery_sessions_status', 'status'),
        Index('idx_discovery_sessions_start_time', 'start_time'),
    )


class ProxyHealth(Base):
    """Tracks health metrics for each proxy."""
    __tablename__ = "proxy_health"

    proxy_url = Column(String, primary_key=True)  # "http://ip:port"
    source = Column(String)  # "proxifly", "proxyscraper", etc.
    protocol = Column(String)  # http, https, socks4, socks5
    ip = Column(String)
    port = Column(Integer)
    country = Column(String(2))  # ISO code
    anonymity = Column(String)  # elite|anonymous|transparent
    https = Column(Boolean, default=False)
    total_requests = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    avg_response_time = Column(Float)  # seconds
    last_used = Column(DateTime)
    last_success = Column(DateTime)
    last_error = Column(DateTime)
    last_error_msg = Column(Text)
    is_healthy = Column(Boolean, default=True)
    score = Column(Float, default=50.0)  # 0-100
    last_check = Column(DateTime)

    __table_args__ = (
        Index('idx_proxy_health_score', 'score'),
        Index('idx_proxy_health_healthy', 'is_healthy'),
        Index('idx_proxy_health_source', 'source'),
    )
