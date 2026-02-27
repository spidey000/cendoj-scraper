"""Data models for Cendoj scraper."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Sentence:
    """Represents a court sentence."""
    id: str
    cendoj_number: str
    court: str
    date: datetime
    pdf_url: str
    file_path: Optional[str] = None
    checksum: Optional[str] = None
    downloaded_at: Optional[datetime] = None
    metadata: dict = None

@dataclass
class Collection:
    """Represents a Cendoj collection."""
    id: str
    name: str
    description: str
    year: int
    url_pattern: str
    last_updated: Optional[datetime] = None

@dataclass
class DownloadResult:
    """Result of a download operation."""
    sentence_id: str
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None
    duration: Optional[float] = None