"""
Gold Aesthetic Benchmark — Curated questions for ACI + VeriDoc v2 evaluation.
Includes English (30) and French (10) questions for Unilabs France pilot.
Tests: citation presence, ACI score distribution, tool triggering, complication protocol activation.
"""
from __future__ import annotations

import re
import time
import statistics
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

GOLD_QUESTIONS_30 = [
    "What are the early signs of vascular compromise during HA filler injection and what should be done immediately?",
    "Tear trough filler: what safety considerations and risk mitigation are emphasized in the literature?",
    "Glabellar injections: what makes this zone higher risk and what precautions are recommended?",
    "How should suspected ocular symptoms after filler injection be handled according to consensus guidance?",
    "What does consensus guidance emphasize about protocol-driven response to filler vascular events?",
    "How should a clinic structure an emergency response for suspected HA filler vascular compromise?",
    "What does the evidence say about the role of hyaluronidase in HA filler complications?",
    "When should an injector stop the procedure and escalate based on perfusion changes?",
    "What are common complication patterns after dermal fillers and how are they generally approached?",
    "How should complication risk be communicated to patients in high-risk injection zones?",
    "How do common BoNT-A dilution practices vary and what should be considered when selecting a dilution strategy?",
    "If a 100U vial is reconstituted with 2.5 mL, what is the concentration in U/mL and U per 0.1 mL?",
    "What are typical factors that influence BoNT-A injection technique by facial region?",
    "What does systematic evidence summarize about BoNT-A aesthetic outcomes across regions?",
    "What cautions should be taken when generalizing dosing patterns across products and techniques?",
    "Laser treatments in Fitzpatrick IV-VI: what risk mitigation is commonly recommended to reduce PIH?",
    "What does review-level evidence emphasize about conservative device parameter selection in higher Fitzpatrick types?",
    "How should test spots and photoprotection be used to reduce pigmentary risk after laser procedures?",
    "What are general considerations for balancing efficacy vs safety in energy-based devices?",
    "What does the literature emphasize about post-procedure care for pigmentary risk reduction?",
    "How should clinicians think about on-label vs off-label use in aesthetic medicine when communicating risk?",
    "What does a cautious evidence-based answer include when regulatory alignment is unclear?",
    "How should CE vs FDA language be handled in a clinical summary without overclaiming?",
    "What should be avoided in an evidence-grounded answer about product indications?",
    "How should AesthetiCite structure an answer differently from a general medical AI tool in aesthetic medicine?",
    "What is the role of complication-first logic in aesthetic decision support tools?",
    "How should an evidence engine avoid hallucinating dosing values in high-stakes aesthetic scenarios?",
    "What should an Aesthetic Confidence Index communicate to clinicians?",
    "What elements should be always present in high-risk injectable answers?",
    "Patient with Fitzpatrick III considering laser resurfacing: what safety considerations should be discussed?",
]

GOLD_QUESTIONS_FR = [
    "Quels sont les signes précoces de compromis vasculaire lors d'une injection d'acide hyaluronique et quelle conduite à tenir immédiate ?",
    "Injection de toxine botulique au niveau de la glabelle : quels sont les risques spécifiques et les précautions recommandées ?",
    "Comment gérer une suspicion d'occlusion vasculaire après injection de filler selon les recommandations de consensus ?",
    "Quelles sont les précautions de sécurité pour les injections de comblement au niveau du sillon nasogénien ?",
    "Quel est le rôle de la hyaluronidase dans la prise en charge des complications des fillers à base d'acide hyaluronique ?",
    "Traitements laser chez les phototypes IV-VI : quelles stratégies pour minimiser le risque d'hyperpigmentation post-inflammatoire ?",
    "Comment un outil d'aide à la décision clinique en médecine esthétique doit-il aborder les complications en priorité ?",
    "Quelles sont les considérations réglementaires (marquage CE vs FDA) à prendre en compte dans un résumé clinique ?",
    "Patient de phototype III envisageant un resurfaçage laser : quels points de sécurité discuter en consultation ?",
    "Quels éléments doivent toujours figurer dans une réponse evidence-based concernant les injectables à haut risque ?",
]

QUESTION_CATEGORIES = {
    0: "safety", 1: "safety", 2: "safety", 3: "safety", 4: "safety",
    5: "safety", 6: "safety", 7: "safety", 8: "complications", 9: "safety",
    10: "dosing", 11: "dosing", 12: "technique", 13: "technique", 14: "dosing",
    15: "devices", 16: "devices", 17: "devices", 18: "devices", 19: "devices",
    20: "regulatory", 21: "regulatory", 22: "regulatory", 23: "regulatory",
    24: "platform", 25: "platform", 26: "platform", 27: "platform", 28: "safety",
    29: "devices",
}

