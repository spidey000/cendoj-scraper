"""Coverage graph and gap analysis service."""

from __future__ import annotations

from typing import Dict, List, Set, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import json

from cendoj.utils.logger import get_logger
from cendoj.storage.database import get_session
from cendoj.storage.schemas import PDFLink, DiscoverySession


logger = get_logger(__name__)


@dataclass
class CoverageNode:
    """Represents a node in the coverage graph."""
    url: str
    depth: int = 0
    strategy: str = 'unknown'
    status: str = 'unknown'
    children: Set[str] = field(default_factory=set)


class CoverageGraph:
    """Directed graph of discovered/crawled URLs."""

    def __init__(self):
        self.nodes: Dict[str, CoverageNode] = {}

    def add_node(self, url: str, **kwargs):
        if url not in self.nodes:
            self.nodes[url] = CoverageNode(url=url, **kwargs)

    def add_edge(self, source: str, target: str):
        if source not in self.nodes:
            self.add_node(source)
        if target not in self.nodes:
            self.add_node(target)
        self.nodes[source].children.add(target)

    def get_frontier(self) -> List[str]:
        """Get nodes with no children (leaf nodes)."""
        return [url for url, node in self.nodes.items() if not node.children]

    def get_orphans(self) -> List[str]:
        """Get nodes with no incoming edges (except seeds)."""
        # For simplicity, nodes that are never a target
        targets = set()
        for node in self.nodes.values():
            targets.update(node.children)
        return [url for url in self.nodes if url not in targets]

    def get_disconnected_components(self) -> List[Set[str]]:
        """Find disconnected subgraphs."""
        visited = set()
        components = []

        def dfs(node_url, component):
            if node_url in visited:
                return
            visited.add(node_url)
            component.add(node_url)
            for child in self.nodes[node_url].children:
                dfs(child, component)

        for url in self.nodes:
            if url not in visited:
                component = set()
                dfs(url, component)
                components.append(component)

        return components


class CoverageAnalyzer:
    """Analyze coverage and identify gaps in the discovery graph."""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.graph = CoverageGraph()

    def build_from_db(self, session_id: Optional[str] = None) -> CoverageGraph:
        """Build coverage graph from database."""
        db_session = get_session()
        try:
            # Get all PDF links
            query = db_session.query(PDFLink)
            if session_id:
                query = query.filter_by(discovery_session_id=session_id)
            
            pdf_links = query.all()
            
            for link in pdf_links:
                source = link.source_url or 'unknown'
                self.graph.add_node(
                    link.url,
                    strategy=link.extraction_method or 'unknown',
                    status=link.status or 'unknown'
                )
                self.graph.add_edge(source, link.url)
            
            self.logger.info(f"Built coverage graph with {len(self.graph.nodes)} nodes")
            return self.graph
        finally:
            db_session.close()

    def analyze_gaps(self) -> Dict[str, Any]:
        """Analyze the graph to identify coverage gaps."""
        gaps = {
            'total_nodes': len(self.graph.nodes),
            'frontier_count': len(self.graph.get_frontier()),
            'orphan_count': len(self.graph.get_orphans()),
            'disconnected_components': len(self.graph.get_disconnected_components()),
            'status_distribution': defaultdict(int),
            'strategy_distribution': defaultdict(int),
            'recommendations': [],
        }

        # Status distribution
        for node in self.graph.nodes.values():
            gaps['status_distribution'][node.status] += 1
            gaps['strategy_distribution'][node.strategy] += 1

        # Generate recommendations
        if gaps['disconnected_components'] > 1:
            gaps['recommendations'].append(
                f"Found {gaps['disconnected_components']} disconnected components - "
                "consider adding more seed URLs to connect them"
            )

        if gaps['orphan_count'] > 0:
            gaps['recommendations'].append(
                f"Found {gaps['orphan_count']} orphan pages (no incoming links) - "
                "check if these should be connected to the main crawl"
            )

        # Check for low-coverage years if URLs contain years
        years = self._extract_years()
        if years:
            missing_years = self._find_missing_years(years)
            if missing_years:
                gaps['recommendations'].append(
                    f"Missing coverage for years: {missing_years[:10]} - "
                    "consider adding archive probes for these years"
                )

        gaps['status_distribution'] = dict(gaps['status_distribution'])
        gaps['strategy_distribution'] = dict(gaps['strategy_distribution'])
        return gaps

    def _extract_years(self) -> Set[int]:
        """Extract years from URLs."""
        import re
        years = set()
        year_pattern = re.compile(r'/(20\d{2})/')
        for url in self.graph.nodes:
            for match in year_pattern.finditer(url):
                year = int(match.group(1))
                if 1990 <= year <= datetime.now().year:
                    years.add(year)
        return years

    def _find_missing_years(self, found_years: Set[int]) -> List[int]:
        """Find missing years in a range."""
        if not found_years:
            return []
        min_year = min(found_years)
        max_year = max(found_years)
        all_years = set(range(min_year, max_year + 1))
        return sorted(all_years - found_years)

    def generate_report(self, session_id: Optional[str] = None) -> str:
        """Generate a text report of coverage analysis."""
        self.build_from_db(session_id)
        gaps = self.analyze_gaps()

        report = ["=" * 50, "COVERAGE ANALYSIS REPORT", "=" * 50, ""]
        report.append(f"Total nodes: {gaps['total_nodes']}")
        report.append(f"Frontier nodes: {gaps['frontier_count']}")
        report.append(f"Orphan nodes: {gaps['orphan_count']}")
        report.append(f"Disconnected components: {gaps['disconnected_components']}")
        report.append("")

        report.append("Status Distribution:")
        for status, count in gaps['status_distribution'].items():
            report.append(f"  {status}: {count}")
        report.append("")

        report.append("Strategy Distribution:")
        for strategy, count in gaps['strategy_distribution'].items():
            report.append(f"  {strategy}: {count}")
        report.append("")

        if gaps['recommendations']:
            report.append("Recommendations:")
            for rec in gaps['recommendations']:
                report.append(f"  - {rec}")

        return "\n".join(report)

    def save_snapshot(self, filepath: str):
        """Save graph snapshot to JSON file."""
        data = {
            'timestamp': datetime.utcnow().isoformat(),
            'nodes': [
                {
                    'url': node.url,
                    'depth': node.depth,
                    'strategy': node.strategy,
                    'status': node.status,
                    'children': list(node.children),
                }
                for node in self.graph.nodes.values()
            ]
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        self.logger.info(f"Coverage snapshot saved to {filepath}")
