"""
Benchmark API endpoints for AesthetiCite Aesthetic Medicine Benchmark (AAMB).
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.core.admin_auth import require_admin
from app.benchmark.runner import (
    run_benchmark,
    run_single_question,
    load_benchmark_questions,
    BenchmarkResult
)
from app.benchmark.gold_aesthetic import run_gold_benchmark, run_unilabs_benchmark, compile_unilabs_report, GOLD_QUESTIONS_30, GOLD_QUESTIONS_FR


router = APIRouter(prefix="/admin/benchmark", tags=["benchmark"])


class BenchmarkRequest(BaseModel):
    categories: Optional[List[str]] = None
    max_questions: Optional[int] = None
    mode: str = "clinic"


class QuestionPreview(BaseModel):
    id: str
    category: str
    difficulty: str
    question: str


class BenchmarkQuestionsResponse(BaseModel):
    version: str
    total_questions: int
    categories: List[dict]
    questions: List[QuestionPreview]


class SingleQuestionRequest(BaseModel):
    question_id: str
    mode: str = "clinic"


@router.get("/questions", response_model=BenchmarkQuestionsResponse)
def get_benchmark_questions(_: dict = Depends(require_admin)):
    """Get list of available benchmark questions."""
    data = load_benchmark_questions()
    questions = [
        QuestionPreview(
            id=q["id"],
            category=q["category"],
            difficulty=q["difficulty"],
            question=q["question"]
        )
        for q in data["questions"]
    ]
    return BenchmarkQuestionsResponse(
        version=data["version"],
        total_questions=len(data["questions"]),
        categories=data["categories"],
        questions=questions
    )


@router.post("/run")
def run_full_benchmark(
    request: BenchmarkRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin)
):
    """Run full benchmark suite. Returns detailed results."""
    result = run_benchmark(
        db=db,
        categories=request.categories,
        max_questions=request.max_questions,
        mode=request.mode
    )
    return {
        "version": result.version,
        "run_id": result.run_id,
        "run_date": result.run_date,
        "total_questions": result.total_questions,
        "questions_answered": result.questions_answered,
        "questions_refused": result.questions_refused,
        "correct_refusals": result.correct_refusals,
        "incorrect_refusals": result.incorrect_refusals,
        "category_scores": result.category_scores,
        "overall_score": round(result.overall_score * 100, 1),
        "average_latency_ms": round(result.average_latency_ms, 0),
        "grade": _score_to_grade(result.overall_score),
        "question_results": result.question_results
    }


@router.post("/run-single")
def run_single(
    request: SingleQuestionRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin)
):
    """Run benchmark on a single question by ID."""
    data = load_benchmark_questions()
    question = next(
        (q for q in data["questions"] if q["id"] == request.question_id),
        None
    )
    if not question:
        raise HTTPException(status_code=404, detail=f"Question {request.question_id} not found")
    
    from dataclasses import asdict
    result = run_single_question(db, question, mode=request.mode)
    return {
        **asdict(result),
        "total_score_percent": round(result.total_score * 100, 1)
    }


@router.get("/summary")
def get_benchmark_summary(_: dict = Depends(require_admin)):
    """Get benchmark summary without running tests."""
    data = load_benchmark_questions()
    
    category_counts = {}
    difficulty_counts = {"medium": 0, "hard": 0, "critical": 0}
    
    for q in data["questions"]:
        cat = q["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        diff = q["difficulty"]
        if diff in difficulty_counts:
            difficulty_counts[diff] += 1
    
    return {
        "version": data["version"],
        "name": "AesthetiCite Aesthetic Medicine Benchmark (AAMB)",
        "description": data["description"],
        "total_questions": len(data["questions"]),
        "categories": data["categories"],
        "category_counts": category_counts,
        "difficulty_distribution": difficulty_counts,
        "scoring_weights": data["scoring"]
    }


class GoldBenchmarkRequest(BaseModel):
    mode: str = "fast"


@router.post("/gold")
def run_gold_aesthetic_benchmark(
    request: GoldBenchmarkRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Run the 30-question gold aesthetic benchmark using VeriDoc v2 engine."""
    from app.engine.veridoc import AesthetiCiteEngine
    from app.api.oe_upgrade import (
        _veridoc_retrieve_adapter, _veridoc_llm_json, _veridoc_llm_text, _engine_cache
    )

    retrieve_fn = _veridoc_retrieve_adapter(db)
    engine = AesthetiCiteEngine(
        retrieve_fn=retrieve_fn,
        llm_json_fn=_veridoc_llm_json,
        llm_text_fn=_veridoc_llm_text,
        cache=_engine_cache,
    )
    result = run_gold_benchmark(engine, mode=request.mode)
    return result


