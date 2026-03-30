"""
AesthetiCite Model Router + Graph RAG + Prompt Optimizer
==========================================================
Implements improvements #2, #4, #10, #15:
  #4  — DeepSeek-R1 routing for DeepConsult/complex queries
  #15 — DSPy-style prompt optimization (systematic A/B on ACI objective)
  #2  — Graph RAG: complication relationship graph
  #10 — Graph-based complication entity mapping

Integration:
  1. In ask_v2.py / veridoc.py, replace direct model call with:
       from app.engine.model_router import route_model, AESTHETIC_GRAPH
       model = route_model(question, mode)

  2. For graph-enriched context in complication queries:
       from app.engine.model_router import graph_enrich_query
       graph_context = graph_enrich_query(question)
       # prepend graph_context to your evidence prompt

  3. Run prompt optimizer (offline, before production):
       from app.engine.model_router import PromptOptimizer
       optimizer = PromptOptimizer()
       best_prompt = optimizer.optimize(eval_set, metric_fn=lambda r: r["aci_score"])
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

OPENAI_API_KEY  = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")
DEEPSEEK_API_KEY  = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# ─────────────────────────────────────────────────────────────────────────────
# Improvement #4 — DeepSeek-R1 model routing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    model_id: str
    api_key: str
    base_url: str
    max_tokens: int = 2000
    temperature: float = 0.2
    label: str = ""


# Model registry
MODELS: Dict[str, ModelConfig] = {
    "gpt-4o-mini": ModelConfig(
        model_id="gpt-4o-mini",
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        max_tokens=2000,
        temperature=0.2,
        label="Standard (GPT-4o-mini)",
    ),
    "deepseek-r1": ModelConfig(
        model_id="deepseek-reasoner",  # DeepSeek-R1 model ID
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        max_tokens=4000,
        temperature=0.1,
        label="Deep reasoning (DeepSeek-R1)",
    ),
}

# Query signals that trigger DeepSeek-R1 routing
DEEPSEEK_TRIGGERS = {
    "modes": {"deepconsult", "deep_consult", "deepconsult_phd"},
    "keywords": [
        "systematic review", "meta-analysis", "compare studies",
        "evidence synthesis", "conflicting evidence", "disagree",
        "literature disagreement", "multiple studies",
        "complex case", "differential diagnosis", "mechanism",
        "pathophysiology", "pharmacokinetics",
    ],
}


def route_model(question: str, mode: str = "fast") -> ModelConfig:
    """
    Improvement #4: Route to DeepSeek-R1 for DeepConsult and complex queries.

    DeepSeek-R1 is ~10x more capable for multi-step reasoning at comparable
    or lower cost. Route it when:
    - mode is deepconsult
    - question contains multi-study synthesis signals
    - question asks for mechanism/pathophysiology (requires chain-of-thought)

    Falls back to gpt-4o-mini if DeepSeek key is not set.
    """
    if not DEEPSEEK_API_KEY:
        logger.debug("[Router] DeepSeek key not set, using gpt-4o-mini")
        return MODELS["gpt-4o-mini"]

    # Mode-based routing
    if mode.lower() in DEEPSEEK_TRIGGERS["modes"]:
        logger.info(f"[Router] DeepConsult mode → DeepSeek-R1")
        return MODELS["deepseek-r1"]

    # Keyword-based routing
    q_lower = question.lower()
    if any(kw in q_lower for kw in DEEPSEEK_TRIGGERS["keywords"]):
        logger.info(f"[Router] Complex query detected → DeepSeek-R1")
        return MODELS["deepseek-r1"]

    return MODELS["gpt-4o-mini"]


def get_model_headers(config: ModelConfig) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Improvements #2 + #10 — Graph RAG: complication entity graph
#
# Encodes: procedure → region → danger_zone → complication → protocol
# Enables multi-hop queries: "HA filler in nasolabial fold + anticoagulation"
# → traverses: filler → nasolabial fold → angular artery danger zone
#              + anticoagulation → bleeding risk modifier
#              → vascular_occlusion protocol (high weight)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GraphNode:
    id: str
    label: str
    node_type: str          # procedure | region | danger_zone | complication | protocol | product | risk_factor
    aliases: List[str] = field(default_factory=list)
    clinical_note: str = ""


@dataclass
class GraphEdge:
    source: str             # node id
    target: str             # node id
    relation: str           # associated_with | located_in | risks | treated_by | modifies
    weight: float = 1.0


class ComplicationGraph:
    """
    Lightweight in-memory knowledge graph for aesthetic injectable medicine.
    Used to enrich retrieval queries with related entities and pathways.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self._adjacency: Dict[str, List[Tuple[str, str, float]]] = {}
        self._build()

    def _add_node(self, n: GraphNode) -> None:
        self.nodes[n.id] = n

    def _add_edge(self, e: GraphEdge) -> None:
        self.edges.append(e)
        self._adjacency.setdefault(e.source, []).append((e.target, e.relation, e.weight))
        self._adjacency.setdefault(e.target, []).append((e.source, e.relation, e.weight))

    def _build(self) -> None:
        # ── Products ──────────────────────────────────────────────────────────
        for pid, label, aliases in [
            ("ha_filler",    "Hyaluronic Acid Filler",    ["HA filler", "juvederm", "restylane", "belotero", "teosyal"]),
            ("neurotoxin",   "Botulinum Toxin",            ["botox", "dysport", "xeomin", "bocouture", "azzalure"]),
            ("biostimulator","Biostimulator",              ["sculptra", "radiesse", "polynucleotides", "plla"]),
        ]:
            self._add_node(GraphNode(pid, label, "product", aliases))

        # ── Procedures ────────────────────────────────────────────────────────
        for pid, label, aliases in [
            ("lip_filler",         "Lip Filler",               ["lip augmentation", "lip enhancement"]),
            ("tear_trough_filler", "Tear Trough Filler",        ["infraorbital filler", "under eye filler"]),
            ("nasolabial_filler",  "Nasolabial Fold Filler",    ["NLF filler", "smile line filler"]),
            ("glabellar_toxin",    "Glabellar Toxin",           ["frown line toxin", "glabella botox"]),
            ("jawline_filler",     "Jawline Filler",            ["mandibular filler", "chin filler"]),
            ("nose_filler",        "Non-Surgical Rhinoplasty",  ["nose filler", "NSR", "nasal filler"]),
            ("temporal_filler",    "Temple Filler",             ["temporal hollowing", "temple augmentation"]),
        ]:
            self._add_node(GraphNode(pid, label, "procedure", aliases))

        # ── Anatomical regions ────────────────────────────────────────────────
        for pid, label in [
            ("periorbital",  "Periorbital Region"),
            ("nasolabial",   "Nasolabial Region"),
            ("glabella",     "Glabella"),
            ("lips",         "Lips"),
            ("nose",         "Nasal Region"),
            ("jawline",      "Jawline"),
            ("temple",       "Temple"),
        ]:
            self._add_node(GraphNode(pid, label, "region"))

        # ── Danger zones ──────────────────────────────────────────────────────
        for pid, label, note in [
            ("angular_artery",   "Angular Artery",            "Terminal branch of facial artery; occlusion → nasolabial skin necrosis"),
            ("supratrochlear",   "Supratrochlear Artery",      "Glabellar injection risk; retrograde emboli → ocular artery"),
            ("infraorbital_art", "Infraorbital Artery",        "Tear trough / lower lid risk"),
            ("nasal_tip_art",    "Nasal Tip Vessels",          "Highest per-procedure vascular risk in aesthetics"),
            ("dorsal_nasal",     "Dorsal Nasal Artery",        "Risk of skin necrosis and vision loss"),
            ("facial_artery",    "Facial Artery",              "Lateral lip and chin; occlusion → lip necrosis"),
            ("temporal_artery",  "Superficial Temporal Artery","Temple filler risk"),
        ]:
            self._add_node(GraphNode(pid, label, "danger_zone", clinical_note=note))

        # ── Complications ─────────────────────────────────────────────────────
        for pid, label in [
            ("vascular_occlusion",  "Vascular Occlusion"),
            ("vision_loss",         "Vision Loss / Ophthalmic Artery Occlusion"),
            ("skin_necrosis",       "Skin Necrosis"),
            ("tyndall_effect",      "Tyndall Effect"),
            ("ptosis",              "Ptosis"),
            ("infection_biofilm",   "Infection / Biofilm"),
            ("filler_nodule",       "Filler Nodule"),
            ("anaphylaxis",         "Anaphylaxis"),
            ("bruising_haematoma",  "Bruising / Haematoma"),
        ]:
            self._add_node(GraphNode(pid, label, "complication"))

        # ── Risk factors ──────────────────────────────────────────────────────
        for pid, label, aliases in [
            ("anticoagulation", "Anticoagulation", ["warfarin", "apixaban", "rivaroxaban", "NOAC", "blood thinners"]),
            ("prior_vascular",  "Prior Vascular Event", ["previous vascular occlusion", "prior ischaemia"]),
            ("smoking",         "Smoking", ["smoker", "tobacco"]),
            ("active_infection","Active Infection", ["infection near site", "herpes active"]),
            ("needle_technique","Needle Technique", ["sharp needle", "needle injection"]),
            ("deep_injection",  "Deep Injection Plane", ["periosteal", "supraperiosteal"]),
        ]:
            self._add_node(GraphNode(pid, label, "risk_factor", aliases))

        # ── Protocols ─────────────────────────────────────────────────────────
        for pid, label in [
            ("proto_vascular_occlusion", "Vascular Occlusion Protocol"),
            ("proto_anaphylaxis",        "Anaphylaxis Protocol"),
            ("proto_tyndall",            "Tyndall Effect Protocol"),
            ("proto_ptosis",             "Ptosis Protocol"),
            ("proto_infection",          "Infection/Biofilm Protocol"),
            ("proto_nodule",             "Filler Nodule Protocol"),
        ]:
            self._add_node(GraphNode(pid, label, "protocol"))

        # ── Edges ─────────────────────────────────────────────────────────────
        edges = [
            # Product → Procedure
            ("ha_filler",          "lip_filler",           "used_in",         1.0),
            ("ha_filler",          "tear_trough_filler",   "used_in",         1.0),
            ("ha_filler",          "nasolabial_filler",    "used_in",         1.0),
            ("ha_filler",          "nose_filler",          "used_in",         1.0),
            ("ha_filler",          "jawline_filler",       "used_in",         1.0),
            ("neurotoxin",         "glabellar_toxin",      "used_in",         1.0),

            # Procedure → Region
            ("lip_filler",         "lips",                 "located_in",      1.0),
            ("tear_trough_filler", "periorbital",          "located_in",      1.0),
            ("nasolabial_filler",  "nasolabial",           "located_in",      1.0),
            ("glabellar_toxin",    "glabella",             "located_in",      1.0),
            ("nose_filler",        "nose",                 "located_in",      1.0),
            ("temporal_filler",    "temple",               "located_in",      1.0),

            # Region → Danger zone
            ("nasolabial",         "angular_artery",       "contains",        0.9),
            ("glabella",           "supratrochlear",       "contains",        0.95),
            ("periorbital",        "infraorbital_art",     "contains",        0.85),
            ("nose",               "nasal_tip_art",        "contains",        1.0),
            ("nose",               "dorsal_nasal",         "contains",        0.95),
            ("lips",               "facial_artery",        "contains",        0.85),
            ("temple",             "temporal_artery",      "contains",        0.8),

            # Danger zone → Complication
            ("angular_artery",     "vascular_occlusion",  "risks",           1.0),
            ("supratrochlear",     "vision_loss",          "risks",           1.0),
            ("supratrochlear",     "vascular_occlusion",  "risks",           0.95),
            ("infraorbital_art",   "vascular_occlusion",  "risks",           0.9),
            ("nasal_tip_art",      "vascular_occlusion",  "risks",           1.0),
            ("nasal_tip_art",      "skin_necrosis",        "risks",           0.95),
            ("facial_artery",      "vascular_occlusion",  "risks",           0.85),

            # Complication → Protocol
            ("vascular_occlusion", "proto_vascular_occlusion", "treated_by", 1.0),
            ("vision_loss",        "proto_vascular_occlusion", "treated_by", 1.0),
            ("skin_necrosis",      "proto_vascular_occlusion", "treated_by", 0.85),
            ("tyndall_effect",     "proto_tyndall",         "treated_by",    1.0),
            ("ptosis",             "proto_ptosis",          "treated_by",    1.0),
            ("infection_biofilm",  "proto_infection",       "treated_by",    1.0),
            ("filler_nodule",      "proto_nodule",          "treated_by",    1.0),
            ("anaphylaxis",        "proto_anaphylaxis",     "treated_by",    1.0),

            # Risk factor → Complication (modifies weight)
            ("anticoagulation",    "bruising_haematoma",   "increases_risk",  0.9),
            ("anticoagulation",    "vascular_occlusion",   "increases_risk",  0.5),
            ("prior_vascular",     "vascular_occlusion",   "increases_risk",  1.0),
            ("needle_technique",   "vascular_occlusion",   "increases_risk",  0.7),
            ("active_infection",   "infection_biofilm",    "increases_risk",  1.0),

            # HA filler → Tyndall / treatable complications
            ("ha_filler",          "tyndall_effect",       "can_cause",       0.6),
            ("ha_filler",          "filler_nodule",        "can_cause",       0.5),
        ]

        for src, tgt, rel, wt in edges:
            self._add_edge(GraphEdge(src, tgt, rel, wt))

    def find_node_by_alias(self, text: str) -> List[GraphNode]:
        """Find nodes matching any alias in the given text."""
        text_lower = text.lower()
        matches: List[GraphNode] = []
        for node in self.nodes.values():
            if node.label.lower() in text_lower:
                matches.append(node)
                continue
            for alias in node.aliases:
                if alias.lower() in text_lower:
                    matches.append(node)
                    break
        return matches

    def get_neighbours(self, node_id: str, max_hops: int = 2) -> List[GraphNode]:
        """BFS to retrieve related nodes within max_hops."""
        visited = {node_id}
        queue = [(node_id, 0)]
        result: List[GraphNode] = []
        while queue:
            current, depth = queue.pop(0)
            if depth >= max_hops:
                continue
            for neighbour_id, _, _ in self._adjacency.get(current, []):
                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    if neighbour_id in self.nodes:
                        result.append(self.nodes[neighbour_id])
                    queue.append((neighbour_id, depth + 1))
        return result

    def get_protocol_for_query(self, question: str) -> List[str]:
        """Return protocol node IDs relevant to a question."""
        matched_nodes = self.find_node_by_alias(question)
        protocols: List[str] = []
        for node in matched_nodes:
            for neighbour in self.get_neighbours(node.id, max_hops=3):
                if neighbour.node_type == "protocol":
                    protocols.append(neighbour.id)
        return list(set(protocols))


