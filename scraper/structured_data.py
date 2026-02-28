"""Structured data extraction from HTML (JSON-LD, Microdata, RDFa)."""

from __future__ import annotations

import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from cendoj.utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class StructuredData:
    """Represents extracted structured data."""
    type: str  # json-ld, microdata, rdfa
    data: Dict[str, Any]
    raw: str
    source_url: str


class StructuredDataExtractor:
    """Extract JSON-LD, Microdata, and RDFa from HTML pages."""

    # Known schema types that typically contain document links
    RELEVANT_SCHEMA_TYPES = {
        'LegalService', 'GovernmentOrganization', 'WebPage', 'Article',
        'NewsArticle', 'LegalArticle', 'Court', 'Organization',
    }

    @classmethod
    def extract(cls, html: str, source_url: str = '') -> List[StructuredData]:
        """Extract all structured data from HTML."""
        results = []
        
        # JSON-LD
        results.extend(cls._extract_jsonld(html, source_url))
        
        # Microdata
        results.extend(cls._extract_microdata(html, source_url))
        
        return results

    @classmethod
    def _extract_jsonld(cls, html: str, source_url: str) -> List[StructuredData]:
        """Extract JSON-LD scripts."""
        results = []
        pattern = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
        
        for match in pattern.finditer(html):
            try:
                data = json.loads(match.group(1))
                results.append(StructuredData(
                    type='json-ld',
                    data=data,
                    raw=match.group(1),
                    source_url=source_url,
                ))
            except json.JSONDecodeError as e:
                logger.debug(f"JSON-LD parse error: {e}")
        
        return results

    @classmethod
    def _extract_microdata(cls, html: str, source_url: str) -> List[StructuredData]:
        """Extract Microdata attributes."""
        from bs4 import BeautifulSoup
        results = []
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find elements with itemtype
        for element in soup.find_all(attrs={'itemtype': True}):
            item_type = element.get('itemtype', '')
            # Extract itemprops
            item_data = {}
            for prop in element.find_all(attrs={'itemprop': True}):
                prop_name = prop.get('itemprop')
                prop_value = prop.get_text(strip=True)
                item_data[prop_name] = prop_value
            
            if item_data:
                results.append(StructuredData(
                    type='microdata',
                    data={'@type': item_type, **item_data},
                    raw=str(element),
                    source_url=source_url,
                ))
        
        return results

    @classmethod
    def extract_pdf_links(cls, structured_data: List[StructuredData]) -> List[str]:
        """Extract PDF URLs from structured data."""
        pdf_urls = []
        
        for sd in structured_data:
            urls = cls._extract_urls_from_dict(sd.data)
            pdf_urls.extend([u for u in urls if u.lower().endswith('.pdf')])
        
        return pdf_urls

    @classmethod
    def _extract_urls_from_dict(cls, obj: Any, seen: Optional[set] = None) -> List[str]:
        """Recursively extract URL strings from dict/list."""
        if seen is None:
            seen = set()
        
        urls = []
        
        if isinstance(obj, str):
            if obj.startswith(('http://', 'https://')) and obj not in seen:
                seen.add(obj)
                urls.append(obj)
        elif isinstance(obj, dict):
            for value in obj.values():
                urls.extend(cls._extract_urls_from_dict(value, seen))
        elif isinstance(obj, list):
            for item in obj:
                urls.extend(cls._extract_urls_from_dict(item, seen))
        
        return urls

    @classmethod
    def extract_relevant_data(cls, structured_data: List[StructuredData]) -> List[Dict[str, Any]]:
        """Extract relevant metadata (dates, court, case numbers) from structured data."""
        relevant = []
        
        for sd in structured_data:
            # Check if schema type is relevant
            schema_type = sd.data.get('@type')
            if schema_type and schema_type in cls.RELEVANT_SCHEMA_TYPES:
                relevant.append({
                    'type': sd.type,
                    'schema_type': schema_type,
                    'data': sd.data,
                    'source_url': sd.source_url,
                })
            # Also check nested @graph
            if '@graph' in sd.data:
                for item in sd.data['@graph']:
                    if isinstance(item, dict):
                        nested_type = item.get('@type')
                        if nested_type in cls.RELEVANT_SCHEMA_TYPES:
                            relevant.append({
                                'type': sd.type,
                                'schema_type': nested_type,
                                'data': item,
                                'source_url': sd.source_url,
                            })
        
        return relevant


class StructuredDataStrategy:
    """Strategy wrapper for structured data extraction."""

    def __init__(self, config):
        self.config = config
        self._struct_config = getattr(config, 'structured_data_config', lambda: {})()
        self.logger = get_logger(self.__class__.__name__)

    @property
    def enabled(self) -> bool:
        return bool(self._struct_config.get('enabled', False))

    def extract_from_html(self, html: str, source_url: str = '') -> List[Dict[str, Any]]:
        """Extract structured data from HTML content."""
        if not self.enabled:
            return []
        
        structured = StructuredDataExtractor.extract(html, source_url)
        
        # Extract PDF links
        pdf_links = StructuredDataExtractor.extract_pdf_links(structured)
        
        # Extract relevant metadata
        relevant = StructuredDataExtractor.extract_relevant_data(structured)
        
        results = {
            'pdf_links': pdf_links,
            'metadata': relevant,
            'total_structured_items': len(structured),
        }
        
        self.logger.debug(f"Extracted {len(pdf_links)} PDF links and {len(relevant)} metadata items from {source_url}")
        
        return results
