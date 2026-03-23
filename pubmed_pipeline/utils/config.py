"""
Configuration management for PubMed pipeline.
Supports the enhanced corpus.yaml format with:
- query_any / query_all structure
- Tiered groups with priority
- Performance hooks for classification and ranking
- Year slicing for large queries
"""

import os
import yaml
import hashlib
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple

@dataclass
class QueryGroup:
    id: str
    label: str
    tier_name: str
    priority: int
    query_any: List[str] = field(default_factory=list)
    query_all: List[str] = field(default_factory=list)
    target_count: int = 10000

@dataclass
class GlobalFilters:
    humans_only: bool = True
    languages: List[str] = field(default_factory=lambda: ["eng"])
    date_range: Tuple[str, str] = ("2000/01/01", "2026/12/31")
    include_terms: List[str] = field(default_factory=list)
    exclude_terms: List[str] = field(default_factory=list)

@dataclass
class NCBIConfig:
    tool: str = "aestheticite-pipeline"
    email: str = ""
    api_key_env: str = "NCBI_API_KEY"
    qps: float = 8.0
    max_retries: int = 6
    backoff_base: float = 0.5
    backoff_max: float = 20.0

@dataclass
class PlanningConfig:
    year_slicing_enabled: bool = True
    block_years: int = 2
    pmid_cap_per_slice: int = 120000

@dataclass 
class PerformanceHooks:
    source_type_rules: List[Dict] = field(default_factory=list)
    quality_rank_mapping: Dict[str, int] = field(default_factory=dict)
    dedup_prefer: List[str] = field(default_factory=list)

@dataclass
class CorpusConfig:
    name: str
    version: str
    target_total: int
    query_groups: List[QueryGroup]
    global_filters: GlobalFilters
    ncbi: NCBIConfig
    planning: PlanningConfig
    hooks: PerformanceHooks
    
    @classmethod
    def from_yaml(cls, path: str) -> 'CorpusConfig':
        with open(path) as f:
            data = yaml.safe_load(f)
        
        ncbi_data = data.get('ncbi', {})
        throttle = ncbi_data.get('throttle', {})
        ncbi = NCBIConfig(
            tool=ncbi_data.get('tool', 'aestheticite-pipeline'),
            email=ncbi_data.get('email', ''),
            api_key_env=ncbi_data.get('api_key_env', 'NCBI_API_KEY'),
            qps=throttle.get('qps', 8.0),
            max_retries=throttle.get('max_retries', 6),
            backoff_base=throttle.get('backoff_base_seconds', 0.5),
            backoff_max=throttle.get('backoff_max_seconds', 20.0),
        )
        
        gf_data = data.get('global_filters', {})
        dr = gf_data.get('date_range', {})
        global_filters = GlobalFilters(
            humans_only=gf_data.get('humans_only', True),
            languages=gf_data.get('languages', ['eng']),
            date_range=(dr.get('from', '2000/01/01'), dr.get('to', '2026/12/31')),
            include_terms=gf_data.get('include_terms', []),
            exclude_terms=gf_data.get('exclude_terms', []),
        )
        
        plan_data = data.get('planning', {})
        ys = plan_data.get('year_slicing', {})
        planning = PlanningConfig(
            year_slicing_enabled=ys.get('enabled', True),
            block_years=ys.get('block_years', 2),
            pmid_cap_per_slice=plan_data.get('pmid_cap_per_query_slice', 120000),
        )
        
        hooks_data = data.get('performance_hooks', {})
        stc = hooks_data.get('source_type_classifier', {})
        qr = hooks_data.get('quality_rank', {})
        dd = hooks_data.get('dedup', {})
        hooks = PerformanceHooks(
            source_type_rules=stc.get('rules', []),
            quality_rank_mapping=qr.get('mapping', {}),
            dedup_prefer=dd.get('prefer_if_conflict', []),
        )
        
        groups = []
        for tier in data.get('tiers', []):
            tier_name = tier.get('name', 'tier')
            priority = tier.get('priority', 3)
            target = tier.get('target_pmids', 10000)
            
            for g in tier.get('groups', []):
                groups.append(QueryGroup(
                    id=g.get('id', ''),
                    label=g.get('label', ''),
                    tier_name=tier_name,
                    priority=priority,
                    query_any=g.get('query_any', []),
                    query_all=g.get('query_all', []),
                    target_count=target // max(1, len(tier.get('groups', [1]))),
                ))
        
        if not groups:
            groups = _load_legacy_format(data)
        
        goal = data.get('goal', {})
        return cls(
            name=data.get('project', goal.get('project', 'corpus')),
            version=str(data.get('version', '1')),
            target_total=goal.get('target_total_pmids', data.get('target_total', 1000000)),
            query_groups=groups,
            global_filters=global_filters,
            ncbi=ncbi,
            planning=planning,
            hooks=hooks,
        )
    
    def hash(self) -> str:
        content = yaml.dump({
            'name': self.name,
            'version': self.version,
            'groups': [g.id for g in self.query_groups],
        })
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def get_year_slices(self) -> List[Tuple[int, int]]:
        if not self.planning.year_slicing_enabled:
            return []
        
        start_str = self.global_filters.date_range[0]
        end_str = self.global_filters.date_range[1]
        
        try:
            start_year = int(start_str.split('/')[0])
        except:
            start_year = 2000
        
        try:
            end_year = int(end_str.split('/')[0])
            if end_year > 2100:
                end_year = datetime.now().year
        except:
            end_year = datetime.now().year
        
        slices = []
        block = self.planning.block_years
        for y in range(start_year, end_year + 1, block):
            slices.append((y, min(y + block - 1, end_year)))
        
        return slices


