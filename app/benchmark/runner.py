"""
Benchmark runner for AesthetiCite Aesthetic Medicine Benchmark (AAMB)
Evaluates answer quality, citation accuracy, and evidence grading.
"""
from __future__ import annotations
import json
import time
import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime

from app.rag.retriever import retrieve_db
from app.rag.citations import to_citations
from app.rag.llm_answer import synthesize_answer
from app.core.safety import safety_screen
from app.rag.improved_pipeline import rerank_simple, uniq_sources, WIDE_K, FINAL_K


@dataclass
class QuestionResult:
    question_id: str
    category: str
    difficulty: str
    question: str
    answer: str
    citations_count: int
    expected_citations_min: int
    evidence_level: Optional[str]
    evidence_level_expected: Optional[str]
    keywords_found: List[str]
    keywords_expected: List[str]
    was_refused: bool
    should_refuse: bool
    latency_ms: int
    scores: Dict[str, float]
    total_score: float


@dataclass
class BenchmarkResult:
    version: str
    run_id: str
    run_date: str
    total_questions: int
    questions_answered: int
    questions_refused: int
    correct_refusals: int
    incorrect_refusals: int
    category_scores: Dict[str, float]
    overall_score: float
    average_latency_ms: float
    question_results: List[Dict]


def load_benchmark_questions() -> Dict:
    """Load benchmark questions from JSON file."""
    questions_path = Path(__file__).parent / "questions.json"
    with open(questions_path, "r") as f:
        return json.load(f)


def calculate_keyword_score(answer: str, expected_keywords: List[str]) -> Tuple[float, List[str]]:
    """Calculate keyword coverage score."""
    if not expected_keywords:
        return 1.0, []
    
    answer_lower = answer.lower()
    found = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    score = len(found) / len(expected_keywords) if expected_keywords else 1.0
    return score, found


def calculate_citation_score(citations_count: int, expected_min: int) -> float:
    """Calculate citation quality score."""
    if expected_min == 0:
        return 1.0
    if citations_count >= expected_min:
        return 1.0
    elif citations_count > 0:
        return citations_count / expected_min
    return 0.0


def calculate_evidence_level_score(actual: Optional[str], expected: Optional[str]) -> float:
    """Calculate evidence grading accuracy score."""
    if expected is None:
        return 1.0
    if actual is None:
        return 0.0
    
    level_order = {"I": 1, "II": 2, "III": 3, "IV": 4}
    actual_num = level_order.get(actual.upper().replace("LEVEL ", ""), 5)
    expected_num = level_order.get(expected.upper().replace("LEVEL ", ""), 5)
    
    diff = abs(actual_num - expected_num)
    if diff == 0:
        return 1.0
    elif diff == 1:
        return 0.7
    elif diff == 2:
        return 0.3
    return 0.0


def calculate_answer_relevance_score(answer: str, gold_answer: str, keywords: List[str]) -> float:
    """Calculate answer relevance score based on semantic similarity approximation."""
    if not answer.strip():
        return 0.0
    
    gold_words = set(gold_answer.lower().split())
    answer_words = set(answer.lower().split())
    
    common_words = gold_words.intersection(answer_words)
    jaccard = len(common_words) / len(gold_words.union(answer_words)) if gold_words.union(answer_words) else 0
    
    keyword_score, _ = calculate_keyword_score(answer, keywords)
    
    return 0.4 * jaccard + 0.6 * keyword_score


def calculate_refusal_score(was_refused: bool, should_refuse: bool) -> float:
    """Calculate refusal accuracy score."""
    if was_refused == should_refuse:
        return 1.0
    return 0.0


def extract_evidence_level(answer: str) -> Optional[str]:
    """Extract evidence level from answer text."""
    patterns = [
        r"Level\s*(I{1,3}V?|[1-4])",
        r"Tier\s*([A-C])",
        r"evidence\s*level\s*(I{1,3}V?|[1-4])",
    ]
    for pattern in patterns:
        match = re.search(pattern, answer, re.IGNORECASE)
        if match:
            level = match.group(1).upper()
            tier_map = {"A": "I", "B": "II", "C": "III"}
            return tier_map.get(level, level)
    return None


