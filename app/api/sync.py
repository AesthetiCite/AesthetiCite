"""
Publication Sync API endpoints for admin management.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db
from app.api.auth import require_admin_api_key
from app.agents.publication_sync import run_sync, run_journal_sync, get_sync_status, ensure_sync_tables

router = APIRouter(prefix="/admin/sync", tags=["admin-sync"])


@router.post("/run")
def trigger_sync(
    days_back: int = 7,
    max_per_query: int = 20,
    background_tasks: BackgroundTasks = None,
    _: str = Depends(require_admin_api_key),
    db: Session = Depends(get_db),
):
    """
    Trigger a publication sync.
    
    - days_back: How many days back to search (default 7)
    - max_per_query: Max papers to fetch per query (default 20)
    
    Returns immediately and runs sync in background.
    """
    ensure_sync_tables()
    
    if background_tasks:
        background_tasks.add_task(run_sync, days_back, max_per_query)
        return {
            "status": "started",
            "message": f"Sync started in background. Searching last {days_back} days.",
        }
    else:
        result = run_sync(days_back=days_back, max_papers_per_query=max_per_query)
        return result


@router.get("/status")
def sync_status(
    limit: int = 10,
    _: str = Depends(require_admin_api_key),
    db: Session = Depends(get_db),
):
    """
    Get recent sync history.
    """
    ensure_sync_tables()
    syncs = get_sync_status(db, limit=limit)
    return {"syncs": syncs}


@router.post("/turbo")
def turbo_sync(
    years_back: int = 5,
    max_per_query: int = 5000,
    background_tasks: BackgroundTasks = None,
    _: str = Depends(require_admin_api_key),
    db: Session = Depends(get_db),
):
    """
    TURBO SYNC: Maximum harvesting mode to reach 1M+ publications.
    
    - years_back: How many years back to search (default 5)
    - max_per_query: Max papers to fetch per query (default 5000, max 10000)
    
    This is the aggressive mode for building a massive knowledge base.
    PubMed Central has ~8M open access papers - we can harvest a significant portion.
    """
    ensure_sync_tables()
    
    days_back = years_back * 365
    max_per_query = min(max_per_query, 10000)
    
    if background_tasks:
        background_tasks.add_task(run_sync, days_back, max_per_query)
        return {
            "status": "started",
            "mode": "TURBO",
            "message": f"Turbo sync started! Searching last {years_back} years with {max_per_query} papers/query.",
            "estimated_papers": f"Could harvest 500K-1M+ papers depending on query coverage",
        }
    else:
        result = run_sync(days_back=days_back, max_papers_per_query=max_per_query)
        return result


@router.post("/journals")
def journal_sync(
    journals: str = "nejm,jama,nccn",
    years_back: int = 10,
    max_per_query: int = 500,
    background_tasks: BackgroundTasks = None,
    _: str = Depends(require_admin_api_key),
    db: Session = Depends(get_db),
):
    """
    Targeted sync for high-impact journals: NEJM, JAMA (all specialty journals), NCCN.
    Fetches PubMed abstracts (not just PMC open-access).
    
    - journals: Comma-separated list (nejm, jama, nccn)
    - years_back: How many years to search (default 10)
    - max_per_query: Max papers per query (default 500)
    """
    ensure_sync_tables()
    journal_list = [j.strip().lower() for j in journals.split(",") if j.strip()]
    
    if background_tasks:
        background_tasks.add_task(run_journal_sync, journal_list, years_back, max_per_query)
        return {
            "status": "started",
            "journals": journal_list,
            "message": f"Journal sync started for {', '.join(journal_list)}. Searching last {years_back} years.",
        }
    else:
        result = run_journal_sync(journals=journal_list, years_back=years_back, max_per_query=max_per_query)
        return result


@router.post("/aesthetic-journals")
def aesthetic_journal_sync(
    years_back: int = 10,
    max_per_query: int = 500,
    background_tasks: BackgroundTasks = None,
    _: str = Depends(require_admin_api_key),
    db: Session = Depends(get_db),
):
    """
    Agent 4: Aesthetic-focused journal sync.
    Targets 15+ aesthetic medicine journals NOT covered by NEJM/JAMA/NCCN agents:
    Dermatol Surg, Aesthet Surg J, J Cosmet Dermatol, Plast Reconstr Surg,
    JAAD, Lasers Surg Med, Aesthetic Plast Surg, J Cutan Aesthet Surg,
    Clin Cosmet Investig Dermatol, J Drugs Dermatol, Dermatol Ther,
    Br J Dermatol, Arch Dermatol Res, J Cosmet Laser Ther, Int J Dermatol,
    Skin Res Technol, Ann Plast Surg, Facial Plast Surg Aesthet Med, JPRAS.
    
    - years_back: How many years to search (default 10)
    - max_per_query: Max papers per query (default 500)
    """
    ensure_sync_tables()

    if background_tasks:
        background_tasks.add_task(run_journal_sync, ["aesthetic_journals"], years_back, max_per_query)
        return {
            "status": "started",
            "agent": "aesthetic_journals",
            "queries": 130,
            "journals": [
                "Dermatol Surg", "Aesthet Surg J", "J Cosmet Dermatol",
                "Plast Reconstr Surg", "JAAD", "Lasers Surg Med",
                "Aesthetic Plast Surg", "J Cutan Aesthet Surg",
                "Clin Cosmet Investig Dermatol", "J Drugs Dermatol",
                "Dermatol Ther", "Br J Dermatol", "Arch Dermatol Res",
                "J Cosmet Laser Ther", "Int J Dermatol", "Skin Res Technol",
                "Ann Plast Surg", "Facial Plast Surg Aesthet Med", "JPRAS",
            ],
            "message": f"Aesthetic journals sync started. Searching last {years_back} years across 19 specialty journals.",
        }
    else:
        result = run_journal_sync(journals=["aesthetic_journals"], years_back=years_back, max_per_query=max_per_query)
        return result


@router.get("/stats")
def sync_stats(
    _: str = Depends(require_admin_api_key),
    db: Session = Depends(get_db),
):
    """
    Get overall knowledge base statistics.
    """
    docs = db.execute(text("SELECT COUNT(*) FROM documents")).scalar()
    chunks = db.execute(text("SELECT COUNT(*) FROM chunks")).scalar()
    
    year_range = db.execute(text("""
        SELECT MIN(year), MAX(year) FROM documents WHERE year IS NOT NULL
    """)).fetchone()
    
    recent_docs = db.execute(text("""
        SELECT title, year, source_id FROM documents
        ORDER BY source_id DESC LIMIT 5
    """)).mappings().fetchall()
    
    ensure_sync_tables()
    last_sync = db.execute(text("""
        SELECT started_at, status, papers_ingested 
        FROM publication_syncs 
        ORDER BY started_at DESC LIMIT 1
    """)).mappings().fetchone()
    
    return {
        "total_documents": docs,
        "total_chunks": chunks,
        "year_range": {
            "min": year_range[0] if year_range else None,
            "max": year_range[1] if year_range else None,
        },
        "recent_documents": [dict(d) for d in recent_docs],
        "last_sync": dict(last_sync) if last_sync else None,
    }
