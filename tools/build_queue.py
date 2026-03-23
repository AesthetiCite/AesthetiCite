import os
import re
import time
import csv
import requests
from urllib.parse import quote

NCBI_EMAIL = os.getenv("NCBI_EMAIL", "veridoc@example.com")
API_KEY = os.getenv("NCBI_API_KEY", "")

def is_doi(s: str) -> bool:
    return bool(re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", s, re.I))

def is_pmid(s: str) -> bool:
    return s.isdigit() and 6 <= len(s) <= 9

def ncbi_get(url: str, params: dict, retries: int = 3):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    params = dict(params)
    params["email"] = NCBI_EMAIL
    if API_KEY:
        params["api_key"] = API_KEY
    
    for attempt in range(retries):
        try:
            r = requests.get(base + url, params=params, timeout=30)
            if r.status_code == 429:
                wait_time = (attempt + 1) * 5
                print(f"Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            r.raise_for_status()
            return r.text
        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise
    return ""

def doi_to_pmid(doi: str) -> str | None:
    term = f"{doi}[DOI]"
    xml = ncbi_get("esearch.fcgi", {"db":"pubmed", "term": term, "retmode":"xml"})
    m = re.search(r"<Id>(\d+)</Id>", xml)
    return m.group(1) if m else None

def fetch_pubmed_summary(pmid: str) -> dict:
    xml = ncbi_get("esummary.fcgi", {"db":"pubmed", "id": pmid, "retmode":"xml"})
    def tag(name):
        m = re.search(rf'<Item Name="{name}" Type="[^"]+">(.+?)</Item>', xml)
        return re.sub("<.*?>", "", m.group(1)).strip() if m else ""
    title = tag("Title")
    source = tag("Source")
    pubdate = tag("PubDate")
    doi = ""
    doi_m = re.search(r'<Item Name="DOI" Type="String">(.+?)</Item>', xml)
    if doi_m:
        doi = doi_m.group(1).strip()
    year_m = re.search(r"(\d{4})", pubdate)
    year = year_m.group(1) if year_m else ""
    return {
        "pmid": pmid,
        "doi": doi,
        "title": title,
        "journal": source,
        "year": year,
    }

def pmid_to_pmcid(pmid: str) -> str | None:
    url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
    params = {"ids": pmid, "format": "json"}
    if API_KEY:
        params["api_key"] = API_KEY
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    js = r.json()
    rec = js.get("records", [{}])[0]
    return rec.get("pmcid")

def pmc_pdf_url(pmcid: str) -> str:
    page = requests.get(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/", timeout=30).text
    m = re.search(r'href="([^"]+\.pdf)"', page, re.I)
    if not m:
        return ""
    href = m.group(1)
    if href.startswith("http"):
        return href
    return "https://pmc.ncbi.nlm.nih.gov" + href

def score_row(journal: str, title: str) -> int:
    t = (title or "").lower()
    j = (journal or "").lower()
    score = 0
    if any(k in t for k in ["guideline", "consensus", "position statement", "recommendation"]):
        score += 40
    if "review" in t or "systematic" in t or "meta-analysis" in t:
        score += 25
    if any(k in t for k in ["complication", "vascular", "occlusion", "necrosis", "blindness", "ischemia", "laser", "burn"]):
        score += 25
    if any(k in j for k in ["dermatol", "aesthetic", "cosmetic", "laser", "plast"]):
        score += 10
    return score

def main():
    input_path = os.getenv("VERIDOC_INPUT", "data/queue/input.txt")
    out_csv = os.getenv("VERIDOC_OUTPUT", "data/queue/veridoc_queue.csv")
    download_open_pmc = os.getenv("DOWNLOAD_PMC", "false").lower() == "true"

    if not os.path.exists(input_path):
        os.makedirs(os.path.dirname(input_path), exist_ok=True)
        with open(input_path, "w", encoding="utf-8") as f:
            f.write("# Paste one DOI or PMID per line\n")
        print(f"Created {input_path}. Add DOIs/PMIDs then re-run.")
        return

    items = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            items.append(line)

    if not items:
        print("No DOIs/PMIDs found in input.txt. Add some and re-run.")
        return

    rows = []
    for it in items:
        pmid = None
        if is_pmid(it):
            pmid = it
        elif is_doi(it):
            pmid = doi_to_pmid(it)
        else:
            pmid = doi_to_pmid(it)

        if not pmid:
            rows.append({
                "source_id": "",
                "title": "",
                "authors": "",
                "organization_or_journal": "",
                "year": "",
                "document_type": "other",
                "domain": "aesthetic_medicine",
                "version": "queue",
                "url": it,
                "pdf_path": "",
                "pmid": "",
                "doi": it,
                "pmcid": "",
                "open_access_pmc": "no",
                "pmc_pdf_url": "",
                "score": 0,
                "notes": "Could not resolve to PMID"
            })
            continue

        meta = fetch_pubmed_summary(pmid)
        pmcid = pmid_to_pmcid(pmid)
        open_access = "yes" if pmcid else "no"
        pdfurl = pmc_pdf_url(pmcid) if pmcid else ""
        score = score_row(meta.get("journal",""), meta.get("title",""))

        year = meta.get("year","") or "nd"
        sid = f"pubmed_{pmid}_{year}".lower()

        row = {
            "source_id": sid,
            "title": meta.get("title",""),
            "authors": "",
            "organization_or_journal": meta.get("journal",""),
            "year": meta.get("year",""),
            "document_type": "review" if "review" in (meta.get("title","").lower()) else "other",
            "domain": "aesthetic_medicine",
            "version": "queue",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "pdf_path": "",
            "pmid": pmid,
            "doi": meta.get("doi","") or "",
            "pmcid": pmcid or "",
            "open_access_pmc": open_access,
            "pmc_pdf_url": pdfurl,
            "score": score,
            "notes": ""
        }
        rows.append(row)

        if download_open_pmc and pmcid and pdfurl:
            try:
                fn = f"{pmcid}.pdf"
                out = os.path.join("data/pmc_downloads", fn)
                if not os.path.exists(out):
                    r = requests.get(pdfurl, timeout=60)
                    r.raise_for_status()
                    with open(out, "wb") as f:
                        f.write(r.content)
                row["pdf_path"] = os.path.abspath(out)
                row["notes"] = "PMC PDF downloaded (open access)"
            except Exception as e:
                row["notes"] = f"PMC download failed: {e}"

        time.sleep(1.0)  # Polite delay to avoid rate limiting

    rows.sort(key=lambda x: x.get("score", 0), reverse=True)

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"Queue created: {out_csv}")
    print("Top 10 (by score):")
    for r in rows[:10]:
        print(f"- {r['score']:>3} | {r['pmid']} | {r['year']} | {r['title'][:90]}{'...' if len(r['title'])>90 else ''}")

    print("\nNext step:")
    print("- Review veridoc_queue.csv")
    print("- For rows with pdf_path filled (PMC open access), bulk ingest using bulk_ingest.py")
    print("- For paywalled items, download legally then fill pdf_path and ingest.")

if __name__ == "__main__":
    main()
