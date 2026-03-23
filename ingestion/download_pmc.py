"""
Download open-access papers from PubMed Central for VeriDoc knowledge base.
Targets 500 high-quality sources in aesthetic medicine, dermatology, and related fields.

Usage:
  python ingestion/download_pmc.py --max-papers 500
"""

import os
import time
import argparse
import requests
import defusedxml.ElementTree as ET
from typing import List, Dict, Optional

PMC_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PMC_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PMC_DIR = "data/pmc_fulltext"

AESTHETIC_MEDICINE_QUERIES = [
    # Dermal Fillers & Complications
    '"hyaluronic acid filler"[Title/Abstract] AND (complication OR adverse OR safety)',
    '"dermal filler"[Title/Abstract] AND (vascular occlusion OR necrosis)',
    '"filler injection"[Title/Abstract] AND blindness',
    'hyaluronidase[Title/Abstract] AND (filler OR aesthetic)',
    '"facial filler"[Title/Abstract] AND (review OR guideline)',
    
    # Botulinum Toxin
    '"botulinum toxin"[Title/Abstract] AND aesthetic AND (review OR guideline)',
    '"botox"[Title/Abstract] AND complication',
    'neuromodulator[Title/Abstract] AND facial AND safety',
    
    # Laser & Energy Devices
    '"laser resurfacing"[Title/Abstract] AND (complication OR safety)',
    '"fractional laser"[Title/Abstract] AND skin',
    '"IPL treatment"[Title/Abstract] AND (safety OR complication)',
    'radiofrequency[Title/Abstract] AND skin AND aesthetic',
    '"laser hair removal"[Title/Abstract] AND (complication OR burn)',
    'Fitzpatrick[Title/Abstract] AND laser AND skin',
    
    # Facial Anatomy
    '"facial anatomy"[Title/Abstract] AND (injection OR filler)',
    '"danger zone"[Title/Abstract] AND (face OR injection)',
    '"vascular anatomy"[Title/Abstract] AND face',
    
    # Skin Rejuvenation
    '"chemical peel"[Title/Abstract] AND (review OR guideline)',
    'microneedling[Title/Abstract] AND (review OR safety)',
    '"platelet rich plasma"[Title/Abstract] AND aesthetic',
    '"skin rejuvenation"[Title/Abstract] AND (review OR evidence)',
    
    # Body Contouring
    'lipolysis[Title/Abstract] AND (nonsurgical OR injection)',
    'cryolipolysis[Title/Abstract] AND (review OR safety)',
    '"body contouring"[Title/Abstract] AND noninvasive',
    
    # Thread Lifts & Scaffolds
    '"thread lift"[Title/Abstract] AND (review OR complication)',
    '"PDO threads"[Title/Abstract]',
    'biostimulator[Title/Abstract] AND aesthetic',
    
    # Sclerotherapy & Vascular
    'sclerotherapy[Title/Abstract] AND (review OR guideline)',
    '"spider veins"[Title/Abstract] AND treatment',
    
    # Skin Conditions Related to Aesthetics
    '"melasma treatment"[Title/Abstract] AND (review OR guideline)',
    '"acne scar"[Title/Abstract] AND treatment AND review',
    'hyperpigmentation[Title/Abstract] AND treatment AND skin',
    'rosacea[Title/Abstract] AND (laser OR treatment) AND review',
    
    # Safety & Consensus Guidelines
    '"aesthetic medicine"[Title/Abstract] AND (guideline OR consensus OR safety)',
    '"cosmetic dermatology"[Title/Abstract] AND (review OR guideline)',
    '"aesthetic procedure"[Title/Abstract] AND complication',
    
    # Specific Complications
    '"granuloma"[Title/Abstract] AND filler',
    '"biofilm"[Title/Abstract] AND filler',
    '"delayed reaction"[Title/Abstract] AND (filler OR injection)',
    '"inflammatory nodule"[Title/Abstract] AND aesthetic',
    
    # Anatomical Regions
    '"lip augmentation"[Title/Abstract] AND (review OR safety)',
    '"nose filler"[Title/Abstract] OR "nasal filler"[Title/Abstract]',
    '"tear trough"[Title/Abstract] AND filler',
    '"chin augmentation"[Title/Abstract] AND (filler OR nonsurgical)',
    '"jawline"[Title/Abstract] AND (filler OR contouring)',
    
    # Evidence Reviews
    '"systematic review"[Title] AND (filler OR "aesthetic medicine" OR "cosmetic dermatology")',
    '"meta-analysis"[Title] AND (aesthetic OR cosmetic OR dermatology)',
]

DOCUMENT_TYPE_KEYWORDS = {
    "guideline": ["guideline", "consensus", "recommendation", "position statement", "best practice"],
    "systematic_review": ["systematic review", "meta-analysis", "cochrane"],
    "review": ["review", "overview", "update"],
    "clinical_trial": ["randomized", "controlled trial", "clinical trial", "rct"],
}

