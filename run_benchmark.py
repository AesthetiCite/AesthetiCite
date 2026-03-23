import sys, json, os, time, logging, gc
sys.path.insert(0, '/home/runner/workspace')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout),
                              logging.FileHandler('/home/runner/workspace/benchmark.log')])
logger = logging.getLogger("benchmark")

CHECKPOINT_EN = '/home/runner/workspace/benchmark_checkpoint_en.json'
CHECKPOINT_FR = '/home/runner/workspace/benchmark_checkpoint_fr.json'
RESULT_FILE = '/home/runner/workspace/unilabs_result.json'
PROGRESS_FILE = '/home/runner/workspace/benchmark_progress.txt'

from app.benchmark.gold_aesthetic import (
    GOLD_QUESTIONS_30, GOLD_QUESTIONS_FR,
    QUESTION_CATEGORIES, FR_QUESTION_CATEGORIES,
    _run_questions, CATEGORY_LABELS
)
from app.engine.veridoc import AesthetiCiteEngine
from app.db import SessionLocal
from app.api.oe_upgrade import _veridoc_retrieve_adapter, _veridoc_llm_json, _veridoc_llm_text, _engine_cache
import statistics

db = SessionLocal()
retrieve_fn = _veridoc_retrieve_adapter(db)
engine = AesthetiCiteEngine(
    retrieve_fn=retrieve_fn,
    llm_json_fn=_veridoc_llm_json,
    llm_text_fn=_veridoc_llm_text,
    cache=_engine_cache,
)

start = time.time()

en_start_idx = 0
if os.path.exists(CHECKPOINT_EN):
    try:
        with open(CHECKPOINT_EN, 'r') as f:
            existing = json.load(f)
        en_start_idx = len(existing)
        logger.info(f"Resuming EN from question {en_start_idx + 1}")
    except Exception:
        en_start_idx = 0

with open(PROGRESS_FILE, 'w') as f:
    f.write(f'RUNNING (EN from Q{en_start_idx + 1})\n')
sys.stdout.flush()

try:
    logger.info(f"Starting EN questions (from {en_start_idx + 1}/30)...")
    en_results = _run_questions(engine, GOLD_QUESTIONS_30, QUESTION_CATEGORIES, 'fast',
                                checkpoint_path=CHECKPOINT_EN, start_idx=en_start_idx)

    fr_start_idx = 0
    if os.path.exists(CHECKPOINT_FR):
        try:
            with open(CHECKPOINT_FR, 'r') as f:
                existing = json.load(f)
            fr_start_idx = len(existing)
            logger.info(f"Resuming FR from question {fr_start_idx + 1}")
        except Exception:
            fr_start_idx = 0

    with open(PROGRESS_FILE, 'w') as f:
        f.write(f'RUNNING (FR from Q{fr_start_idx + 1})\n')

    logger.info(f"Starting FR questions (from {fr_start_idx + 1}/10)...")
    fr_results = _run_questions(engine, GOLD_QUESTIONS_FR, FR_QUESTION_CATEGORIES, 'fast',
                                checkpoint_path=CHECKPOINT_FR, start_idx=fr_start_idx)

    all_results = en_results + fr_results
    n_total = len(all_results)
    total_wall_s = round(time.time() - start, 1)

    aci_values = [r["aci"] for r in all_results if r.get("status") != "error" and r.get("aci", 0) > 0]
    n_cited = sum(1 for r in all_results if r.get("has_citations"))
    n_tools = sum(1 for r in all_results if r.get("n_tools", 0) > 0)
    n_protocol = sum(1 for r in all_results if r.get("has_protocol"))
    n_errors = sum(1 for r in all_results if r.get("status") == "error")
    latencies = [r["latency_s"] for r in all_results if r.get("status") != "error"]

    avg_aci = round(statistics.mean(aci_values), 2) if aci_values else 0.0
    median_aci = round(statistics.median(aci_values), 2) if aci_values else 0.0
    aci_std = round(statistics.stdev(aci_values), 2) if len(aci_values) > 1 else 0.0
    avg_latency = round(statistics.mean(latencies), 2) if latencies else 0.0

    citation_rate = round(100 * n_cited / max(1, n_total), 1)
    tool_rate = round(100 * n_tools / max(1, n_total), 1)
    n_safety = sum(1 for r in all_results if r.get("category") == "safety")
    n_safety_protocol = sum(1 for r in all_results if r.get("category") == "safety" and r.get("has_protocol"))
    protocol_rate_safety = round(100 * n_safety_protocol / max(1, n_safety), 1) if n_safety > 0 else 0

    overall_score = round(
        0.30 * min(citation_rate / 100, 1.0) +
        0.30 * min(avg_aci / 10.0, 1.0) +
        0.15 * min(tool_rate / 50, 1.0) +
        0.15 * min(protocol_rate_safety / 70, 1.0) +
        0.10 * (1.0 - min(n_errors / max(1, n_total), 1.0)),
        3
    )

    if overall_score >= 0.85: grade = "A"
    elif overall_score >= 0.70: grade = "B+"
    elif overall_score >= 0.55: grade = "B"
    elif overall_score >= 0.40: grade = "C"
    else: grade = "D"

    result = {
        "benchmark": "unilabs_gold_aesthetic_v1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "fast",
        "total_wall_s": total_wall_s,
        "summary": {
            "grade": grade,
            "overall_score": overall_score,
            "questions_total": n_total,
            "questions_en": len(en_results),
            "questions_fr": len(fr_results),
            "citation_rate": citation_rate,
            "avg_aci": avg_aci,
            "median_aci": median_aci,
            "aci_std": aci_std,
            "tool_triggering_rate": tool_rate,
            "protocol_activation_rate_safety": protocol_rate_safety,
            "error_rate": round(100 * n_errors / max(1, n_total), 1),
            "avg_latency_s": avg_latency,
            "en_citation_rate": round(100 * sum(1 for r in en_results if r.get("has_citations")) / max(1, len(en_results)), 1),
            "en_avg_aci": round(statistics.mean([r["aci"] for r in en_results if r.get("status") != "error" and r.get("aci", 0) > 0]) if any(r.get("aci", 0) > 0 for r in en_results) else 0, 2),
            "fr_citation_rate": round(100 * sum(1 for r in fr_results if r.get("has_citations")) / max(1, len(fr_results)), 1),
            "fr_avg_aci": round(statistics.mean([r["aci"] for r in fr_results if r.get("status") != "error" and r.get("aci", 0) > 0]) if any(r.get("aci", 0) > 0 for r in fr_results) else 0, 2),
        },
        "results": all_results,
    }

    with open(RESULT_FILE, 'w') as f:
        json.dump(result, f, indent=2)

    summary_text = f"""DONE
Elapsed: {total_wall_s:.0f}s
Grade: {grade}
Score: {overall_score}
Citation Rate: {citation_rate}%
Avg ACI: {avg_aci}
Median ACI: {median_aci}
Tool Triggering: {tool_rate}%
Protocol Activation: {protocol_rate_safety}%
Error Rate: {round(100 * n_errors / max(1, n_total), 1)}%
EN: {len(en_results)} questions
FR: {len(fr_results)} questions
"""
    with open(PROGRESS_FILE, 'w') as f:
        f.write(summary_text)
    logger.info(f"Benchmark complete in {total_wall_s:.0f}s - Grade: {grade}, Score: {overall_score}")

except Exception as e:
    import traceback
    err = traceback.format_exc()
    logger.error(f"Benchmark failed: {err}")
    with open(PROGRESS_FILE, 'w') as f:
        f.write(f'ERROR\n{err}\n')
finally:
    db.close()
    gc.collect()