def run_single_question(
    db,
    question_data: Dict,
    mode: str = "clinic",
    domain: str = "aesthetic_medicine"
) -> QuestionResult:
    """Run benchmark on a single question."""
    t0 = time.perf_counter()
    
    question = question_data["question"]
    
    safety = safety_screen(question)
    if not safety.allowed:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return QuestionResult(
            question_id=question_data["id"],
            category=question_data["category"],
            difficulty=question_data["difficulty"],
            question=question,
            answer="[REFUSED BY SAFETY]",
            citations_count=0,
            expected_citations_min=question_data["expected_citations_min"],
            evidence_level=None,
            evidence_level_expected=question_data.get("evidence_level_expected"),
            keywords_found=[],
            keywords_expected=question_data["expected_keywords"],
            was_refused=True,
            should_refuse=question_data.get("must_refuse", False),
            latency_ms=latency_ms,
            scores={},
            total_score=calculate_refusal_score(True, question_data.get("must_refuse", False))
        )
    
    # Wide retrieval + quality-weighted reranking for better accuracy
    wide_retrieved = retrieve_db(db=db, question=question, domain=domain, k=WIDE_K)
    reranked = rerank_simple(question, wide_retrieved)
    retrieved = reranked[:FINAL_K]
    citations = to_citations(retrieved)
    
    if len(uniq_sources(retrieved)) < 2:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return QuestionResult(
            question_id=question_data["id"],
            category=question_data["category"],
            difficulty=question_data["difficulty"],
            question=question,
            answer="[INSUFFICIENT EVIDENCE]",
            citations_count=len(citations),
            expected_citations_min=question_data["expected_citations_min"],
            evidence_level=None,
            evidence_level_expected=question_data.get("evidence_level_expected"),
            keywords_found=[],
            keywords_expected=question_data["expected_keywords"],
            was_refused=True,
            should_refuse=question_data.get("must_refuse", False),
            latency_ms=latency_ms,
            scores={},
            total_score=0.0
        )
    
    answer = synthesize_answer(
        question=question,
        mode=mode,
        domain=domain,
        retrieved=retrieved
    )
    
    latency_ms = int((time.perf_counter() - t0) * 1000)
    
    evidence_level = extract_evidence_level(answer)
    keyword_score, found_keywords = calculate_keyword_score(
        answer, question_data["expected_keywords"]
    )
    citation_score = calculate_citation_score(
        len(citations), question_data["expected_citations_min"]
    )
    evidence_score = calculate_evidence_level_score(
        evidence_level, question_data.get("evidence_level_expected")
    )
    relevance_score = calculate_answer_relevance_score(
        answer, question_data["gold_answer"], question_data["expected_keywords"]
    )
    refusal_score = calculate_refusal_score(False, question_data.get("must_refuse", False))
    
    scores = {
        "answer_relevance": relevance_score,
        "citation_quality": citation_score,
        "evidence_grading": evidence_score,
        "keyword_coverage": keyword_score,
        "refusal_accuracy": refusal_score,
    }
    
    weights = {
        "answer_relevance": 0.30,
        "citation_quality": 0.25,
        "evidence_grading": 0.20,
        "keyword_coverage": 0.15,
        "refusal_accuracy": 0.10,
    }
    
    total_score = sum(scores[k] * weights[k] for k in scores)
    
    return QuestionResult(
        question_id=question_data["id"],
        category=question_data["category"],
        difficulty=question_data["difficulty"],
        question=question,
        answer=answer[:500] + "..." if len(answer) > 500 else answer,
        citations_count=len(citations),
        expected_citations_min=question_data["expected_citations_min"],
        evidence_level=evidence_level,
        evidence_level_expected=question_data.get("evidence_level_expected"),
        keywords_found=found_keywords,
        keywords_expected=question_data["expected_keywords"],
        was_refused=False,
        should_refuse=question_data.get("must_refuse", False),
        latency_ms=latency_ms,
        scores=scores,
        total_score=total_score
    )


def run_benchmark(
    db,
    categories: Optional[List[str]] = None,
    max_questions: Optional[int] = None,
    mode: str = "clinic"
) -> BenchmarkResult:
    """Run full benchmark suite."""
    benchmark_data = load_benchmark_questions()
    questions = benchmark_data["questions"]
    
    if categories:
        questions = [q for q in questions if q["category"] in categories]
    
    if max_questions:
        questions = questions[:max_questions]
    
    results = []
    category_scores: Dict[str, List[float]] = {}
    total_latency = 0
    questions_refused = 0
    correct_refusals = 0
    incorrect_refusals = 0
    
    for q in questions:
        result = run_single_question(db, q, mode=mode)
        results.append(result)
        
        if result.category not in category_scores:
            category_scores[result.category] = []
        category_scores[result.category].append(result.total_score)
        
        total_latency += result.latency_ms
        
        if result.was_refused:
            questions_refused += 1
            if result.should_refuse:
                correct_refusals += 1
            else:
                incorrect_refusals += 1
    
    category_averages = {
        cat: sum(scores) / len(scores) if scores else 0
        for cat, scores in category_scores.items()
    }
    
    overall_score = sum(r.total_score for r in results) / len(results) if results else 0
    avg_latency = total_latency / len(results) if results else 0
    
    run_id = f"AAMB-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    return BenchmarkResult(
        version=benchmark_data["version"],
        run_id=run_id,
        run_date=datetime.now().isoformat(),
        total_questions=len(questions),
        questions_answered=len(results) - questions_refused,
        questions_refused=questions_refused,
        correct_refusals=correct_refusals,
        incorrect_refusals=incorrect_refusals,
        category_scores=category_averages,
        overall_score=overall_score,
        average_latency_ms=avg_latency,
        question_results=[asdict(r) for r in results]
    )