# Singleton graph instance
AESTHETIC_GRAPH = ComplicationGraph()


def graph_enrich_query(question: str, max_context_length: int = 400) -> str:
    """
    Improvement #2 + #10: Build a graph context block for the answer prompt.

    Usage in veridoc.py:
        from app.engine.model_router import graph_enrich_query
        graph_ctx = graph_enrich_query(question)
        if graph_ctx:
            prompt = f"KNOWLEDGE GRAPH CONTEXT:\n{graph_ctx}\n\n" + prompt

    Returns empty string if no relevant entities found.
    """
    matched = AESTHETIC_GRAPH.find_node_by_alias(question)
    if not matched:
        return ""

    lines: List[str] = []
    seen_ids: set = set()

    for node in matched[:4]:  # cap at 4 seed nodes
        if node.id in seen_ids:
            continue
        seen_ids.add(node.id)

        neighbours = AESTHETIC_GRAPH.get_neighbours(node.id, max_hops=2)
        rels = [
            (e.target if e.source == node.id else e.source, e.relation)
            for e in AESTHETIC_GRAPH.edges
            if e.source == node.id or e.target == node.id
        ]

        context_parts = [f"{node.label} ({node.node_type})"]
        if node.clinical_note:
            context_parts.append(f"Note: {node.clinical_note}")
        for neighbour_id, relation in rels[:5]:
            if neighbour_id in AESTHETIC_GRAPH.nodes:
                nb = AESTHETIC_GRAPH.nodes[neighbour_id]
                context_parts.append(f"  → {relation}: {nb.label}")

        lines.append(" | ".join(context_parts[:3]))

    context = "; ".join(lines)
    return context[:max_context_length] if context else ""