def classify_document_type(title: str, abstract: str = "") -> str:
    """Classify document type based on title and abstract."""
    text = (title + " " + abstract).lower()
    
    for doc_type, keywords in DOCUMENT_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return doc_type if doc_type != "systematic_review" else "review"
    
    return "review"

def search_pmc(query: str, max_results: int = 50) -> List[str]:
    """Search PMC for open-access papers matching query."""
    params = {
        "db": "pmc",
        "term": f'{query} AND "open access"[filter]',
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
    }
    
    try:
        resp = requests.get(PMC_SEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        id_list = data.get("esearchresult", {}).get("idlist", [])
        return id_list
    except Exception as e:
        print(f"  Search error: {e}")
        return []

def fetch_pmc_xml(pmcid: str) -> Optional[str]:
    """Fetch full-text XML for a PMC article."""
    params = {
        "db": "pmc",
        "id": pmcid,
        "rettype": "full",
        "retmode": "xml",
    }
    
    try:
        resp = requests.get(PMC_FETCH_URL, params=params, timeout=60)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  Fetch error for {pmcid}: {e}")
        return None

def extract_basic_metadata(xml_content: str) -> Dict:
    """Extract basic metadata from XML to check if paper is relevant."""
    try:
        root = ET.fromstring(xml_content)
        
        title_elem = root.find(".//article-title")
        title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""
        
        year_elem = root.find(".//pub-date/year")
        year = int(year_elem.text.strip()) if year_elem is not None and year_elem.text.isdigit() else None
        
        abstract_elem = root.find(".//abstract")
        abstract = " ".join(abstract_elem.itertext()).strip() if abstract_elem is not None else ""
        
        return {"title": title, "year": year, "abstract": abstract}
    except:
        return {}

def is_relevant_paper(meta: Dict) -> bool:
    """Check if paper is relevant and recent enough."""
    if not meta.get("title"):
        return False
    
    year = meta.get("year")
    if year and year < 2010:
        return False
    
    title_lower = meta.get("title", "").lower()
    irrelevant_keywords = ["veterinary", "animal model", "mice", "rat", "in vitro only", "cell culture"]
    for kw in irrelevant_keywords:
        if kw in title_lower:
            return False
    
    return True

def download_papers(max_papers: int = 500, papers_per_query: int = 15):
    """Download papers from PMC based on aesthetic medicine queries."""
    os.makedirs(PMC_DIR, exist_ok=True)
    
    existing_files = set(os.listdir(PMC_DIR))
    existing_pmcids = {f.replace(".xml", "").replace("PMC", "") for f in existing_files if f.endswith(".xml")}
    
    print(f"Found {len(existing_pmcids)} existing papers")
    print(f"Target: {max_papers} total papers")
    print(f"Need to download: ~{max(0, max_papers - len(existing_pmcids))} more\n")
    
    all_pmcids = set(existing_pmcids)
    downloaded = 0
    skipped = 0
    
    for i, query in enumerate(AESTHETIC_MEDICINE_QUERIES):
        if len(all_pmcids) >= max_papers:
            print(f"\nReached target of {max_papers} papers!")
            break
        
        print(f"\n[{i+1}/{len(AESTHETIC_MEDICINE_QUERIES)}] Query: {query[:60]}...")
        
        pmcids = search_pmc(query, max_results=papers_per_query)
        print(f"  Found {len(pmcids)} results")
        
        new_ids = [pid for pid in pmcids if pid not in all_pmcids]
        
        for pmcid in new_ids:
            if len(all_pmcids) >= max_papers:
                break
            
            time.sleep(0.4)
            
            xml_content = fetch_pmc_xml(pmcid)
            if not xml_content:
                continue
            
            meta = extract_basic_metadata(xml_content)
            if not is_relevant_paper(meta):
                skipped += 1
                continue
            
            filepath = os.path.join(PMC_DIR, f"PMC{pmcid}.xml")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(xml_content)
            
            doc_type = classify_document_type(meta.get("title", ""), meta.get("abstract", ""))
            all_pmcids.add(pmcid)
            downloaded += 1
            
            print(f"  ✓ Downloaded: PMC{pmcid} ({meta.get('year', '?')}) [{doc_type}]")
            print(f"    {meta.get('title', 'Unknown')[:70]}...")
    
    print(f"\n{'='*60}")
    print(f"Download Summary:")
    print(f"  Previously existing: {len(existing_pmcids)}")
    print(f"  Newly downloaded: {downloaded}")
    print(f"  Skipped (irrelevant): {skipped}")
    print(f"  Total papers: {len(all_pmcids)}")
    print(f"{'='*60}")
    
    return len(all_pmcids)

def main():
    parser = argparse.ArgumentParser(description="Download PMC papers for VeriDoc")
    parser.add_argument("--max-papers", type=int, default=500, help="Maximum papers to download")
    parser.add_argument("--per-query", type=int, default=15, help="Papers per search query")
    args = parser.parse_args()
    
    download_papers(max_papers=args.max_papers, papers_per_query=args.per_query)

if __name__ == "__main__":
    main()
