"""Pattern-based URL generation strategy."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import List, Dict, Any, Set, Tuple
from urllib.parse import urlparse

from cendoj.scraper.strategies.base import DiscoveryStrategy, StrategyResult
from cendoj.storage.database import get_session
from cendoj.storage.schemas import PDFLink, Sentence


class PatternGenerator(DiscoveryStrategy):
    """Generate missing URLs by filling gaps in sequential numeric patterns."""

    name = "pattern_generator"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get config (use same pattern as sitemap: config.pattern_generator_config)
        self._pattern_config = getattr(self.config, 'pattern_generator_config', lambda: {})()
        self._min_samples = int(self._pattern_config.get('min_samples', 100))
        self._include_patterns = [re.compile(p) for p in self._pattern_config.get('include_patterns', [])]
        self._exclude_patterns = [re.compile(p) for p in self._pattern_config.get('exclude_patterns', [])]
        self._max_urls = int(self._pattern_config.get('max_urls', 10000))

    @property
    def enabled(self) -> bool:
        return bool(self._pattern_config.get('enabled', False))

    async def initialize(self):
        pass

    async def discover(self) -> StrategyResult:
        result = StrategyResult(metadata={'strategy': self.name})
        if not self.enabled:
            return result

        # Load URLs from DB
        urls = await self._load_urls()
        if len(urls) < self._min_samples:
            self.logger.info(f"Need at least {self._min_samples} URLs, found {len(urls)}. Skipping pattern generator.")
            return result

        # Filter
        filtered = self._filter_urls(urls)
        self.logger.info(f"PatternGenerator analyzing {len(filtered)} URLs")

        # Generate missing URLs
        generated = await self._generate_missing(filtered)
        generated = generated[:self._max_urls]
        result.seed_urls.extend(generated)
        result.metadata['sample_count'] = len(filtered)
        result.metadata['generated_count'] = len(generated)
        return result

    async def cleanup(self):
        pass

    async def _load_urls(self) -> List[str]:
        """Load existing PDF URLs from database."""
        db_session = get_session()
        try:
            pdf_links = db_session.query(PDFLink).all()
            urls = [pl.url for pl in pdf_links if pl.url]
            sentences = db_session.query(Sentence).filter(Sentence.pdf_url.isnot(None)).all()
            for s in sentences:
                if s.pdf_url and s.pdf_url not in urls:
                    urls.append(s.pdf_url)
            return urls
        finally:
            db_session.close()

    def _filter_urls(self, urls: List[str]) -> List[str]:
        """Apply include/exclude filters."""
        if not urls:
            return []
        filtered = []
        for url in sorted(set(urls)):
            if self._exclude_patterns and any(p.search(url) for p in self._exclude_patterns):
                continue
            if self._include_patterns and not any(p.search(url) for p in self._include_patterns):
                continue
            filtered.append(url)
        return filtered

    async def _generate_missing(self, urls: List[str]) -> List[str]:
        """Perform pattern-based generation."""
        # Group by skeleton where sequence token is replaced by {SEQ}
        groups: Dict[str, List[Tuple[str, int, int, int]]] = defaultdict(list)
        # For each skeleton we store tuple: (original_url, seq_value, seq_start_offset, seq_width)
        for url in urls:
            parsed = urlparse(url)
            path = parsed.path
            if not path.lower().endswith('.pdf'):
                continue
            # Separate filename
            filename = path.rstrip('/').split('/')[-1]
            # Find numeric tokens in filename using regex to capture numbers
            matches = list(re.finditer(r'\d+', filename))
            if not matches:
                continue
            # The last match is candidate sequence
            last_match = matches[-1]
            seq_str = last_match.group()
            seq_value = int(seq_str)
            seq_start = last_match.start()
            seq_end = last_match.end()
            seq_width = seq_end - seq_start

            # Build skeleton: replace this numeric token with {SEQ} placeholder
            skeleton_filename = filename[:seq_start] + '{SEQ}' + filename[seq_end:]
            # Reconstruct skeleton path with placeholder
            path_parts = path.split('/')
            if path_parts:
                path_parts[-1] = skeleton_filename
                skeleton_path = '/'.join(path_parts)
            else:
                skeleton_path = skeleton_filename

            groups[skeleton_path].append((url, seq_value, seq_start, seq_width))

        generated_urls = []
        for skeleton, items in groups.items():
            if len(items) < 2:
                continue  # Need at least 2 to infer range

            seqs = [seq for _, seq, _, _ in items]
            min_seq = min(seqs)
            max_seq = max(seqs)
            # Use template from first item
            template_url, _, seq_start, width = items[0]
            existing_set = set(seqs)
            for seq in range(min_seq, max_seq + 1):
                if seq in existing_set:
                    continue
                # Maintain zero-padding if width suggests
                seq_str = f"{seq:0{width}d}"
                # Replace placeholder
                new_filename = skeleton.replace('{SEQ}', seq_str)
                # Reconstruct full URL
                parsed = urlparse(template_url)
                path_parts = parsed.path.split('/')
                if path_parts:
                    path_parts[-1] = new_filename
                    new_path = '/'.join(path_parts)
                else:
                    new_path = new_filename
                new_url = parsed._replace(path=new_path).geturl()
                generated_urls.append(new_url)
                if len(generated_urls) >= self._max_urls:
                    break
            if len(generated_urls) >= self._max_urls:
                break

        self.logger.info(f"Generated {len(generated_urls)} missing URLs from pattern filling")
        return generated_urls