@router.get("/gold/questions")
def get_gold_questions(_: dict = Depends(require_admin)):
    """List the 30 EN + 10 FR gold aesthetic benchmark questions."""
    en_qs = [{"index": i + 1, "query": q, "language": "en"} for i, q in enumerate(GOLD_QUESTIONS_30)]
    fr_qs = [{"index": i + 31, "query": q, "language": "fr"} for i, q in enumerate(GOLD_QUESTIONS_FR)]
    return {
        "n": len(GOLD_QUESTIONS_30) + len(GOLD_QUESTIONS_FR),
        "questions": en_qs + fr_qs,
    }


class UnilabsReportRequest(BaseModel):
    mode: str = "fast"


@router.post("/gold/report")
def run_unilabs_report(
    request: UnilabsReportRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Run the full Unilabs-ready benchmark report (30 EN + 10 FR questions)."""
    from app.engine.veridoc import AesthetiCiteEngine
    from app.api.oe_upgrade import (
        _veridoc_retrieve_adapter, _veridoc_llm_json, _veridoc_llm_text, _engine_cache
    )

    retrieve_fn = _veridoc_retrieve_adapter(db)
    engine = AesthetiCiteEngine(
        retrieve_fn=retrieve_fn,
        llm_json_fn=_veridoc_llm_json,
        llm_text_fn=_veridoc_llm_text,
        cache=_engine_cache,
    )
    return run_unilabs_benchmark(engine, mode=request.mode)


import threading, json as _json, os

_benchmark_state = {"status": "idle", "progress": 0, "total": 40, "current_q": "", "results": None, "error": None}
_benchmark_lock = threading.Lock()


def _run_benchmark_thread(mode: str):
    import time, statistics, gc, logging
    logger = logging.getLogger("benchmark")
    from app.db.session import SessionLocal as _SL
    from app.engine.veridoc import AesthetiCiteEngine
    from app.api.oe_upgrade import (
        _veridoc_retrieve_adapter, _veridoc_llm_json, _veridoc_llm_text, _engine_cache
    )
    from app.benchmark.gold_aesthetic import (
        GOLD_QUESTIONS_30, GOLD_QUESTIONS_FR,
        QUESTION_CATEGORIES, FR_QUESTION_CATEGORIES,
        _run_questions, CATEGORY_LABELS
    )

    db = _SL()
    t0 = time.time()
    try:
        retrieve_fn = _veridoc_retrieve_adapter(db)
        engine = AesthetiCiteEngine(
            retrieve_fn=retrieve_fn,
            llm_json_fn=_veridoc_llm_json,
            llm_text_fn=_veridoc_llm_text,
            cache=_engine_cache,
        )

        with _benchmark_lock:
            _benchmark_state["status"] = "running"
            _benchmark_state["progress"] = 0
            _benchmark_state["error"] = None

        checkpoint_en = '/home/runner/workspace/benchmark_checkpoint_en.json'
        checkpoint_fr = '/home/runner/workspace/benchmark_checkpoint_fr.json'

        en_start = 0
        if os.path.exists(checkpoint_en):
            try:
                with open(checkpoint_en, 'r') as f:
                    en_start = len(_json.load(f))
                logger.info(f"[BG Benchmark] Resuming EN from Q{en_start + 1}")
            except Exception:
                en_start = 0

        logger.info(f"[BG Benchmark] Starting EN questions (from {en_start + 1}/30)...")
        en_results = _run_questions(engine, GOLD_QUESTIONS_30, QUESTION_CATEGORIES, mode,
                                    checkpoint_path=checkpoint_en, start_idx=en_start)

        with _benchmark_lock:
            _benchmark_state["progress"] = len(en_results)

        fr_start = 0
        if os.path.exists(checkpoint_fr):
            try:
                with open(checkpoint_fr, 'r') as f:
                    fr_start = len(_json.load(f))
                logger.info(f"[BG Benchmark] Resuming FR from Q{fr_start + 1}")
            except Exception:
                fr_start = 0

        logger.info(f"[BG Benchmark] Starting FR questions (from {fr_start + 1}/10)...")
        fr_results = _run_questions(engine, GOLD_QUESTIONS_FR, FR_QUESTION_CATEGORIES, mode,
                                    checkpoint_path=checkpoint_fr, start_idx=fr_start)

        total_wall_s = round(time.time() - t0, 1)
        result = compile_unilabs_report(en_results, fr_results, mode, total_wall_s)

        with open('/home/runner/workspace/unilabs_result.json', 'w') as f:
            _json.dump(result, f, indent=2)

        with _benchmark_lock:
            _benchmark_state["status"] = "done"
            _benchmark_state["progress"] = len(en_results) + len(fr_results)
            _benchmark_state["results"] = result

        logger.info(f"[BG Benchmark] Complete! Grade: {result.get('summary', {}).get('grade')}")
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        logger.error(f"[BG Benchmark] Failed: {err}")
        with _benchmark_lock:
            _benchmark_state["status"] = "error"
            _benchmark_state["error"] = str(e)
    finally:
        db.close()
        gc.collect()


@router.post("/gold/report/start")
def start_unilabs_report_bg(
    request: UnilabsReportRequest,
    _: dict = Depends(require_admin),
):
    """Start the Unilabs benchmark in a background thread. Poll /gold/report/status for progress."""
    with _benchmark_lock:
        if _benchmark_state["status"] == "running":
            raise HTTPException(status_code=409, detail="Benchmark already running")
        _benchmark_state["status"] = "starting"
        _benchmark_state["progress"] = 0
        _benchmark_state["total"] = 40
        _benchmark_state["results"] = None
        _benchmark_state["error"] = None

    t = threading.Thread(target=_run_benchmark_thread, args=(request.mode,), daemon=True)
    t.start()
    return {"status": "started", "message": "Benchmark running in background. Poll /admin/benchmark/gold/report/status for progress."}


@router.get("/gold/report/status")
def get_benchmark_status(_: dict = Depends(require_admin)):
    """Check status of background benchmark run."""
    with _benchmark_lock:
        resp = {
            "status": _benchmark_state["status"],
            "progress": _benchmark_state["progress"],
            "total": _benchmark_state["total"],
            "error": _benchmark_state["error"],
        }
    if _benchmark_state["status"] == "done" and _benchmark_state["results"]:
        resp["summary"] = _benchmark_state["results"].get("summary")
    checkpoint_en = '/home/runner/workspace/benchmark_checkpoint_en.json'
    if os.path.exists(checkpoint_en):
        try:
            with open(checkpoint_en, 'r') as f:
                cp = _json.load(f)
            resp["progress"] = len(cp)
        except Exception:  # nosec B110
            pass
    checkpoint_fr = '/home/runner/workspace/benchmark_checkpoint_fr.json'
    if os.path.exists(checkpoint_fr):
        try:
            with open(checkpoint_fr, 'r') as f:
                cp = _json.load(f)
            resp["progress"] = 30 + len(cp)
        except Exception:  # nosec B110
            pass
    return resp


@router.get("/gold/report/result")
def get_benchmark_result(_: dict = Depends(require_admin)):
    """Get the latest benchmark result (from memory or file)."""
    if _benchmark_state["results"]:
        return _benchmark_state["results"]
    result_file = '/home/runner/workspace/unilabs_result.json'
    if os.path.exists(result_file):
        with open(result_file, 'r') as f:
            return _json.load(f)
    raise HTTPException(status_code=404, detail="No benchmark results available. Run a benchmark first.")


def _score_to_grade(score: float) -> str:
    """Convert numerical score to letter grade."""
    if score >= 0.95:
        return "A+"
    elif score >= 0.90:
        return "A"
    elif score >= 0.85:
        return "A-"
    elif score >= 0.80:
        return "B+"
    elif score >= 0.75:
        return "B"
    elif score >= 0.70:
        return "B-"
    elif score >= 0.65:
        return "C+"
    elif score >= 0.60:
        return "C"
    elif score >= 0.55:
        return "C-"
    elif score >= 0.50:
        return "D"
    else:
        return "F"
