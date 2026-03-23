import os, re, json, time, csv
import requests
from typing import List, Dict, Any, Tuple

NCBI_EMAIL = os.getenv("NCBI_EMAIL", "veridoc@example.com")
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")  # optional

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

# Strict keyword gate to keep results on-topic
INCLUDE_ANY = [
    "dermal filler", "facial filler", "hyaluronic acid filler", "soft tissue filler",
    "hyaluronidase", "vascular occlusion", "ischemia", "ischaemia", "necrosis",
    "vision loss", "blindness", "ophthalm", "retinal", "embol", "intravascular",
    "aesthetic", "cosmetic", "injectable", "filler-induced", "laser", "ipl"
]
EXCLUDE_ANY = [
    "mouse", "murine", "rat model", "zebrafish", "plant", "arctic", "astrocyte",
    "ecosystem", "peatland", "halogen bond", "bromine", "sulfur", "quantum",
    "nanoparticle", "polymer synthesis"
]

def ncbi_get(endpoint: str, params: Dict[str, Any]) -> str:
    params = dict(params)
    params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    r = requests.get(BASE + endpoint, params=params, timeout=40)
    r.raise_for_status()
    return r.text

def esearch(term: str, retmax: int = 60) -> List[str]:
    xml = ncbi_get("esearch.fcgi", {
        "db":"pubmed", "term": term, "retmode":"xml", "retmax": str(retmax), "sort":"relevance"
    })
    return re.findall(r"<Id>(\d+)</Id>", xml)

def esummary(pmids: List[str]) -> List[Dict[str, Any]]:
    out = []
    for i in range(0, len(pmids), 100):
        batch = pmids[i:i+100]
        xml = ncbi_get("esummary.fcgi", {"db":"pubmed", "id": ",".join(batch), "retmode":"xml"})
        # Split by DocSum blocks
        blocks = xml.split("<DocSum>")
        for b in blocks:
            mid = re.search(r"<Id>(\d+)</Id>", b)
            if not mid:
                continue
            pmid = mid.group(1)

            def item(name: str) -> str:
                m = re.search(rf'<Item Name="{re.escape(name)}" Type="[^"]+">(.+?)</Item>', b)
                return re.sub("<.*?>", "", m.group(1)).strip() if m else ""

            title = item("Title")
            journal = item("Source")
            pubdate = item("PubDate")
            year_m = re.search(r"(\d{4})", pubdate or "")
            year = int(year_m.group(1)) if year_m else None
            doi = item("DOI") or None

            out.append({
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "year": year,
                "doi": doi,
                "pubdate": pubdate or None
            })
        time.sleep(0.34)
    return out

def on_topic(title: str, journal: str) -> bool:
    t = (title or "").lower()
    j = (journal or "").lower()
    if any(x in t for x in EXCLUDE_ANY) or any(x in j for x in EXCLUDE_ANY):
        return False
    return any(x in t for x in INCLUDE_ANY) or any(x in j for x in ["dermatol", "aesthet", "cosmet", "laser"])

def score(title: str, journal: str) -> int:
    t = (title or "").lower()
    s = 0
    if any(k in t for k in ["guideline", "consensus", "position statement", "recommendation"]):
        s += 60
    if any(k in t for k in ["systematic review", "meta-analysis"]):
        s += 35
    if "review" in t:
        s += 20
    if any(k in t for k in ["vascular occlusion", "necrosis", "ischemia", "vision loss", "blindness", "hyaluronidase"]):
        s += 30
    if any(k in (journal or "").lower() for k in ["dermatol", "aesthet", "cosmetic", "plast", "laser"]):
        s += 10
    return s

def infer_document_type(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in ["guideline", "consensus", "position statement", "recommendation"]):
        return "consensus"
    if any(k in t for k in ["systematic review", "meta-analysis", "review"]):
        return "review"
    return "other"

def make_source_id(pmid: str, year: int | None) -> str:
    return f"pubmed_{pmid}_{year or 'nd'}"

