"""Form discovery and automated submission strategy."""

from __future__ import annotations

import re
from typing import List, Dict, Any, Set
from urllib.parse import urljoin, parse_qs, urlencode
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup

from cendoj.scraper.strategies.base import DiscoveryStrategy, StrategyResult
from cendoj.utils.logger import get_logger

logger = get_logger(__name__)


class FormDiscoveryStrategy(DiscoveryStrategy):
    """Discover and submit forms to uncover hidden PDF listings."""

    name = "form_discovery"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._form_config = getattr(self.config, 'form_discovery_config', lambda: {})()
        self._session: aiohttp.ClientSession = None
        self._max_combinations = int(self._form_config.get('max_combinations', 1000))
        self._seed_pages = self._form_config.get('seed_pages', [])
        self._form_selectors = self._form_config.get('form_selectors', ['form'])
        self._include_patterns = [re.compile(p) for p in self._form_config.get('include_patterns', [])]
        self._exclude_patterns = [re.compile(p) for p in self._form_config.get('exclude_patterns', [])]

    @property
    def enabled(self) -> bool:
        return bool(self._form_config.get('enabled', False)) and bool(self._seed_pages)

    async def initialize(self):
        if not self.enabled or self._session:
            return
        timeout = aiohttp.ClientTimeout(total=self._form_config.get('timeout_seconds', 60))
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def discover(self) -> StrategyResult:
        result = StrategyResult(metadata={'strategy': self.name})
        if not self.enabled:
            return result

        for page_url in self._seed_pages:
            try:
                forms = await self._fetch_and_parse_forms(page_url)
                for form in forms:
                    pdf_urls = await self._submit_form_and_extract(page_url, form)
                    result.seed_urls.extend(pdf_urls)
                    if len(result.seed_urls) >= self._max_combinations:
                        break
            except Exception as exc:
                logger.warning(f"FormDiscovery failed for {page_url}: {exc}")

        result.seed_urls = self._filter_urls(result.seed_urls)
        result.metadata['total_seeds'] = len(result.seed_urls)
        return result

    async def cleanup(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _fetch_and_parse_forms(self, page_url: str) -> List[Dict]:
        """Download page and parse <form> elements."""
        if self.rate_limiter:
            await self.rate_limiter.wait()
        if not self._session:
            await self.initialize()
        async with self._session.get(page_url) as resp:
            resp.raise_for_status()
            html = await resp.text()
        soup = BeautifulSoup(html, 'html.parser')
        forms = []
        for selector in self._form_selectors:
            for form in soup.select(selector):
                form_data = self._parse_form(form, page_url)
                if form_data:
                    forms.append(form_data)
        return forms

    def _parse_form(self, form: BeautifulSoup, base_url: str) -> Dict[str, Any]:
        """Extract action, method, and input fields from a form."""
        action = form.get('action')
        if not action:
            return None
        method = form.get('method', 'get').lower()
        action_url = urljoin(base_url, action)
        inputs = {}
        for inp in form.find_all(['input', 'select', 'textarea']):
            name = inp.get('name')
            if not name:
                continue
            tag = inp.name
            input_type = inp.get('type', '').lower()
            value = inp.get('value', '')
            if tag == 'select':
                options = [opt.get('value') or opt.text for opt in inp.find_all('option') if opt.get('value') or opt.text]
                inputs[name] = {'type': 'select', 'options': options, 'multiple': inp.get('multiple') is not None}
            elif tag == 'textarea':
                inputs[name] = {'type': 'textarea', 'value': value}
            else:
                if input_type in ('checkbox', 'radio'):
                    # For checkboxes/radios, we'll consider each as independent boolean presence
                    inputs[name] = {'type': input_type, 'value': value, 'checked': input_type == 'checkbox' and inp.has_attr('checked')}
                else:
                    inputs[name] = {'type': 'text', 'value': value}
        return {'action': action_url, 'method': method, 'inputs': inputs, 'original_html': str(form)}

    async def _submit_form_and_extract(self, base_url: str, form: Dict) -> List[str]:
        """Submit the form with enumerated parameter values and extract PDF URLs from responses."""
        # Build list of parameter combinations, bounded by max_combinations
        param_combinations = self._enumerate_parameters(form['inputs'])
        pdf_urls: Set[str] = set()
        count = 0
        for params in param_combinations:
            if count >= self._max_combinations:
                break
            try:
                if self.rate_limiter:
                    await self.rate_limiter.wait()
                if form['method'] == 'post':
                    async with self._session.post(form['action'], data=params) as resp:
                        html = await resp.text()
                else:
                    query = urlencode(params)
                    full_url = f"{form['action']}?{query}"
                    async with self._session.get(full_url) as resp:
                        html = await resp.text()
                # Extract PDFs from response HTML
                found = re.findall(r'https?://[^\s"\'<>]+\.pdf', html, re.IGNORECASE)
                pdf_urls.update(found)
                count += 1
            except Exception as exc:
                logger.debug(f"Form submission failed: {exc}")
        return list(pdf_urls)

    def _enumerate_parameters(self, inputs: Dict) -> List[Dict[str, str]]:
        """Generate a list of parameter dictionaries to submit."""
        # Heuristic:
        # - For text/textarea: use the default value or placeholder
        # - For select: use each option (maybe only a few if many)
        # - For checkbox/radio: try both present and absent (or value vs nothing)
        # We'll flatten into a single combination per set, but could also produce cartesian product.
        # To stay within max_combinations, we'll produce one combination per "interesting" selection per field.
        combinations = []
        # We'll start with all default/empty values
        base = {}
        selections = {}
        for name, meta in inputs.items():
            if meta['type'] == 'select':
                opts = meta.get('options', [])
                if opts:
                    # Use first option as default, and possibly all options if few (e.g., <= 5)
                    selections[name] = opts[:5]  # cap to 5
                else:
                    base[name] = ''
            elif meta['type'] in ('checkbox', 'radio'):
                # Include both: omitted, or value if there is a value attribute
                val = meta.get('value', '')
                selections[name] = ['', val] if val else ['']
            else:
                base[name] = meta.get('value', '')

        if not selections:
            return [base]

        # Create combinations by varying selected fields one at a time, plus base
        combos = [base]
        for name, values in selections.items():
            for val in values:
                combo = base.copy()
                if val != '':
                    combo[name] = val
                # Avoid duplicates
                if combo not in combos:
                    combos.append(combo)
        return combos
