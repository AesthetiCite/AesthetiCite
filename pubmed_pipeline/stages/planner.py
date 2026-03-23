"""
Stage 1: Query Planning
========================
Builds the corpus definition and retrieves PMIDs from PubMed.
Supports the enhanced corpus.yaml format with:
- query_any / query_all structure
- Year slicing for large queries
- Global filters (include/exclude terms)
"""

import time
import requests
import logging
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from pubmed_pipeline.utils.config import CorpusConfig, QueryGroup
from pubmed_pipeline.utils.throttle import RateLimiter, retry_with_backoff

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

@dataclass
class PlanResult:
    total_pmids: int
    pmids_by_tier: Dict[str, int]
    pmids_by_group: Dict[str, int]
    all_pmids: Set[str]
    coverage_report: Dict

class QueryPlanner:
    def __init__(self, config: CorpusConfig):
        self.config = config
        self.rate_limiter = RateLimiter(config.ncbi.qps)
        self.all_pmids: Set[str] = set()
        self.pmids_by_tier: Dict[str, Set[str]] = {}
        self.pmids_by_group: Dict[str, Set[str]] = {}
    
    @retry_with_backoff(max_retries=6, base_delay=0.5, exceptions=(requests.RequestException,))
    def search_pubmed(self, query: str, retmax: int = 10000, retstart: int = 0) -> tuple:
        self.rate_limiter.wait()
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retstart": retstart,
            "retmode": "json",
            "usehistory": "y",
            "tool": self.config.ncbi.tool,
        }
        if self.config.ncbi.email:
            params["email"] = self.config.ncbi.email
        
        r = requests.get(ESEARCH_URL, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        result = data.get("esearchresult", {})
        count = int(result.get("count", 0))
        ids = result.get("idlist", [])
        webenv = result.get("webenv", "")
        query_key = result.get("querykey", "")
        return ids, count, webenv, query_key
    
    def build_query(self, group: QueryGroup, year_range: Optional[Tuple[int, int]] = None) -> str:
        """Build PubMed query from group with query_any/query_all structure."""
        parts = []
        
        if group.query_any:
            any_parts = " OR ".join(group.query_any)
            parts.append(f"({any_parts})")
        
        for q in group.query_all:
            parts.append(f"({q})")
        
        if not parts:
            return ""
        
        query = " AND ".join(parts)
        
        gf = self.config.global_filters
        for term in gf.include_terms:
            query = f"({query}) AND ({term})"
        
        for term in gf.exclude_terms:
            query = f"({query}) NOT ({term})"
        
        if gf.languages:
            lang_filter = " OR ".join([f"{lang}[la]" for lang in gf.languages])
            query = f"({query}) AND ({lang_filter})"
        
        if year_range:
            start, end = year_range
            query = f"({query}) AND ({start}:{end}[pdat])"
        elif gf.date_range:
            start, end = gf.date_range
            if '/' in start:
                start = start.split('/')[0]
            if '/' in end:
                end_year = end.split('/')[0]
                if int(end_year) > 2100:
                    end_year = str(datetime.now().year)
                end = end_year
            query = f"({query}) AND ({start}:{end}[pdat])"
        
        return query
    
    def plan_group(self, group: QueryGroup) -> Set[str]:
        """Plan a single query group, optionally using year slicing."""
        group_pmids = set()
        
        year_slices = self.config.get_year_slices() if self.config.planning.year_slicing_enabled else []
        
        if year_slices:
            logger.info(f"  Using {len(year_slices)} year slices")
            for start_year, end_year in year_slices:
                query = self.build_query(group, (start_year, end_year))
                if not query:
                    continue
                
                slice_pmids = self._fetch_pmids(query, group.target_count)
                new_pmids = slice_pmids - self.all_pmids
                group_pmids.update(new_pmids)
                
                if len(group_pmids) >= group.target_count:
                    break
        else:
            query = self.build_query(group)
            if query:
                group_pmids = self._fetch_pmids(query, group.target_count)
        
        return group_pmids
    
    def _fetch_pmids(self, query: str, target_count: int) -> Set[str]:
        """Fetch PMIDs for a query with pagination."""
        pmids = set()
        retstart = 0
        batch_size = 10000
        
        ids, total_count, _, _ = self.search_pubmed(query, retmax=batch_size)
        pmids.update(ids)
        
        while len(pmids) < min(target_count, total_count) and retstart + batch_size < total_count:
            retstart += batch_size
            ids, _, _, _ = self.search_pubmed(query, retmax=batch_size, retstart=retstart)
            if not ids:
                break
            pmids.update(ids)
            
            if len(pmids) >= target_count:
                break
        
        return pmids
    
    def run(self) -> PlanResult:
        logger.info(f"Starting query planning for corpus: {self.config.name}")
        logger.info(f"Target: {self.config.target_total} publications")
        logger.info(f"Query groups: {len(self.config.query_groups)}")
        
        groups_by_priority = sorted(self.config.query_groups, key=lambda g: g.priority)
        
        for group in groups_by_priority:
            logger.info(f"Planning group '{group.id}' ({group.tier_name}, priority {group.priority})")
            
            group_pmids = self.plan_group(group)
            new_pmids = group_pmids - self.all_pmids
            
            self.pmids_by_group[group.id] = new_pmids
            
            if group.tier_name not in self.pmids_by_tier:
                self.pmids_by_tier[group.tier_name] = set()
            self.pmids_by_tier[group.tier_name].update(new_pmids)
            
            self.all_pmids.update(new_pmids)
            
            logger.info(f"  Group '{group.id}': {len(new_pmids)} unique PMIDs (total: {len(self.all_pmids)})")
            
            if len(self.all_pmids) >= self.config.target_total:
                logger.info(f"Reached target of {self.config.target_total}")
                break
        
        coverage = self.generate_coverage_report()
        
        return PlanResult(
            total_pmids=len(self.all_pmids),
            pmids_by_tier={k: len(v) for k, v in self.pmids_by_tier.items()},
            pmids_by_group={k: len(v) for k, v in self.pmids_by_group.items()},
            all_pmids=self.all_pmids,
            coverage_report=coverage,
        )
    
    def generate_coverage_report(self) -> Dict:
        return {
            "total_pmids": len(self.all_pmids),
            "by_tier": {k: len(v) for k, v in self.pmids_by_tier.items()},
            "by_group": {k: len(v) for k, v in self.pmids_by_group.items()},
            "groups_planned": len(self.pmids_by_group),
            "config_version": self.config.version,
        }