# ─────────────────────────────────────────────────────────────────────────────
# Improvement #15 — DSPy-style prompt optimizer
# Systematic A/B on ACI objective function
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_VARIANTS: List[Dict[str, str]] = [
    {
        "id": "v1_baseline",
        "description": "Current baseline",
        "system_suffix": "",
        "preamble": "",
    },
    {
        "id": "v2_chain_of_thought",
        "description": "Chain-of-thought before answer",
        "system_suffix": "\nBefore answering, briefly reason through the evidence hierarchy. Then give your structured answer.",
        "preamble": "REASONING: [think through evidence quality]\n\nANSWER:\n",
    },
    {
        "id": "v3_calibrated",
        "description": "Explicit calibration instruction",
        "system_suffix": "\nFor each key claim, explicitly state the evidence level (guideline/RCT/observational/expert opinion) inline.",
        "preamble": "",
    },
    {
        "id": "v4_structured_sections",
        "description": "Enforce structured output sections",
        "system_suffix": "\nYour answer MUST have exactly these sections: CLINICAL SUMMARY | KEY EVIDENCE | SAFETY CONSIDERATIONS | LIMITATIONS.",
        "preamble": "",
    },
]


class PromptOptimizer:
    """
    Improvement #15: Systematic prompt optimization using ACI as objective.

    Usage (run offline, not in request path):
        from app.engine.model_router import PromptOptimizer

        optimizer = PromptOptimizer()
        results = await optimizer.run_eval(
            questions=["What is the dose of hyaluronidase for vascular occlusion?", ...],
            compute_aci_fn=your_aci_function,
        )
        best = optimizer.best_variant(results)
        print(f"Best prompt variant: {best['variant_id']}, avg ACI={best['mean_aci']:.2f}")
    """

    def __init__(self) -> None:
        self.variants = PROMPT_VARIANTS
        self._results: List[Dict[str, Any]] = []

    async def run_eval(
        self,
        questions: List[str],
        compute_aci_fn: Callable,         # async fn(question, answer, chunks) → float
        retrieve_fn: Optional[Callable] = None,
        n_questions: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Run all prompt variants against a question set and collect ACI scores.
        Returns list of {variant_id, scores, mean_aci}.
        """
        import httpx

        questions_sample = questions[:n_questions]
        results = []

        for variant in self.variants:
            scores: List[float] = []
            for q in questions_sample:
                try:
                    # Simple single-call test (no full RAG pipeline)
                    system = (
                        "You are AesthetiCite, a clinical evidence assistant for aesthetic medicine. "
                        "Use inline citations [S1], [S2] for every claim."
                        + variant["system_suffix"]
                    )
                    user = variant["preamble"] + q

                    payload = {
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user",   "content": user},
                        ],
                        "max_tokens": 600,
                        "temperature": 0.2,
                    }

                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(
                            f"{OPENAI_BASE_URL}/chat/completions",
                            json=payload,
                            headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                                     "Content-Type": "application/json"},
                        )
                        resp.raise_for_status()
                        answer = resp.json()["choices"][0]["message"]["content"]

                    aci = await compute_aci_fn(q, answer, [])
                    scores.append(float(aci))

                except Exception as e:
                    logger.warning(f"[PromptOpt] Eval failed for variant {variant['id']}: {e}")

            mean = sum(scores) / len(scores) if scores else 0.0
            results.append({
                "variant_id":  variant["id"],
                "description": variant["description"],
                "scores":      scores,
                "mean_aci":    round(mean, 3),
                "n_evaluated": len(scores),
            })
            logger.info(f"[PromptOpt] {variant['id']}: mean_aci={mean:.3f} (n={len(scores)})")

        self._results = results
        return results

    def best_variant(self, results: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        data = results or self._results
        return max(data, key=lambda r: r["mean_aci"]) if data else {}

    def report(self) -> str:
        if not self._results:
            return "No evaluation results yet. Run run_eval() first."
        lines = ["Prompt Optimization Results:", "─" * 50]
        for r in sorted(self._results, key=lambda x: x["mean_aci"], reverse=True):
            marker = " ← BEST" if r == self.best_variant() else ""
            lines.append(f"  {r['variant_id']:30s} ACI={r['mean_aci']:.3f}  n={r['n_evaluated']}{marker}")
        return "\n".join(lines)