def main():
    target = int(os.getenv("TARGET_PMIDS", "120"))

    # Carefully crafted PubMed queries (Title/Abstract constrained to reduce noise)
    QUERIES = [
        '(dermal filler[Title/Abstract] OR facial filler[Title/Abstract] OR hyaluronic acid filler[Title/Abstract]) AND (vascular occlusion[Title/Abstract] OR ischemia[Title/Abstract] OR necrosis[Title/Abstract])',
        '(hyaluronidase[Title/Abstract]) AND (dermal filler[Title/Abstract] OR hyaluronic acid[Title/Abstract] OR facial filler[Title/Abstract])',
        '(facial filler[Title/Abstract] OR dermal filler[Title/Abstract]) AND (vision loss[Title/Abstract] OR blindness[Title/Abstract] OR ophthalm*[Title/Abstract])',
        '(laser[Title/Abstract] OR IPL[Title/Abstract] OR "intense pulsed light"[Title/Abstract]) AND (burn[Title/Abstract] OR complication[Title/Abstract] OR safety[Title/Abstract]) AND dermatology[Title/Abstract]',
        '(filler complication*[Title/Abstract] OR dermal filler complication*[Title/Abstract]) AND (review[Title/Abstract] OR guideline[Title/Abstract] OR consensus[Title/Abstract])',
    ]

    # Verified seed PMIDs (hard anchor)
    seed = ["38231537", "34852044", "38131127", "31822960"]

    seen = set(seed)
    pmids = seed[:]

    # Collect candidate PMIDs
    for q in QUERIES:
        ids = esearch(q, retmax=80)
        for pid in ids:
            if pid not in seen:
                seen.add(pid)
                pmids.append(pid)
        time.sleep(0.34)

    # Pull metadata and filter aggressively
    meta = esummary(pmids)
    filtered = [m for m in meta if on_topic(m.get("title",""), m.get("journal",""))]

    # Score + sort
    for m in filtered:
        m["score"] = score(m.get("title",""), m.get("journal",""))
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Keep top target
    filtered = filtered[:target]

    # Write copy-paste PMID list
    pmid_out = "data/queue/input_verified_120.txt"
    with open(pmid_out, "w", encoding="utf-8") as f:
        f.write("# Veridoc verified PMIDs (filtered to derm/aesthetic topics)\n")
        for m in filtered:
            f.write(m["pmid"] + "\n")

    # Write top 15 metadata JSONL (ready for /admin/ingest_pdf metadata_json)
    top15 = filtered[:15]
    jsonl_out = "data/queue/top15_metadata.jsonl"
    with open(jsonl_out, "w", encoding="utf-8") as f:
        for m in top15:
            pmid = m["pmid"]
            year = m.get("year")
            title = m.get("title") or f"PubMed PMID {pmid}"
            journal = m.get("journal") or "PubMed"
            doi = m.get("doi")
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" + (f" | DOI:{doi}" if doi else "")

            payload = {
                "source_id": make_source_id(pmid, year),
                "title": title,
                "authors": None,
                "organization_or_journal": journal,
                "year": year,
                "document_type": infer_document_type(title),
                "domain": "aesthetic_medicine",
                "version": "ERAU-access",
                "url": url
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    # Also write a CSV for review
    csv_out = "data/queue/verified_120_with_titles.csv"
    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["score","pmid","year","journal","title","doi"])
        w.writeheader()
        for m in filtered:
            w.writerow({
                "score": m.get("score",0),
                "pmid": m.get("pmid",""),
                "year": m.get("year",""),
                "journal": m.get("journal",""),
                "title": m.get("title",""),
                "doi": m.get("doi","") or ""
            })

    print("✅ Outputs created:")
    print(f"- {pmid_out} (copy/paste PMIDs)")
    print(f"- {csv_out} (titles for sanity check)")
    print(f"- {jsonl_out} (top-15 metadata JSONL)")
    print("\nNext:")
    print("1) Open verified_120_with_titles.csv and spot-check the first 20 titles.")
    print("2) Download PDFs legally via ERAU for the top 15.")
    print("3) Upload each with /admin/ingest_pdf using metadata_json from top15_metadata.jsonl")

if __name__ == "__main__":
    main()
