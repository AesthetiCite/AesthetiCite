import os
import re
import json
import time
import requests
from typing import List, Dict, Any

NCBI_EMAIL = os.getenv("NCBI_EMAIL", "veridoc@example.com")
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

def ncbi_get(endpoint: str, params: Dict[str, Any], retries: int = 3) -> str:
    params = dict(params)
    params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    
    for attempt in range(retries):
        try:
            r = requests.get(BASE + endpoint, params=params, timeout=40)
            if r.status_code == 429:
                wait = (attempt + 1) * 5
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.text
        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise
    return ""

def esearch_pubmed(term: str, retmax: int = 50) -> List[str]:
    xml = ncbi_get("esearch.fcgi", {
        "db": "pubmed",
        "term": term,
        "retmode": "xml",
        "retmax": str(retmax),
        "sort": "relevance",
    })
    return re.findall(r"<Id>(\d+)</Id>", xml)

def esummary_pubmed(pmids: List[str]) -> List[Dict[str, Any]]:
    if not pmids:
        return []
    out = []
    for i in range(0, len(pmids), 100):
        batch = pmids[i:i+100]
        xml = ncbi_get("esummary.fcgi", {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
        })
        docs = re.split(r"</DocSum>", xml)
        for d in docs:
            m_id = re.search(r"<Id>(\d+)</Id>", d)
            if not m_id:
                continue
            pmid = m_id.group(1)
            def item(name: str) -> str:
                m = re.search(rf'<Item Name="{re.escape(name)}" Type="[^"]+">(.+?)</Item>', d)
                return re.sub("<.*?>", "", m.group(1)).strip() if m else ""
            title = item("Title")
            journal = item("Source")
            pubdate = item("PubDate")
            year_m = re.search(r"(\d{4})", pubdate or "")
            year = int(year_m.group(1)) if year_m else None
            doi = item("DOI")
            out.append({
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "year": year,
                "doi": doi or None,
                "pubdate": pubdate or None
            })
        time.sleep(1)
    return out

def score_title(title: str) -> int:
    t = (title or "").lower()
    score = 0
    if any(k in t for k in ["guideline", "consensus", "position statement", "recommendation"]):
        score += 50
    if any(k in t for k in ["systematic review", "meta-analysis", "review"]):
        score += 25
    if any(k in t for k in ["vascular", "occlusion", "ischemia", "necrosis", "blindness", "vision loss", "laser", "burn", "hyaluronidase"]):
        score += 25
    return score

def make_source_id(pmid: str, year: int | None) -> str:
    return f"pubmed_{pmid}_{year or 'nd'}"

def infer_document_type(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in ["guideline", "consensus", "position statement", "recommendation"]):
        return "consensus"
    if "systematic review" in t or "meta-analysis" in t:
        return "review"
    if "review" in t:
        return "review"
    return "other"

def main():
    QUERIES = [
        '(dermal filler[Title/Abstract] OR hyaluronic acid filler[Title/Abstract]) AND (vascular occlusion[Title/Abstract] OR ischemia[Title/Abstract] OR necrosis[Title/Abstract]) AND (review[Publication Type] OR guideline[Publication Type] OR consensus[Title/Abstract])',
        '(hyaluronidase[Title/Abstract]) AND (filler[Title/Abstract] OR hyaluronic acid[Title/Abstract]) AND (review[Publication Type] OR consensus[Title/Abstract])',
        '(facial filler[Title/Abstract] OR dermal filler[Title/Abstract]) AND (blindness[Title/Abstract] OR vision loss[Title/Abstract] OR ophthalmic[Title/Abstract])',
        '(facial anatomy[Title/Abstract] OR vascular anatomy[Title/Abstract]) AND (filler injection[Title/Abstract] OR injectable[Title/Abstract]) AND (review[Publication Type] OR anatomy[Title/Abstract])',
        '(botulinum toxin[Title/Abstract]) AND (complication[Title/Abstract] OR adverse event[Title/Abstract]) AND (review[Publication Type] OR guideline[Publication Type])',
        '(laser[Title/Abstract] OR IPL[Title/Abstract] OR intense pulsed light[Title/Abstract]) AND (safety[Title/Abstract] OR burn[Title/Abstract] OR complication[Title/Abstract]) AND (review[Publication Type] OR guideline[Publication Type])',
        '(Fitzpatrick[Title/Abstract] OR skin of color[Title/Abstract] OR darker skin[Title/Abstract]) AND (laser[Title/Abstract] OR IPL[Title/Abstract]) AND (risk[Title/Abstract] OR complication[Title/Abstract])',
        '(isotretinoin[Title/Abstract]) AND (laser[Title/Abstract] OR procedure[Title/Abstract]) AND (review[Publication Type] OR guideline[Publication Type])',
        '(anticoagulant[Title/Abstract] OR anticoagulation[Title/Abstract]) AND (dermal filler[Title/Abstract] OR cosmetic procedure[Title/Abstract])',
        '(autoimmune[Title/Abstract] OR immunosuppress*[Title/Abstract]) AND (dermal filler[Title/Abstract] OR aesthetic procedure[Title/Abstract])',
    ]

    target_total = 120
    pmids: List[str] = []
    seen = set()

    print("Searching PubMed for aesthetic medicine publications...")
    for i, q in enumerate(QUERIES, 1):
        print(f"  Query {i}/{len(QUERIES)}...")
        ids = esearch_pubmed(q, retmax=60)
        for pid in ids:
            if pid not in seen:
                seen.add(pid)
                pmids.append(pid)
        time.sleep(1)

    pmids = pmids[:max(target_total, 120)]
    print(f"Found {len(pmids)} unique PMIDs")

    input_path = "data/queue/input_120.txt"
    os.makedirs(os.path.dirname(input_path), exist_ok=True)
    with open(input_path, "w", encoding="utf-8") as f:
        f.write("# Auto-generated Veridoc list (PMIDs)\n")
        for pid in pmids[:target_total]:
            f.write(pid + "\n")

    print("Fetching metadata from PubMed...")
    meta = esummary_pubmed(pmids[:target_total])

    for m in meta:
        m["score"] = score_title(m.get("title", ""))
    meta.sort(key=lambda x: x.get("score", 0), reverse=True)

    top15 = meta[:15]

    out_jsonl = "data/queue/top15_metadata.jsonl"
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for m in top15:
            pmid = m["pmid"]
            year = m.get("year")
            title = m.get("title") or f"PubMed PMID {pmid}"
            journal = m.get("journal") or "PubMed"
            doi = m.get("doi")
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            if doi:
                url = f"{url} | DOI:{doi}"

            payload = {
                "source_id": make_source_id(pmid, year),
                "title": title,
                "authors": None,
                "organization_or_journal": journal,
                "year": year,
                "document_type": infer_document_type(title),
                "domain": "aesthetic_medicine",
                "version": "1.0",
                "url": url
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    print(f"\nGenerated:")
    print(f"  {input_path} ({len(pmids)} PMIDs)")
    print(f"  {out_jsonl} (Top 15 metadata)")
    print("\nTop 15 highest-scoring publications:")
    for i, m in enumerate(top15, 1):
        print(f"  {i:2}. [{m['score']:2}] {m['title'][:70]}...")
        print(f"      {m['journal']} ({m['year']})")

if __name__ == "__main__":
    main()