FR_QUESTION_CATEGORIES = {
    0: "safety", 1: "safety", 2: "safety", 3: "safety", 4: "safety",
    5: "devices", 6: "platform", 7: "regulatory", 8: "devices", 9: "safety",
}

CATEGORY_LABELS = {
    "safety": "Complication Safety",
    "dosing": "Dosing & Dilution",
    "technique": "Injection Technique",
    "devices": "Energy Devices & Laser",
    "regulatory": "Regulatory Alignment",
    "platform": "Platform Intelligence",
    "complications": "Complication Management",
}


def summarize_aci(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    aci_all = [r.get("aci", 0.0) for r in results]
    aci_scored = [a for a in aci_all if a > 0]

    return {
        "avg_aci_all_including_zeros": round(sum(aci_all) / max(1, len(aci_all)), 2),
        "avg_aci_scored_nonzero_only": round(sum(aci_scored) / max(1, len(aci_scored)), 2),
        "median_aci_scored": round(sorted(aci_scored)[len(aci_scored) // 2], 2) if aci_scored else 0.0,
        "aci_coverage_pct": round(100.0 * len(aci_scored) / max(1, len(results)), 1),
        "n_zero_aci": sum(1 for a in aci_all if a == 0),
    }


def _run_questions(engine: Any, questions: List[str], categories: Dict[int, str], mode: str = "fast",
                   checkpoint_path: Optional[str] = None, start_idx: int = 0) -> List[Dict[str, Any]]:
    import gc, logging, json
    logger = logging.getLogger("benchmark")
    results: List[Dict[str, Any]] = []
    if checkpoint_path and start_idx > 0:
        try:
            with open(checkpoint_path, 'r') as f:
                results = json.load(f)
            logger.info(f"[Benchmark] Resumed from checkpoint with {len(results)} completed results")
        except Exception:
            results = []
            start_idx = 0

    total = len(questions)
    for idx in range(start_idx, total):
        q = questions[idx]
        logger.info(f"[Benchmark] Question {idx+1}/{total}: {q[:60]}...")
        t0 = time.time()
        try:
            out = engine.answer(q, mode=mode)
            logger.info(f"[Benchmark] Question {idx+1}/{total} done in {time.time()-t0:.1f}s")
        except Exception as exc:
            results.append({
                "index": idx,
                "query": q,
                "language": "fr" if any(c in q for c in "éèêàùç") else "en",
                "category": categories.get(idx, "general"),
                "aci": 0.0,
                "has_citations": False,
                "n_refs": 0,
                "n_tools": 0,
                "has_protocol": False,
                "evidence_grade": "N/A",
                "latency_s": round(time.time() - t0, 2),
                "error": str(exc)[:200],
                "status": "error",
            })
            if checkpoint_path:
                with open(checkpoint_path, 'w') as f:
                    json.dump(results, f)
            continue

        aci_raw = out.get("aci_score", 0.0) or 0.0
        aci = aci_raw.get("overall_confidence_0_10", 0.0) if isinstance(aci_raw, dict) else float(aci_raw or 0.0)
        answer_text = out.get("clinical_answer", "")
        refs = out.get("references", [])
        cited = bool(re.search(r"\[[0-9a-f\-]{8,}\]|\[\w+[\-_]?\d+\]", answer_text)) or len(refs) > 0
        tools = out.get("inline_tools", [])
        protocol = out.get("complication_protocol")
        grade_obj = out.get("evidence_strength") or {}
        grade = grade_obj.get("grade", "N/A") if isinstance(grade_obj, dict) else str(grade_obj)
        status = out.get("status", "ok")

        results.append({
            "index": idx,
            "query": q,
            "language": "fr" if any(c in q for c in "éèêàùç") else "en",
            "category": categories.get(idx, "general"),
            "aci": round(aci, 2),
            "has_citations": cited,
            "n_refs": len(out.get("references", [])),
            "n_tools": len(tools),
            "tool_names": [t.get("tool", "") for t in tools],
            "has_protocol": protocol is not None,
            "evidence_grade": grade,
            "latency_s": round(time.time() - t0, 2),
            "status": status,
            "answer_preview": (answer_text or "")[:300],
        })
        if checkpoint_path:
            with open(checkpoint_path, 'w') as f:
                json.dump(results, f)
        gc.collect()
    return results


def run_gold_benchmark(engine: Any, mode: str = "fast") -> Dict[str, Any]:
    results = _run_questions(engine, GOLD_QUESTIONS_30, QUESTION_CATEGORIES, mode)
    n_total = len(GOLD_QUESTIONS_30)
    n_cited = sum(1 for r in results if r.get("has_citations"))
    aci = summarize_aci(results)
    n_tools_triggered = sum(1 for r in results if r.get("n_tools", 0) > 0)
    n_protocol_triggered = sum(1 for r in results if r.get("has_protocol"))

    return {
        "n": n_total,
        "aci": aci,
        "pct_with_citations": round(100.0 * n_cited / max(1, n_total), 1),
        "n_tools_triggered": n_tools_triggered,
        "n_protocol_triggered": n_protocol_triggered,
        "results": results,
    }


def compile_unilabs_report(en_results: List[Dict], fr_results: List[Dict], mode: str, total_wall_s: float) -> Dict[str, Any]:
    """Compile benchmark results into the full Unilabs report format."""
    all_results = en_results + fr_results
    n_total = len(all_results)

    aci_summary = summarize_aci(all_results)
    aci_values = [r["aci"] for r in all_results if r.get("status") != "error" and r.get("aci", 0) > 0]
    n_cited = sum(1 for r in all_results if r.get("has_citations"))
    n_tools = sum(1 for r in all_results if r.get("n_tools", 0) > 0)
    n_protocol = sum(1 for r in all_results if r.get("has_protocol"))
    n_errors = sum(1 for r in all_results if r.get("status") == "error")
    latencies = [r["latency_s"] for r in all_results if r.get("status") != "error"]

    avg_aci = aci_summary["avg_aci_scored_nonzero_only"]
    median_aci = aci_summary["median_aci_scored"]
    aci_std = round(statistics.stdev(aci_values), 2) if len(aci_values) > 1 else 0.0
    avg_latency = round(statistics.mean(latencies), 2) if latencies else 0.0
    p95_latency = round(sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0, 2)

    aci_high = sum(1 for v in aci_values if v >= 7.0)
    aci_mid = sum(1 for v in aci_values if 4.0 <= v < 7.0)
    aci_low = sum(1 for v in aci_values if 0 < v < 4.0)

    cat_scores: Dict[str, Dict[str, Any]] = {}
    for r in all_results:
        cat = r.get("category", "general")
        if cat not in cat_scores:
            cat_scores[cat] = {"n": 0, "cited": 0, "aci_sum": 0.0, "tools": 0, "protocol": 0}
        cat_scores[cat]["n"] += 1
        if r.get("has_citations"):
            cat_scores[cat]["cited"] += 1
        cat_scores[cat]["aci_sum"] += r.get("aci", 0) or 0
        if r.get("n_tools", 0) > 0:
            cat_scores[cat]["tools"] += 1
        if r.get("has_protocol"):
            cat_scores[cat]["protocol"] += 1

    category_breakdown = {}
    for cat, s in cat_scores.items():
        category_breakdown[cat] = {
            "label": CATEGORY_LABELS.get(cat, cat.replace("_", " ").title()),
            "questions": s["n"],
            "citation_rate": round(100 * s["cited"] / max(1, s["n"]), 1),
            "avg_aci": round(s["aci_sum"] / max(1, s["n"]), 2),
            "tools_triggered": s["tools"],
            "protocols_triggered": s["protocol"],
        }

    fr_cited = sum(1 for r in fr_results if r.get("has_citations"))
    fr_aci = summarize_aci(fr_results)

    en_cited = sum(1 for r in en_results if r.get("has_citations"))
    en_aci = summarize_aci(en_results)

    citation_rate = round(100 * n_cited / max(1, n_total), 1)
    tool_rate = round(100 * n_tools / max(1, n_total), 1)
    protocol_rate_safety = 0
    n_safety = sum(1 for r in all_results if r.get("category") == "safety")
    n_safety_protocol = sum(1 for r in all_results if r.get("category") == "safety" and r.get("has_protocol"))
    if n_safety > 0:
        protocol_rate_safety = round(100 * n_safety_protocol / n_safety, 1)

    overall_score = round(
        0.30 * min(citation_rate / 100, 1.0) +
        0.30 * min(avg_aci / 10.0, 1.0) +
        0.15 * min(tool_rate / 50, 1.0) +
        0.15 * min(protocol_rate_safety / 70, 1.0) +
        0.10 * (1.0 - min(n_errors / max(1, n_total), 1.0)),
        3
    )

    if overall_score >= 0.85:
        grade = "A"
    elif overall_score >= 0.70:
        grade = "B+"
    elif overall_score >= 0.55:
        grade = "B"
    elif overall_score >= 0.40:
        grade = "C"
    else:
        grade = "D"

    generic_comparison = {
        "aestheticite": {
            "citation_rate": citation_rate,
            "avg_aci": avg_aci,
            "safety_protocol_activation": protocol_rate_safety,
            "inline_clinical_tools": True,
            "aesthetic_chunk_tagging": True,
            "complication_first_logic": True,
            "french_language_support": True,
            "aesthetic_confidence_index": True,
        },
        "generic_medical_ai": {
            "citation_rate": "~40-60% (no domain-specific retrieval)",
            "avg_aci": "N/A (no confidence scoring)",
            "safety_protocol_activation": "N/A (no complication protocol)",
            "inline_clinical_tools": False,
            "aesthetic_chunk_tagging": False,
            "complication_first_logic": False,
            "french_language_support": "Partial",
            "aesthetic_confidence_index": False,
        },
    }

    return {
        "report_title": "AesthetiCite Gold Benchmark Report",
        "report_subtitle": "Unilabs France Pilot Evaluation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": "VeriDoc v2",
        "mode": mode,
        "total_wall_time_s": total_wall_s,

        "summary": {
            "total_questions": n_total,
            "questions_en": len(en_results),
            "questions_fr": len(fr_results),
            "overall_score": round(overall_score * 100, 1),
            "grade": grade,
            "citation_rate": citation_rate,
            "aci": aci_summary,
            "avg_aci": avg_aci,
            "median_aci": median_aci,
            "aci_std": aci_std,
            "tool_triggering_rate": tool_rate,
            "protocol_activation_rate_safety": protocol_rate_safety,
            "error_rate": round(100 * n_errors / max(1, n_total), 1),
            "avg_latency_s": avg_latency,
            "p95_latency_s": p95_latency,
        },

        "aci_distribution": {
            "high_confidence": {"count": aci_high, "range": "7.0-10.0"},
            "moderate_confidence": {"count": aci_mid, "range": "4.0-6.9"},
            "low_confidence": {"count": aci_low, "range": "0.1-3.9"},
            "no_score": {"count": len(all_results) - len(aci_values)},
        },

        "language_performance": {
            "english": {
                "questions": len(en_results),
                "citation_rate": round(100 * en_cited / max(1, len(en_results)), 1),
                "aci": en_aci,
            },
            "french": {
                "questions": len(fr_results),
                "citation_rate": round(100 * fr_cited / max(1, len(fr_results)), 1),
                "aci": fr_aci,
            },
        },

        "category_breakdown": category_breakdown,

        "differentiators_vs_generic_ai": generic_comparison,

        "pilot_kpi_mapping": {
            "clinical_usefulness": {
                "metric": "Citation Rate + ACI Score",
                "value": f"{citation_rate}% cited, ACI {avg_aci}/10 (scored), {aci_summary['avg_aci_all_including_zeros']}/10 (all), coverage {aci_summary['aci_coverage_pct']}%",
                "assessment": "Strong" if citation_rate >= 70 and avg_aci >= 5 else "Moderate" if citation_rate >= 50 else "Needs improvement",
            },
            "safety_first_behavior": {
                "metric": "Complication Protocol Activation on Safety Questions",
                "value": f"{protocol_rate_safety}% ({n_safety_protocol}/{n_safety} safety questions)",
                "assessment": "Strong" if protocol_rate_safety >= 60 else "Moderate" if protocol_rate_safety >= 30 else "Needs improvement",
            },
            "aesthetic_precision": {
                "metric": "Inline Tool Triggering",
                "value": f"{tool_rate}% ({n_tools}/{n_total} questions)",
                "assessment": "Active" if n_tools > 0 else "Not triggered",
            },
            "french_readiness": {
                "metric": "French Question Performance",
                "value": f"{len(fr_results)} questions, {round(100 * fr_cited / max(1, len(fr_results)), 1)}% cited, ACI {fr_aci['avg_aci_scored_nonzero_only']}/10 (scored), coverage {fr_aci['aci_coverage_pct']}%",
                "assessment": "Ready" if fr_cited > 0 else "Needs improvement",
            },
        },

        "results_en": en_results,
        "results_fr": fr_results,
    }


def run_unilabs_benchmark(engine: Any, mode: str = "fast") -> Dict[str, Any]:
    """Run the full Unilabs-ready benchmark: 30 EN + 10 FR questions with professional report output."""
    t_start = time.time()
    en_results = _run_questions(engine, GOLD_QUESTIONS_30, QUESTION_CATEGORIES, mode)
    fr_results = _run_questions(engine, GOLD_QUESTIONS_FR, FR_QUESTION_CATEGORIES, mode)
    total_wall_s = round(time.time() - t_start, 1)
    return compile_unilabs_report(en_results, fr_results, mode, total_wall_s)
