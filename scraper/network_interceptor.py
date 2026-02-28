"""Network traffic interception for discovering hidden API endpoints."""

from __future__ import annotations

import json
import asyncio
from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

from cendoj.utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class NetworkRequest:
    """Represents a captured network request."""
    url: str
    method: str
    post_data: Optional[str] = None
    content_type: Optional[str] = None
    status: Optional[int] = None
    response_size: Optional[int] = None
    timestamp: float = field(default_factory=asyncio.get_event_loop().time)


class NetworkInterceptor:
    """
    Intercepts network traffic from Playwright pages to discover hidden API endpoints.
    
    Usage:
        interceptor = NetworkInterceptor()
        page = await browser.new_page()
        interceptor.attach(page)
        # ... do stuff ...
        endpoints = interceptor.get_json_endpoints()
        interceptor.detach()
    """

    def __init__(self, capture_json: bool = True, capture_html: bool = False, max_requests: int = 1000):
        self.capture_json = capture_json
        self.capture_html = capture_html
        self.max_requests = max_requests
        self._requests: List[NetworkRequest] = []
        self._page = None
        self._handlers: List[Callable] = []

    def attach(self, page):
        """Attach interception handlers to a Playwright page."""
        self._page = page
        self._requests.clear()
        
        async def on_request(request):
            if len(self._requests) >= self.max_requests:
                return
            post_data = None
            if request.method == 'POST':
                try:
                    post_data = request.post_data
                except Exception:
                    pass
            req = NetworkRequest(
                url=request.url,
                method=request.method,
                post_data=post_data,
            )
            self._requests.append(req)
            
            # Notify handlers
            for handler in self._handlers:
                try:
                    handler(req)
                except Exception as e:
                    logger.debug(f"Network handler error: {e}")

        async def on_response(response):
            if len(self._requests) >= self.max_requests:
                return
            # Find matching request and update
            for req in reversed(self._requests):
                if req.url == response.url:
                    req.status = response.status
                    try:
                        req.response_size = len(response.body) if response.body else None
                    except Exception:
                        pass
                    ct = response.headers.get('content-type', '')
                    req.content_type = ct
                    break

        page.on('request', on_request)
        page.on('response', on_response)
        logger.debug(f"Network interceptor attached to page")

    def detach(self):
        """Detach handlers from page."""
        if self._page:
            self._page.remove_listener('request', None)
            self._page.remove_listener('response', None)
            self._page = None

    def add_handler(self, handler: Callable[[NetworkRequest], None]):
        """Add a callback to be notified of requests."""
        self._handlers.append(handler)

    def get_requests(self) -> List[NetworkRequest]:
        """Get all captured requests."""
        return self._requests.copy()

    def get_json_endpoints(self) -> List[NetworkRequest]:
        """Get requests that returned JSON responses."""
        return [r for r in self._requests if r.content_type and 'application/json' in r.content_type]

    def get_api_endpoints(self) -> List[NetworkRequest]:
        """Get requests that look like API calls (XHR/fetch)."""
        api_keywords = ('/api/', '/ws/', '/ajax', '/xhr', '.json', 'callback=', 'format=json')
        return [r for r in self._requests if any(kw in r.url.lower() for kw in api_keywords)]

    def get_pdf_related_requests(self) -> List[NetworkRequest]:
        """Get requests that mention PDF in URL."""
        return [r for r in self._requests if '.pdf' in r.url.lower()]

    def extract_endpoints(self) -> Dict[str, Set[str]]:
        """Extract categorized endpoint patterns."""
        endpoints = {
            'json': set(),
            'api': set(),
            'pdf': set(),
            'html': set(),
        }
        for req in self._requests:
            if req.content_type:
                if 'application/json' in req.content_type:
                    endpoints['json'].add(req.url)
                elif 'text/html' in req.content_type:
                    endpoints['html'].add(req.url)
            if '.pdf' in req.url.lower():
                endpoints['pdf'].add(req.url)
            if any(kw in req.url.lower() for kw in ('/api/', '/ws/', '/ajax', '/xhr')):
                endpoints['api'].add(req.url)
        return {k: list(v) for k, v in endpoints.items()}


class NetworkInterceptorManager:
    """Manages network interceptors across multiple pages/sites."""

    def __init__(self):
        self._interceptors: Dict[str, NetworkInterceptor] = {}

    def create_interceptor(self, name: str = 'default', **kwargs) -> NetworkInterceptor:
        """Create a named interceptor."""
        interceptor = NetworkInterceptor(**kwargs)
        self._interceptors[name] = interceptor
        return interceptor

    def get_interceptor(self, name: str = 'default') -> Optional[NetworkInterceptor]:
        return self._interceptors.get(name)

    def get_all_endpoints(self) -> Dict[str, List[str]]:
        """Aggregate endpoints from all interceptors."""
        aggregated = {
            'json': set(),
            'api': set(),
            'pdf': set(),
            'html': set(),
        }
        for interceptor in self._interceptors.values():
            endpoints = interceptor.extract_endpoints()
            for category, urls in endpoints.items():
                aggregated[category].update(urls)
        return {k: list(v) for k, v in aggregated.items()}

    def clear(self):
        """Clear all interceptors."""
        self._interceptors.clear()
