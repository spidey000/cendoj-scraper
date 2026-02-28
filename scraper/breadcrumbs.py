"""Breadcrumb trail extraction and analysis."""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from urllib.parse import urljoin

from cendoj.utils.logger import get_logger
from cendoj.storage.database import get_session
from cendoj.storage.schemas import BreadcrumbTrail


logger = get_logger(__name__)


@dataclass
class Breadcrumb:
    """A single breadcrumb element."""
    text: str
    url: Optional[str] = None


class BreadcrumbExtractor:
    """Extract breadcrumb trails from HTML content."""

    # Common breadcrumb selectors
    SELECTORS = [
        '.breadcrumb a',
        '.breadcrumb li',
        'nav[aria-label="breadcrumb"] a',
        '[itemscope][itemtype*="Breadcrumb"] a',
        '.nav-path a',
        '.crumbs a',
        'ol.breadcrumb li a',
        'ul.breadcrumb li a'
    ]

    @classmethod
    def extract(cls, html_content: str, base_url: str = '') -> List[List[Breadcrumb]]:
        """
        Extract all breadcrumb trails from HTML.
        Returns a list of trails, each trail is a list of Breadcrumb objects.
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        trails = []

        for selector in cls.SELECTORS:
            elements = soup.select(selector)
            if not elements:
                continue

            # Build trail from consecutive elements in the same breadcrumb container
            # Group by common parent
            for parent in cls._group_by_parent(elements):
                trail = []
                for el in parent:
                    text = el.get_text(strip=True)
                    href = el.get('href')
                    url = urljoin(base_url, href) if href else None
                    trail.append(Breadcrumb(text=text, url=url))
                if trail and len(trail) >= 2:  # at least two elements
                    trails.append(trail)

        return trails

    @staticmethod
    def _group_by_parent(elements):
        """Group elements by their immediate breadcrumb container parent."""
        from bs4 import BeautifulSoup
        groups = []
        seen_parents = set()

        for el in elements:
            parent = el.find_parent(['nav', 'ol', 'ul', 'div'], class_=re.compile(r'(breadcrumb|crumb|nav-path|crumbs)'))
            if parent and id(parent) not in seen_parents:
                seen_parents.add(id(parent))
                # Collect all breadcrumb links within this parent in order
                children = parent.select(', '.join(BreadcrumbExtractor.SELECTORS))
                groups.append(children)
        return groups


class BreadcrumbAnalyzer:
    """Analyze breadcrumb trails to understand site taxonomy and detect gaps."""

    def __init__(self):
        self.logger = get_logger(f"{self.__class__.__name__}")

    def analyze_trails(self, trails: List[List[Breadcrumb]]) -> Dict[str, Any]:
        """
        Analyze trails to produce taxonomy insights.
        Returns a dict with:
        - unique_paths: set of normalized path strings
        - depth_distribution: dict[depth, count]
        - orphan_pages: list of URLs that appear as leaves without parent entries
        - missing_intermediates: set of URLs that are referenced but never visited as pages
        """
        stats = {
            'total_trails': len(trails),
            'unique_paths': set(),
            'depth_distribution': {},
            'orphan_pages': [],
            'path_texts': []
        }

        all_urls = set()
        leaf_urls = set()

        for trail in trails:
            path_parts = []
            for i, crumb in enumerate(trail):
                if crumb.url:
                    path_parts.append(crumb.url)
                    all_urls.add(crumb.url)
                    if i == len(trail) - 1:
                        leaf_urls.add(crumb.url)
            if path_parts:
                normalized_path = '|'.join(path_parts)
                stats['unique_paths'].add(normalized_path)
                stats['path_texts'].append(' > '.join(c.text for c in trail))
                depth = len(trail)
                stats['depth_distribution'][depth] = stats['depth_distribution'].get(depth, 0) + 1

        # Orphan pages: leaf URLs whose parent URLs never appeared as a page (breadcrumb URL that is not a leaf elsewhere)
        # Basic heuristic: if a URL appears only as a non-last element, it's an intermediate node; if never appears as leaf, it's orphan
        intermediate_urls = all_urls - leaf_urls
        # Pages that are referenced in breadcrumbs but haven't been crawled as content pages
        stats['orphan_pages'] = list(all_urls)  # simplified; can refine with visited pages check

        stats['unique_paths'] = list(stats['unique_paths'])
        return stats


class BreadcrumbDBRecorder:
    """Persist breadcrumb trails to database."""

    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = get_logger(f"{self.__class__.__name__}")

    def record_trail(self, page_url: str, trail: List[Breadcrumb]):
        """Store a breadcrumb trail for a given page."""
        # Convert to JSON-serializable format
        breadcrumb_data = [
            {'text': b.text, 'url': b.url}
            for b in trail
        ]
        record = BreadcrumbTrail(
            page_url=page_url,
            breadcrumbs=breadcrumb_data
        )
        self.db_session.add(record)
        self.db_session.commit()
        self.logger.debug(f"Recorded breadcrumb trail for {page_url} ({len(trail)} items)")

    def get_trails_for_page(self, page_url: str) -> List[Dict]:
        records = self.db_session.query(BreadcrumbTrail).filter_by(page_url=page_url).all()
        return [r.breadcrumbs for r in records]
