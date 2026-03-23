"""
AesthetiCite Growth Engine v2.0.0 — PostgreSQL
================================================
Complete rewrite of growth_engine.py replacing SQLite with PostgreSQL.
Keeps every endpoint, route prefix, and response model identical —
fully backward-compatible drop-in replacement.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import statistics
import textwrap
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

router = APIRouter(prefix="/api/growth", tags=["AesthetiCite Growth Engine"])

EXPORT_DIR = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "")


# ─── Database ─────────────────────────────────────────────────────────────────

def get_conn() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def init_db() -> None:
    """Create all growth engine tables in PostgreSQL. Idempotent."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS growth_bookmarks (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     TEXT NOT NULL,
            title       TEXT NOT NULL,
            question    TEXT NOT NULL,
            answer_json JSONB NOT NULL DEFAULT '{}',
            tags        JSONB NOT NULL DEFAULT '[]',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON growth_bookmarks(user_id);

        CREATE TABLE IF NOT EXISTS growth_session_reports (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id     TEXT,
            clinician_id  TEXT,
            title         TEXT NOT NULL,
            report_date   DATE,
            notes         TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_sreports_clinic ON growth_session_reports(clinic_id);

        CREATE TABLE IF NOT EXISTS growth_session_report_items (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_id                UUID NOT NULL REFERENCES growth_session_reports(id) ON DELETE CASCADE,
            patient_label            TEXT,
            procedure                TEXT NOT NULL,
            region                   TEXT NOT NULL,
            product_type             TEXT NOT NULL,
            technique                TEXT,
            injector_experience_level TEXT,
            engine_response          JSONB NOT NULL DEFAULT '{}',
            created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_sritems_report ON growth_session_report_items(report_id);

        CREATE TABLE IF NOT EXISTS growth_query_logs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id        TEXT,
            clinician_id     TEXT,
            query_text       TEXT NOT NULL,
            answer_type      TEXT,
            aci_score        REAL,
            response_time_ms REAL,
            evidence_level   TEXT,
            domain           TEXT DEFAULT 'aesthetic_medicine',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_qlogs_clinic   ON growth_query_logs(clinic_id);
        CREATE INDEX IF NOT EXISTS idx_qlogs_created  ON growth_query_logs(created_at DESC);

        CREATE TABLE IF NOT EXISTS growth_patient_exports (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id    TEXT,
            clinician_id TEXT,
            source_title TEXT NOT NULL,
            source_text  TEXT NOT NULL,
            patient_text TEXT NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS growth_api_keys (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id  TEXT NOT NULL,
            label      TEXT NOT NULL,
            key_hash   TEXT NOT NULL UNIQUE,
            is_active  BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_apikeys_hash ON growth_api_keys(key_hash);

        CREATE TABLE IF NOT EXISTS growth_paper_subscriptions (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          TEXT NOT NULL,
            topic            TEXT NOT NULL,
            email            TEXT,
            last_checked_at  TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_psubs_user ON growth_paper_subscriptions(user_id);

        CREATE TABLE IF NOT EXISTS growth_paper_alert_items (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subscription_id UUID NOT NULL REFERENCES growth_paper_subscriptions(id) ON DELETE CASCADE,
            paper_title     TEXT NOT NULL,
            paper_abstract  TEXT,
            source_url      TEXT,
            published_date  TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS growth_knowledge_chunks (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title       TEXT NOT NULL,
            content     TEXT NOT NULL,
            source_type TEXT,
            source_ref  TEXT,
            tags        JSONB NOT NULL DEFAULT '[]',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()


try:
    if DATABASE_URL:
        init_db()
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning(f"[growth-engine] DB init deferred: {_e}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ─── Models ───────────────────────────────────────────────────────────────────

class BookmarkCreate(BaseModel):
    user_id: str
    title: str
    question: str
    answer_json: Dict[str, Any]
    tags: List[str] = Field(default_factory=list)


class BookmarkResponse(BaseModel):
    id: str
    user_id: str
    title: str
    question: str
    answer_json: Dict[str, Any]
    tags: List[str]
    created_at_utc: str


class SessionReportCreate(BaseModel):
    clinic_id: Optional[str] = None
    clinician_id: Optional[str] = None
    title: str
    report_date: Optional[str] = None
    notes: Optional[str] = None


class SessionReportItemCreate(BaseModel):
    patient_label: Optional[str] = None
    procedure: str
    region: str
    product_type: str
    technique: Optional[str] = None
    injector_experience_level: Optional[str] = None
    engine_response_json: Dict[str, Any]


class SessionReportResponse(BaseModel):
    id: str
    clinic_id: Optional[str] = None
    clinician_id: Optional[str] = None
    title: str
    report_date: Optional[str] = None
    notes: Optional[str] = None
    created_at_utc: str


class SessionReportItemResponse(BaseModel):
    id: str
    report_id: str
    patient_label: Optional[str] = None
    procedure: str
    region: str
    product_type: str
    technique: Optional[str] = None
    injector_experience_level: Optional[str] = None
    engine_response_json: Dict[str, Any]
    created_at_utc: str


class QueryLogCreate(BaseModel):
    clinic_id: Optional[str] = None
    clinician_id: Optional[str] = None
    query_text: str
    answer_type: str = "evidence_search"
    aci_score: Optional[float] = None
    response_time_ms: Optional[float] = None
    evidence_level: Optional[str] = None
    domain: Optional[str] = "aesthetic_medicine"


class DashboardResponse(BaseModel):
    total_queries: int
    average_aci_score: Optional[float] = None
    average_response_time_ms: Optional[float] = None
    top_questions: List[Dict[str, Any]]
    evidence_level_distribution: Dict[str, int]
    answer_type_distribution: Dict[str, int]


class PatientReadableRequest(BaseModel):
    clinic_id: Optional[str] = None
    clinician_id: Optional[str] = None
    source_title: str
    source_text: str


class PatientReadableResponse(BaseModel):
    id: str
    patient_text: str
    created_at_utc: str


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    use_hnsw: bool = True


class SearchResultItem(BaseModel):
    chunk_id: str
    title: str
    snippet: str
    source_type: Optional[str] = None
    source_ref: Optional[str] = None
    score: float


class SearchResponse(BaseModel):
    mode: str
    results: List[SearchResultItem]


class APIKeyCreateRequest(BaseModel):
    clinic_id: str
    label: str


class APIKeyCreateResponse(BaseModel):
    id: str
    clinic_id: str
    label: str
    api_key: str
    created_at_utc: str


class PaperAlertSubscribeRequest(BaseModel):
    user_id: str
    topic: str
    email: Optional[str] = None


class PaperAlertSubscriptionResponse(BaseModel):
    id: str
    user_id: str
    topic: str
    email: Optional[str] = None
    last_checked_utc: Optional[str] = None
    created_at_utc: str


class PaperAlertDigestResponse(BaseModel):
    subscription_id: str
    topic: str
    new_items: List[Dict[str, Any]]


class DrugInteractionRequest(BaseModel):
    medications: List[str] = Field(default_factory=list)
    planned_products: List[str] = Field(default_factory=list)


class DrugInteractionItem(BaseModel):
    medication: str
    product_or_context: str
    severity: Literal["low", "moderate", "high"]
    explanation: str
    action: str


class DrugInteractionResponse(BaseModel):
    items: List[DrugInteractionItem]
    summary: str


# ─── PDF helper ───────────────────────────────────────────────────────────────

class PDFWriter:
    def __init__(self, path: str) -> None:
        self.c = canvas.Canvas(path, pagesize=A4)
        self.w, self.h = A4
        self.left = 18 * mm
        self.right = self.w - 18 * mm
        self.top = self.h - 18 * mm
        self.bottom = 18 * mm
        self.y = self.top

    def _ensure(self, needed: float) -> None:
        if self.y - needed < self.bottom:
            self.c.showPage()
            self.y = self.top

    def line(self, text: str, font: str = "Helvetica", size: int = 10, leading: int = 14) -> None:
        self._ensure(leading)
        self.c.setFont(font, size)
        self.c.drawString(self.left, self.y, str(text)[:180])
        self.y -= leading

    def wrapped(self, text: str, font: str = "Helvetica", size: int = 10,
                leading: int = 14, bullet: Optional[str] = None) -> None:
        max_w = self.right - self.left
        self.c.setFont(font, size)
        prefix = f"{bullet} " if bullet else ""
        indent = stringWidth(prefix, font, size) if bullet else 0
        usable = max_w - indent
        words = str(text).split()
        cur = ""
        first = True

        def flush(t: str, is_first: bool) -> None:
            self._ensure(leading)
            self.c.setFont(font, size)
            x = self.left + (indent if bullet and not is_first else 0)
            self.c.drawString(x, self.y, (prefix if bullet and is_first else "") + t)
            self.y -= leading

        for w in words:
            cand = w if not cur else f"{cur} {w}"
            if stringWidth(cand, font, size) <= usable:
                cur = cand
            else:
                flush(cur, first); first = False; cur = w
        if cur:
            flush(cur, first)

    def section(self, title: str) -> None:
        self.y -= 4
        self.line(title, font="Helvetica-Bold", size=12, leading=16)

    def save(self) -> None:
        self.c.save()


# ─── API key auth ─────────────────────────────────────────────────────────────

def get_api_key_record(x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header.")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM growth_api_keys WHERE key_hash = %s AND is_active = TRUE",
        (hash_api_key(x_api_key),)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return dict(row)


# ─── Drug interaction adapter ─────────────────────────────────────────────────

DRUG_HIGH = {"warfarin", "acenocoumarol", "apixaban", "rivaroxaban", "dabigatran",
             "edoxaban", "heparin", "enoxaparin", "tinzaparin", "dalteparin",
             "methotrexate", "azathioprine", "ciclosporin", "tacrolimus",
             "mycophenolate", "isotretinoin", "roaccutane"}

DRUG_MODERATE = {"aspirin", "clopidogrel", "ticagrelor", "prasugrel",
                 "ibuprofen", "naproxen", "diclofenac", "celecoxib",
                 "sertraline", "fluoxetine", "escitalopram", "citalopram",
                 "paroxetine", "venlafaxine", "duloxetine",
                 "prednisolone", "prednisone", "dexamethasone"}

DRUG_LOW = {"vitamin e", "fish oil", "omega 3", "omega-3", "ginkgo", "garlic supplement"}

DRUG_EXPLANATIONS: Dict[str, str] = {
    "warfarin": "Vitamin K antagonist — substantially increases bruising and bleeding risk.",
    "acenocoumarol": "Vitamin K antagonist — substantially increases bruising and bleeding risk.",
    "apixaban": "NOAC — significantly increases procedural bleeding risk.",
    "rivaroxaban": "NOAC — significantly increases procedural bleeding risk.",
    "dabigatran": "NOAC — significantly increases procedural bleeding risk.",
    "edoxaban": "NOAC — significantly increases procedural bleeding risk.",
    "heparin": "Injectable anticoagulant — significantly increases bleeding risk.",
    "enoxaparin": "LMWH — significantly increases bleeding risk.",
    "tinzaparin": "LMWH — significantly increases bleeding risk.",
    "dalteparin": "LMWH — significantly increases bleeding risk.",
    "aspirin": "Antiplatelet — increases bruising risk. Do not stop without prescriber approval.",
    "clopidogrel": "Antiplatelet — increases bruising risk. Do not stop without prescriber approval.",
    "ticagrelor": "Antiplatelet — increases bruising risk. Do not stop without prescriber approval.",
    "prasugrel": "Antiplatelet — increases bruising risk. Do not stop without prescriber approval.",
    "ibuprofen": "NSAID — inhibits platelet function, increases bruising.",
    "naproxen": "NSAID — inhibits platelet function, increases bruising.",
    "diclofenac": "NSAID — inhibits platelet function, increases bruising.",
    "celecoxib": "COX-2 inhibitor — moderate platelet effect.",
    "sertraline": "SSRI — reduces platelet aggregation, increases bruising.",
    "fluoxetine": "SSRI — reduces platelet aggregation, increases bruising.",
    "escitalopram": "SSRI — reduces platelet aggregation, increases bruising.",
    "citalopram": "SSRI — reduces platelet aggregation, increases bruising.",
    "paroxetine": "SSRI — reduces platelet aggregation, increases bruising.",
    "venlafaxine": "SNRI — reduces platelet aggregation, increases bruising.",
    "duloxetine": "SNRI — reduces platelet aggregation, increases bruising.",
    "prednisolone": "Long-term steroid — impairs healing and immune response.",
    "prednisone": "Long-term steroid — impairs healing and immune response.",
    "dexamethasone": "Corticosteroid — impairs healing, increased infection risk.",
    "methotrexate": "Immunosuppressant — increased infection and poor healing risk.",
    "azathioprine": "Immunosuppressant — increased infection and poor healing risk.",
    "ciclosporin": "Immunosuppressant — increased infection and poor healing risk.",
    "tacrolimus": "Immunosuppressant — increased infection and poor healing risk.",
    "mycophenolate": "Immunosuppressant — increased infection and poor healing risk.",
    "isotretinoin": "Impairs wound healing — defer ablative procedures 6–12 months after stopping.",
    "roaccutane": "Impairs wound healing — defer ablative procedures 6–12 months after stopping.",
    "vitamin e": "May mildly increase bruising — stop 1 week before if possible.",
    "fish oil": "May mildly increase bruising — stop 1 week before if possible.",
    "omega 3": "May mildly increase bruising — stop 1 week before if possible.",
    "omega-3": "May mildly increase bruising — stop 1 week before if possible.",
    "ginkgo": "May mildly increase bruising — stop 1 week before if possible.",
    "garlic supplement": "May mildly increase bruising — stop 1 week before if possible.",
}

DRUG_ACTIONS = {
    "high": "Review with prescribing clinician. Document in consent. Do not stop anticoagulation without medical approval.",
    "moderate": "Warn patient about increased bruising. Document. Do not stop prescribed medication without prescriber advice.",
    "low": "Advise stopping 1 week before treatment if safe to do so. Note in records.",
}


def check_drug_interactions(
    medications: List[str], planned_products: List[str]
) -> List[DrugInteractionItem]:
    items = []
    prods = planned_products or ["injectable aesthetic procedure"]
    for med in medications:
        med_n = normalize(med)
        sev: Optional[str] = None
        matched_key: Optional[str] = None
        for drug in DRUG_HIGH:
            if drug in med_n or med_n in drug:
                sev = "high"; matched_key = drug; break
        if not sev:
            for drug in DRUG_MODERATE:
                if drug in med_n or med_n in drug:
                    sev = "moderate"; matched_key = drug; break
        if not sev:
            for drug in DRUG_LOW:
                if drug in med_n or med_n in drug:
                    sev = "low"; matched_key = drug; break
        if sev and matched_key:
            explanation = DRUG_EXPLANATIONS.get(matched_key, f"{med} may affect procedural safety.")
            action = DRUG_ACTIONS[sev]
            for prod in prods:
                items.append(DrugInteractionItem(
                    medication=med,
                    product_or_context=prod,
                    severity=sev,
                    explanation=explanation,
                    action=action,
                ))
    return items


# ─── PubMed adapter ───────────────────────────────────────────────────────────

def search_new_papers(topic: str, since_utc: Optional[str]) -> List[Dict[str, Any]]:
    import requests
    from datetime import datetime as _dt
    api_key = os.environ.get("NCBI_API_KEY", "")
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    min_date = "2024/01/01"
    if since_utc:
        try:
            d = _dt.fromisoformat(since_utc.replace("Z", "+00:00"))
            min_date = d.strftime("%Y/%m/%d")
        except Exception:  # nosec B110
            pass
    today = _dt.utcnow().strftime("%Y/%m/%d")
    params: Dict[str, str] = {
        "db": "pubmed", "term": f'("{topic}"[Title/Abstract]) AND aesthetic medicine',
        "retmax": "6", "sort": "pub date", "retmode": "json",
        "mindate": min_date, "maxdate": today, "datetype": "pdat",
    }
    if api_key:
        params["api_key"] = api_key
    try:
        r = requests.get(f"{base}/esearch.fcgi", params=params, timeout=8)
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
    except Exception:
        return []
    if not ids:
        return []
    try:
        p2: Dict[str, str] = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
        if api_key:
            p2["api_key"] = api_key
        r2 = requests.get(f"{base}/esummary.fcgi", params=p2, timeout=8)
        r2.raise_for_status()
        result_data = r2.json().get("result", {})
    except Exception:
        return []
    papers = []
    for pmid in ids:
        entry = result_data.get(pmid, {})
        if not entry or "error" in entry:
            continue
        title = entry.get("title", "").rstrip(".")
        papers.append({
            "title": title or f"PubMed {pmid}",
            "abstract": f"{entry.get('source','')}. {entry.get('pubdate','')}".strip(". "),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "published_date": entry.get("pubdate", ""),
        })
    return papers


# ─── HNSW adapter (pgvector-backed keyword fallback) ─────────────────────────

def hnsw_search(query: str, top_k: int) -> List[SearchResultItem]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id::text, title, content, source_type, source_ref FROM growth_knowledge_chunks LIMIT 200")
    rows = cur.fetchall()
    conn.close()
    terms = set(normalize(query).split())
    scored = []
    for row in rows:
        content_n = normalize(row["content"])
        title_n = normalize(row["title"])
        score = sum(1 for t in terms if t in content_n or t in title_n)
        if score > 0:
            scored.append(SearchResultItem(
                chunk_id=row["id"],
                title=row["title"],
                snippet=row["content"][:240],
                source_type=row["source_type"],
                source_ref=row["source_ref"],
                score=float(score),
            ))
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


# ─── Endpoints ────────────────────────────────────────────────────────────────

# 2. Bookmarks

@router.post("/bookmarks", response_model=BookmarkResponse)
def create_bookmark(payload: BookmarkCreate) -> BookmarkResponse:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        INSERT INTO growth_bookmarks (user_id, title, question, answer_json, tags)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
        RETURNING id::text, user_id, title, question, answer_json, tags, created_at
    """, (payload.user_id, payload.title, payload.question,
          json.dumps(payload.answer_json), json.dumps(payload.tags)))
    row = cur.fetchone()
    conn.commit(); conn.close()
    return BookmarkResponse(
        id=row["id"], user_id=row["user_id"], title=row["title"],
        question=row["question"], answer_json=row["answer_json"],
        tags=row["tags"], created_at_utc=row["created_at"].isoformat(),
    )


@router.get("/bookmarks/{user_id}", response_model=List[BookmarkResponse])
def list_bookmarks(user_id: str) -> List[BookmarkResponse]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id::text, user_id, title, question, answer_json, tags, created_at
        FROM growth_bookmarks WHERE user_id = %s ORDER BY created_at DESC
    """, (user_id,))
    rows = cur.fetchall(); conn.close()
    return [BookmarkResponse(
        id=r["id"], user_id=r["user_id"], title=r["title"],
        question=r["question"], answer_json=r["answer_json"],
        tags=r["tags"], created_at_utc=r["created_at"].isoformat(),
    ) for r in rows]


@router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: str) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM growth_bookmarks WHERE id = %s", (bookmark_id,))
    conn.commit(); conn.close()
    return {"status": "ok", "deleted_id": bookmark_id}


# 3. Session safety reports

@router.post("/session-reports", response_model=SessionReportResponse)
def create_session_report(payload: SessionReportCreate) -> SessionReportResponse:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        INSERT INTO growth_session_reports (clinic_id, clinician_id, title, report_date, notes)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id::text, clinic_id, clinician_id, title, report_date::text, notes, created_at
    """, (payload.clinic_id, payload.clinician_id, payload.title,
          payload.report_date, payload.notes))
    row = cur.fetchone(); conn.commit(); conn.close()
    return SessionReportResponse(
        id=row["id"], clinic_id=row["clinic_id"], clinician_id=row["clinician_id"],
        title=row["title"], report_date=row["report_date"],
        notes=row["notes"], created_at_utc=row["created_at"].isoformat(),
    )


@router.post("/session-reports/{report_id}/items", response_model=SessionReportItemResponse)
def add_session_report_item(report_id: str, payload: SessionReportItemCreate) -> SessionReportItemResponse:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id FROM growth_session_reports WHERE id = %s", (report_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found.")
    cur.execute("""
        INSERT INTO growth_session_report_items
            (report_id, patient_label, procedure, region, product_type,
             technique, injector_experience_level, engine_response)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id::text, report_id::text, patient_label, procedure, region,
                  product_type, technique, injector_experience_level,
                  engine_response, created_at
    """, (report_id, payload.patient_label, payload.procedure, payload.region,
          payload.product_type, payload.technique, payload.injector_experience_level,
          json.dumps(payload.engine_response_json)))
    row = cur.fetchone(); conn.commit(); conn.close()
    return SessionReportItemResponse(
        id=row["id"], report_id=row["report_id"], patient_label=row["patient_label"],
        procedure=row["procedure"], region=row["region"], product_type=row["product_type"],
        technique=row["technique"], injector_experience_level=row["injector_experience_level"],
        engine_response_json=row["engine_response"], created_at_utc=row["created_at"].isoformat(),
    )


@router.get("/session-reports/{report_id}")
def get_session_report(report_id: str) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id::text, clinic_id, clinician_id, title, report_date::text, notes, created_at
        FROM growth_session_reports WHERE id = %s
    """, (report_id,))
    report = cur.fetchone()
    if not report:
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found.")
    cur.execute("""
        SELECT id::text, report_id::text, patient_label, procedure, region,
               product_type, technique, injector_experience_level,
               engine_response, created_at
        FROM growth_session_report_items
        WHERE report_id = %s ORDER BY created_at ASC
    """, (report_id,))
    items = cur.fetchall(); conn.close()
    return {
        "report": {**dict(report), "created_at_utc": report["created_at"].isoformat()},
        "items": [{**dict(i), "engine_response_json": i["engine_response"],
                   "created_at_utc": i["created_at"].isoformat()} for i in items],
    }


@router.post("/session-reports/{report_id}/export-pdf")
def export_session_report_pdf(report_id: str) -> Dict[str, Any]:
    payload = get_session_report(report_id)
    report = payload["report"]
    items = payload["items"]
    filename = f"session_report_{report_id}.pdf"
    pdf_path = os.path.join(EXPORT_DIR, filename)
    pdf = PDFWriter(pdf_path)
    pdf.line("AesthetiCite Session Safety Report", font="Helvetica-Bold", size=16, leading=20)
    pdf.line(f"Title: {report['title']}", font="Helvetica-Bold")
    pdf.line(f"Date: {report.get('report_date') or ''}")
    if report.get("notes"):
        pdf.section("Notes"); pdf.wrapped(report["notes"])
    for idx, item in enumerate(items, 1):
        eng = item.get("engine_response_json", {})
        pdf.section(f"Procedure {idx} — {item.get('patient_label') or 'Patient'}")
        pdf.wrapped(f"Procedure: {item['procedure']}", bullet="•")
        pdf.wrapped(f"Region: {item['region']}", bullet="•")
        pdf.wrapped(f"Product: {item['product_type']}", bullet="•")
        if isinstance(eng, dict):
            sa = eng.get("safety_assessment", {})
            if sa:
                pdf.wrapped(
                    f"Decision: {sa.get('decision','N/A')} | Risk: {sa.get('overall_risk_score','N/A')}/100",
                    font="Helvetica-Bold", bullet="→"
                )
            for risk in eng.get("top_risks", [])[:5]:
                pdf.wrapped(f"{risk.get('complication','')}: {risk.get('risk_score','')}/100", bullet="•")
            for step in eng.get("mitigation_steps", [])[:6]:
                pdf.wrapped(step, bullet="•")
    pdf.save()
    try:
        from app.api.operational import pdf_storage
        url = pdf_storage.save(pdf_path, filename)
    except Exception:
        url = f"/exports/{filename}"
    return {"report_id": report_id, "filename": filename, "url": url}


# 4. Clinic dashboard

@router.post("/query-logs")
def create_query_log(payload: QueryLogCreate) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO growth_query_logs
            (clinic_id, clinician_id, query_text, answer_type,
             aci_score, response_time_ms, evidence_level, domain)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id::text
    """, (payload.clinic_id, payload.clinician_id, payload.query_text,
          payload.answer_type, payload.aci_score, payload.response_time_ms,
          payload.evidence_level, payload.domain))
    rec_id = cur.fetchone()[0]; conn.commit(); conn.close()
    return {"status": "ok", "id": rec_id}


@router.get("/dashboard/{clinic_id}", response_model=DashboardResponse)
def clinic_dashboard(clinic_id: str) -> DashboardResponse:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT query_text, answer_type, aci_score, response_time_ms, evidence_level
        FROM growth_query_logs WHERE clinic_id = %s
    """, (clinic_id,))
    rows = cur.fetchall(); conn.close()
    total = len(rows)
    aci_vals = [float(r["aci_score"]) for r in rows if r["aci_score"] is not None]
    rt_vals = [float(r["response_time_ms"]) for r in rows if r["response_time_ms"] is not None]
    top_questions = [{"query": q, "count": c}
                     for q, c in Counter(r["query_text"] for r in rows).most_common(10)]
    return DashboardResponse(
        total_queries=total,
        average_aci_score=round(statistics.mean(aci_vals), 2) if aci_vals else None,
        average_response_time_ms=round(statistics.mean(rt_vals), 2) if rt_vals else None,
        top_questions=top_questions,
        evidence_level_distribution=dict(Counter(r["evidence_level"] for r in rows if r["evidence_level"])),
        answer_type_distribution=dict(Counter(r["answer_type"] for r in rows if r["answer_type"])),
    )


# 5. Patient-readable export

def simplify_for_patient(title: str, source_text: str) -> str:
    clean = " ".join(source_text.replace("\n", " ").strip().split())
    short = textwrap.shorten(clean, width=1200, placeholder="...")
    return (
        f"{title}\n\nPatient summary:\n"
        "This information explains the treatment or clinical point in simpler language.\n\n"
        f"{short}\n\nWhat this means for you:\n"
        "• Your clinician is using this information to improve safety and decision-making.\n"
        "• The exact treatment decision still depends on your own medical situation.\n"
        "• Ask your clinician if you want the risks, benefits, and alternatives explained for your case."
    )


@router.post("/patient-readable-export", response_model=PatientReadableResponse)
def patient_readable_export(payload: PatientReadableRequest) -> PatientReadableResponse:
    patient_text = simplify_for_patient(payload.source_title, payload.source_text)
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        INSERT INTO growth_patient_exports
            (clinic_id, clinician_id, source_title, source_text, patient_text)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id::text, patient_text, created_at
    """, (payload.clinic_id, payload.clinician_id,
          payload.source_title, payload.source_text, patient_text))
    row = cur.fetchone(); conn.commit(); conn.close()
    return PatientReadableResponse(
        id=row["id"], patient_text=row["patient_text"],
        created_at_utc=row["created_at"].isoformat(),
    )


@router.get("/patient-readable-export/{export_id}")
def get_patient_export(export_id: str) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id::text, clinic_id, patient_text, created_at FROM growth_patient_exports WHERE id = %s",
        (export_id,)
    )
    row = cur.fetchone(); conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Export not found.")
    return {**dict(row), "created_at_utc": row["created_at"].isoformat()}


# 6. PWA manifest (served primarily via Express, but also available here)

@router.get("/pwa/manifest.json")
def pwa_manifest() -> Dict[str, Any]:
    return {
        "name": "AesthetiCite",
        "short_name": "AesthetiCite",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#6366f1",
        "description": "Clinical safety and evidence engine for aesthetic injectables.",
        "icons": [
            {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
        "categories": ["medical", "health"],
        "shortcuts": [
            {"name": "Safety Check", "url": "/safety-workspace", "description": "Run pre-procedure safety check"},
            {"name": "Complications", "url": "/clinical-tools", "description": "Complication protocols"},
        ],
    }


# 7. HNSW search

@router.post("/search", response_model=SearchResponse)
def search_knowledge(payload: SearchRequest) -> SearchResponse:
    results = hnsw_search(payload.query, payload.top_k)
    return SearchResponse(mode="pgvector_keyword", results=results)


# 8. Clinic API keys

@router.post("/api-keys", response_model=APIKeyCreateResponse)
def create_api_key(payload: APIKeyCreateRequest) -> APIKeyCreateResponse:
    raw_key = "ac_" + secrets.token_urlsafe(32)
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        INSERT INTO growth_api_keys (clinic_id, label, key_hash)
        VALUES (%s, %s, %s)
        RETURNING id::text, clinic_id, label, created_at
    """, (payload.clinic_id, payload.label, hash_api_key(raw_key)))
    row = cur.fetchone(); conn.commit(); conn.close()
    return APIKeyCreateResponse(
        id=row["id"], clinic_id=row["clinic_id"], label=row["label"],
        api_key=raw_key, created_at_utc=row["created_at"].isoformat(),
    )


@router.post("/clinic-api/search", response_model=SearchResponse)
def clinic_api_search(
    payload: SearchRequest,
    key_row: Dict[str, Any] = Depends(get_api_key_record),
) -> SearchResponse:
    results = hnsw_search(payload.query, payload.top_k)
    return SearchResponse(mode="clinic_api", results=results)


# 9. Paper alerts

@router.post("/paper-alerts/subscribe", response_model=PaperAlertSubscriptionResponse)
def subscribe_paper_alert(payload: PaperAlertSubscribeRequest) -> PaperAlertSubscriptionResponse:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        INSERT INTO growth_paper_subscriptions (user_id, topic, email)
        VALUES (%s, %s, %s)
        RETURNING id::text, user_id, topic, email, last_checked_at, created_at
    """, (payload.user_id, payload.topic, payload.email))
    row = cur.fetchone(); conn.commit(); conn.close()
    return PaperAlertSubscriptionResponse(
        id=row["id"], user_id=row["user_id"], topic=row["topic"],
        email=row["email"],
        last_checked_utc=row["last_checked_at"].isoformat() if row["last_checked_at"] else None,
        created_at_utc=row["created_at"].isoformat(),
    )


@router.get("/paper-alerts/{user_id}", response_model=List[PaperAlertSubscriptionResponse])
def list_paper_alerts(user_id: str) -> List[PaperAlertSubscriptionResponse]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id::text, user_id, topic, email, last_checked_at, created_at
        FROM growth_paper_subscriptions WHERE user_id = %s ORDER BY created_at DESC
    """, (user_id,))
    rows = cur.fetchall(); conn.close()
    return [PaperAlertSubscriptionResponse(
        id=r["id"], user_id=r["user_id"], topic=r["topic"], email=r["email"],
        last_checked_utc=r["last_checked_at"].isoformat() if r["last_checked_at"] else None,
        created_at_utc=r["created_at"].isoformat(),
    ) for r in rows]


@router.post("/paper-alerts/{subscription_id}/run", response_model=PaperAlertDigestResponse)
def run_paper_alert(subscription_id: str) -> PaperAlertDigestResponse:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id::text, user_id, topic, email, last_checked_at
        FROM growth_paper_subscriptions WHERE id = %s
    """, (subscription_id,))
    sub = cur.fetchone()
    if not sub:
        conn.close()
        raise HTTPException(status_code=404, detail="Subscription not found.")
    since = sub["last_checked_at"].isoformat() if sub["last_checked_at"] else None
    papers = search_new_papers(sub["topic"], since)
    for p in papers:
        cur.execute("""
            INSERT INTO growth_paper_alert_items
                (subscription_id, paper_title, paper_abstract, source_url, published_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (subscription_id, p.get("title", ""), p.get("abstract"),
              p.get("url"), p.get("published_date")))
    cur.execute(
        "UPDATE growth_paper_subscriptions SET last_checked_at = now() WHERE id = %s",
        (subscription_id,)
    )
    conn.commit(); conn.close()
    return PaperAlertDigestResponse(
        subscription_id=subscription_id, topic=sub["topic"], new_items=papers
    )


# 10. Drug interactions

@router.post("/drug-interactions", response_model=DrugInteractionResponse)
def drug_interactions(payload: DrugInteractionRequest) -> DrugInteractionResponse:
    items = check_drug_interactions(payload.medications, payload.planned_products)
    has_high = any(i.severity == "high" for i in items)
    summary = (
        f"{len(items)} interaction(s) found — HIGH severity. Review before proceeding."
        if has_high else
        f"{len(items)} interaction(s) found. Check actions before proceeding."
        if items else
        "No significant interactions identified."
    )
    return DrugInteractionResponse(items=items, summary=summary)


# Internal seed

@router.post("/internal/seed-knowledge")
def seed_knowledge() -> Dict[str, Any]:
    seed_rows = [
        {"title": "Vascular occlusion after HA filler",
         "content": "High-dose pulsed hyaluronidase, territory-based treatment, rapid reassessment, and emergency escalation for visual symptoms.",
         "source_type": "review", "source_ref": "S1", "tags": ["vascular occlusion", "hyaluronidase", "filler"]},
        {"title": "Tyndall effect after superficial filler",
         "content": "Blue-gray discoloration after superficial HA filler placement can often be treated with conservative targeted hyaluronidase.",
         "source_type": "review", "source_ref": "S20", "tags": ["tyndall", "tear trough"]},
        {"title": "Ptosis after botulinum toxin",
         "content": "Botulinum toxin ptosis is usually temporary and linked to diffusion. Diplopia or atypical neurologic findings require escalation.",
         "source_type": "review", "source_ref": "S30", "tags": ["ptosis", "botulinum toxin"]},
    ]
    conn = get_conn()
    cur = conn.cursor()
    count = 0
    for row in seed_rows:
        cur.execute("""
            INSERT INTO growth_knowledge_chunks (title, content, source_type, source_ref, tags)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT DO NOTHING
        """, (row["title"], row["content"], row["source_type"], row["source_ref"], json.dumps(row["tags"])))
        count += 1
    conn.commit(); conn.close()
    return {"inserted": count}


@router.get("/info")
def growth_engine_info() -> Dict[str, Any]:
    return {
        "engine": "AesthetiCite Growth Engine",
        "version": "2.0.0",
        "storage": "PostgreSQL",
        "features": ["bookmarks", "session_reports", "clinic_dashboard",
                     "patient_readable_export", "pwa", "hnsw_search",
                     "api_keys", "paper_alerts", "drug_interactions"],
        "generated_at": now_utc_iso(),
    }
