"""
Stage 2: Retrieval (Metadata + Abstracts)
==========================================
Fetches publication metadata from PubMed E-utilities.
"""

import time
import requests
import defusedxml.ElementTree as ET
import logging
import gzip
import json
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field

from pubmed_pipeline.utils.throttle import RateLimiter, retry_with_backoff, ProgressTracker

logger = logging.getLogger(__name__)

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

@dataclass
class Publication:
    pmid: str
    title: str = ""
    abstract: str = ""
    journal: str = ""
    year: Optional[int] = None
    doi: Optional[str] = None
    publication_types: List[str] = field(default_factory=list)
    mesh_terms: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    language: str = "eng"
    pmc_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "abstract": self.abstract,
            "journal": self.journal,
            "year": self.year,
            "doi": self.doi,
            "publication_types": self.publication_types,
            "mesh_terms": self.mesh_terms,
            "authors": self.authors,
            "language": self.language,
            "pmc_id": self.pmc_id,
        }

class PubMedFetcher:
    def __init__(self, rate_limit_qps: float = 3.0, save_raw: bool = False, raw_dir: str = "data/raw"):
        self.rate_limiter = RateLimiter(rate_limit_qps)
        self.save_raw = save_raw
        self.raw_dir = Path(raw_dir)
        if save_raw:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
    
    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(requests.RequestException, ET.ParseError))
    def fetch_batch(self, pmids: List[str]) -> List[Publication]:
        self.rate_limiter.wait()
        
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        
        r = requests.get(EFETCH_URL, params=params, timeout=120)
        r.raise_for_status()
        
        if self.save_raw:
            raw_path = self.raw_dir / f"batch_{pmids[0]}_{len(pmids)}.xml.gz"
            with gzip.open(raw_path, 'wt') as f:
                f.write(r.text)
        
        return self.parse_xml(r.content)
    
    def parse_xml(self, content: bytes) -> List[Publication]:
        publications = []
        try:
            root = ET.fromstring(content)
            for article in root.findall(".//PubmedArticle"):
                pub = self.parse_article(article)
                if pub:
                    publications.append(pub)
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
        return publications
    
    def parse_article(self, article: ET.Element) -> Optional[Publication]:
        try:
            medline = article.find(".//MedlineCitation")
            if medline is None:
                return None
            
            pmid_elem = medline.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else None
            if not pmid:
                return None
            
            art = medline.find(".//Article")
            if art is None:
                return None
            
            title_elem = art.find(".//ArticleTitle")
            title = "".join(title_elem.itertext()) if title_elem is not None else ""
            
            abstract_parts = []
            abstract_elem = art.find(".//Abstract")
            if abstract_elem is not None:
                for abs_text in abstract_elem.findall(".//AbstractText"):
                    label = abs_text.get("Label", "")
                    text = "".join(abs_text.itertext())
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
            abstract = " ".join(abstract_parts)
            
            journal_elem = art.find(".//Journal/Title")
            journal = journal_elem.text if journal_elem is not None else ""
            
            year = None
            pub_date = art.find(".//Journal/JournalIssue/PubDate")
            if pub_date is not None:
                year_elem = pub_date.find("Year")
                if year_elem is not None and year_elem.text:
                    try:
                        year = int(year_elem.text)
                    except ValueError:
                        pass
                if year is None:
                    medline_date = pub_date.find("MedlineDate")
                    if medline_date is not None and medline_date.text:
                        try:
                            year = int(medline_date.text[:4])
                        except ValueError:
                            pass
            
            doi = None
            for id_elem in article.findall(".//ArticleIdList/ArticleId"):
                if id_elem.get("IdType") == "doi":
                    doi = id_elem.text
                    break
            
            pmc_id = None
            for id_elem in article.findall(".//ArticleIdList/ArticleId"):
                if id_elem.get("IdType") == "pmc":
                    pmc_id = id_elem.text
                    break
            
            pub_types = []
            for pt in art.findall(".//PublicationTypeList/PublicationType"):
                if pt.text:
                    pub_types.append(pt.text)
            
            mesh_terms = []
            for mesh in medline.findall(".//MeshHeadingList/MeshHeading/DescriptorName"):
                if mesh.text:
                    mesh_terms.append(mesh.text)
            
            authors = []
            for author in art.findall(".//AuthorList/Author"):
                last = author.find("LastName")
                fore = author.find("ForeName")
                if last is not None and last.text:
                    name = last.text
                    if fore is not None and fore.text:
                        name = f"{fore.text} {name}"
                    authors.append(name)
            
            lang_elem = art.find(".//Language")
            language = lang_elem.text if lang_elem is not None else "eng"
            
            return Publication(
                pmid=pmid,
                title=title,
                abstract=abstract,
                journal=journal,
                year=year,
                doi=doi,
                publication_types=pub_types,
                mesh_terms=mesh_terms,
                authors=authors[:10],
                language=language,
                pmc_id=pmc_id,
            )
        except Exception as e:
            logger.error(f"Error parsing article: {e}")
            return None
    
    def fetch_all(self, pmids: List[str], batch_size: int = 200) -> List[Publication]:
        all_pubs = []
        progress = ProgressTracker(len(pmids), "Fetching")
        
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            try:
                pubs = self.fetch_batch(batch)
                all_pubs.extend(pubs)
            except Exception as e:
                logger.error(f"Batch fetch failed at {i}: {e}")
            progress.update(len(batch))
        
        progress.finish()
        return all_pubs