def _load_legacy_format(data: dict) -> List[QueryGroup]:
    """Load legacy format with simple query_groups list."""
    groups = []
    for g in data.get('query_groups', []):
        groups.append(QueryGroup(
            id=g.get('name', ''),
            label=g.get('name', ''),
            tier_name=g.get('tier', 'tier3'),
            priority=3 if 'tier3' in g.get('tier', '') else (2 if 'tier2' in g.get('tier', '') else 1),
            query_any=g.get('queries', []),
            query_all=[],
            target_count=g.get('target_count', 10000),
        ))
    return groups


def get_db_url() -> str:
    url = os.getenv('DATABASE_URL', '')
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://')
    return url


def classify_source_type(publication_types: List[str], title: str, abstract: str = "", rules: List[Dict] = None) -> str:
    """
    Classify source type using performance hooks rules.
    Returns: guideline, rct, meta_analysis, review, case_series, or other
    """
    if rules is None:
        rules = DEFAULT_SOURCE_TYPE_RULES
    
    pt_lower = [pt.lower() for pt in publication_types]
    text = f"{title} {abstract}".lower()
    
    for rule in rules:
        if 'if_publication_type_any' in rule:
            for pt in rule['if_publication_type_any']:
                if pt.lower() in pt_lower:
                    return rule.get('then_source_type', 'other')
        
        if 'if_title_or_abstract_regex' in rule:
            pattern = rule['if_title_or_abstract_regex']
            if re.search(pattern, text, re.IGNORECASE):
                return rule.get('then_source_type', 'other')
        
        if 'else_source_type' in rule:
            return rule['else_source_type']
    
    return 'other'


def get_quality_rank(source_type: str, mapping: Dict[str, int] = None) -> int:
    """Get quality rank for source type using performance hooks mapping."""
    if mapping is None:
        mapping = DEFAULT_QUALITY_RANKS
    return mapping.get(source_type, 35)


DEFAULT_SOURCE_TYPE_RULES = [
    {"if_publication_type_any": ["Practice Guideline", "Guideline"], "then_source_type": "guideline"},
    {"if_title_or_abstract_regex": r"(consensus|recommendation|position statement|guideline)", "then_source_type": "guideline"},
    {"if_publication_type_any": ["Randomized Controlled Trial"], "then_source_type": "rct"},
    {"if_publication_type_any": ["Systematic Review", "Meta-Analysis"], "then_source_type": "meta_analysis"},
    {"if_publication_type_any": ["Review"], "then_source_type": "review"},
    {"if_publication_type_any": ["Case Reports"], "then_source_type": "case_series"},
    {"else_source_type": "other"},
]

DEFAULT_QUALITY_RANKS = {
    "pi": 100,
    "guideline": 95,
    "meta_analysis": 85,
    "rct": 80,
    "case_series": 55,
    "review": 50,
    "other": 35,
}
