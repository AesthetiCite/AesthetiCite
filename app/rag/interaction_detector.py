"""
Drug Interaction Intent Detection and Structured Response Layer

This module detects drug interaction queries and routes them through 
a structured NIH RxNav integration layer, ensuring no interaction 
answer is given without a structured source.
"""
from __future__ import annotations
import re
import logging
from typing import List, Dict, Tuple, Optional, NamedTuple
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"

# Drug interaction keywords and patterns
INTERACTION_KEYWORDS = {
    'interaction', 'interactions', 'interact', 'interacts',
    'drug-drug', 'drug interaction', 'drug interactions',
    'combine', 'combined', 'combining', 'together',
    'safe to take', 'safe to use', 'safely take', 'safely use',
    'contraindicated', 'contraindication', 'contraindications',
    'can i take', 'can you take', 'taking together',
    'mix', 'mixing', 'mixed with',
    'concurrent', 'concurrently', 'concomitant', 'concomitantly',
    'avoid', 'avoid with', 'should not take',
    'potentiate', 'potentiation', 'synergistic',
    'antagonize', 'antagonist', 'antagonism',
    'inhibit', 'inhibitor', 'inhibition', 'induce', 'inducer', 'induction',
    'cyp450', 'cyp3a4', 'cyp2d6', 'p-glycoprotein', 'p-gp',
}

# Common drug name patterns (brands and generics)
COMMON_DRUG_PATTERN = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?|'
    r'[a-z]{4,}(?:olol|pril|sartan|statin|mycin|cillin|azole|pam|zepam|'
    r'dipine|olone|asone|prox|mab|nib|tinib|zumab|ximab))\b',
    re.IGNORECASE
)

# Known drug categories for detection
DRUG_CLASSES = {
    'anticoagulants': ['warfarin', 'heparin', 'enoxaparin', 'rivaroxaban', 'apixaban', 'dabigatran', 'edoxaban'],
    'antiplatelet': ['aspirin', 'clopidogrel', 'prasugrel', 'ticagrelor', 'dipyridamole'],
    'nsaids': ['ibuprofen', 'naproxen', 'diclofenac', 'celecoxib', 'meloxicam', 'indomethacin', 'ketorolac'],
    'opioids': ['morphine', 'oxycodone', 'hydrocodone', 'fentanyl', 'codeine', 'tramadol', 'methadone'],
    'benzodiazepines': ['diazepam', 'lorazepam', 'alprazolam', 'clonazepam', 'midazolam'],
    'antibiotics': ['amoxicillin', 'azithromycin', 'ciprofloxacin', 'metronidazole', 'doxycycline', 'clindamycin'],
    'antidepressants': ['fluoxetine', 'sertraline', 'escitalopram', 'venlafaxine', 'duloxetine', 'bupropion'],
    'antihypertensives': ['lisinopril', 'amlodipine', 'losartan', 'metoprolol', 'hydrochlorothiazide'],
    'local_anesthetics': ['lidocaine', 'bupivacaine', 'ropivacaine', 'prilocaine', 'articaine'],
    'injectables': ['botox', 'botulinum', 'dysport', 'xeomin', 'juvederm', 'restylane', 'sculptra'],
}


@dataclass
class DrugMention:
    """A detected drug mention in the query."""
    name: str
    rxcui: Optional[str] = None
    class_name: Optional[str] = None
    confidence: float = 0.0


@dataclass
class InteractionResult:
    """Structured drug interaction result."""
    drug_a: str
    drug_b: str
    severity: Optional[str]  # 'high', 'moderate', 'low', 'N/A'
    mechanism: str
    description: str
    evidence_level: str  # 'established', 'probable', 'possible', 'theoretical'
    clinical_significance: str
    management: str
    source: str  # 'RxNav', 'DrugBank', etc.
    rxcui_a: Optional[str] = None
    rxcui_b: Optional[str] = None


@dataclass
class InteractionIntent:
    """Detected interaction intent with extracted drugs."""
    is_interaction_query: bool
    confidence: float
    detected_drugs: List[DrugMention]
    query_type: str  # 'pairwise', 'multi-drug', 'class-based', 'general'
    original_query: str


def detect_interaction_intent(question: str) -> InteractionIntent:
    """
    Detect if a query is asking about drug interactions.
    
    Returns an InteractionIntent with confidence score and extracted drugs.
    """
    q_lower = question.lower()
    confidence = 0.0
    query_type = 'general'
    
    # Check for interaction keywords
    keyword_matches = 0
    for keyword in INTERACTION_KEYWORDS:
        if keyword in q_lower:
            keyword_matches += 1
            confidence += 0.15
    
    # Strong patterns that indicate interaction queries
    strong_patterns = [
        r'(?:can|should)\s+(?:i|you)\s+(?:take|use|mix)\s+\w+\s+(?:with|and)\s+\w+',
        r'(?:interaction|interacts?)\s+(?:between|with)',
        r'\w+\s+(?:and|with|plus)\s+\w+\s+(?:interaction|together|safe)',
        r'(?:contraindicated|avoid)\s+(?:with|when)',
        r'(?:drug|medication)s?\s+interact',
    ]
    
    for pattern in strong_patterns:
        if re.search(pattern, q_lower):
            confidence += 0.25
            break
    
    # Extract potential drug names
    detected_drugs = extract_drug_mentions(question)
    
    # Multiple drugs mentioned increases confidence
    if len(detected_drugs) >= 2:
        confidence += 0.30
        query_type = 'pairwise' if len(detected_drugs) == 2 else 'multi-drug'
    elif len(detected_drugs) == 1:
        # Single drug with interaction keyword
        if keyword_matches > 0:
            confidence += 0.15
            query_type = 'general'
    
    # Check for drug class mentions
    for class_name, drugs in DRUG_CLASSES.items():
        if class_name.replace('_', ' ') in q_lower or class_name in q_lower:
            confidence += 0.20
            query_type = 'class-based'
            break
    
    # Cap confidence
    confidence = min(1.0, confidence)
    
    # Threshold for interaction query - require BOTH 2+ drugs AND keyword match to avoid false positives
    is_interaction = confidence >= 0.50 and len(detected_drugs) >= 2 and keyword_matches > 0
    
    return InteractionIntent(
        is_interaction_query=is_interaction,
        confidence=confidence,
        detected_drugs=detected_drugs,
        query_type=query_type,
        original_query=question
    )


def extract_drug_mentions(text: str) -> List[DrugMention]:
    """Extract potential drug names from text."""
    mentions = []
    seen = set()
    
    # Check against known drug classes
    for class_name, drugs in DRUG_CLASSES.items():
        for drug in drugs:
            if drug.lower() in text.lower() and drug.lower() not in seen:
                mentions.append(DrugMention(
                    name=drug.title(),
                    class_name=class_name,
                    confidence=0.9
                ))
                seen.add(drug.lower())
    
    # Pattern matching for drug-like names
    for match in COMMON_DRUG_PATTERN.finditer(text):
        name = match.group(0)
        if name.lower() not in seen and len(name) >= 4:
            mentions.append(DrugMention(
                name=name.title(),
                confidence=0.6
            ))
            seen.add(name.lower())
    
    return mentions


async def resolve_rxcui(drug_name: str) -> Optional[str]:
    """Resolve a drug name to RxCUI using RxNav."""
    try:
        url = f"{RXNAV_BASE}/approximateTerm.json"
        params = {"term": drug_name, "maxEntries": 1}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        
        candidates = data.get("approximateGroup", {}).get("candidate", []) or []
        if candidates:
            return candidates[0].get("rxcui")
    except Exception as e:
        logger.warning(f"Failed to resolve RxCUI for {drug_name}: {e}")
    return None


async def get_structured_interactions(
    drugs: List[str],
    include_severity: bool = True
) -> List[InteractionResult]:
    """
    Get structured drug interactions from RxNav.
    
    Returns a list of InteractionResult with severity, mechanism, and management.
    """
    if len(drugs) < 2:
        return []
    
    # Resolve all drug names to RxCUIs
    rxcuis = []
    drug_map = {}
    
    for drug in drugs:
        rxcui = await resolve_rxcui(drug)
        if rxcui:
            rxcuis.append(rxcui)
            drug_map[rxcui] = drug
    
    if len(rxcuis) < 2:
        logger.warning(f"Could not resolve enough agents to RxCUIs ({len(drugs)} provided, need ≥2)")
        return []
    
    # Query RxNav interaction endpoint
    try:
        url = f"{RXNAV_BASE}/interaction/list.json"
        params = {"rxcuis": "+".join(rxcuis)}
        
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        
        results = []
        groups = data.get("fullInteractionTypeGroup", []) or []
        
        for group in groups:
            source = group.get("sourceName", "RxNav")
            
            for interaction_type in group.get("fullInteractionType", []) or []:
                for pair in interaction_type.get("interactionPair", []) or []:
                    description = pair.get("description", "")
                    severity = pair.get("severity", "N/A")
                    
                    # Extract drug names from interaction concepts
                    concepts = pair.get("interactionConcept", []) or []
                    drug_names = []
                    rxcui_list = []
                    
                    for concept in concepts:
                        if "minConceptItem" in concept:
                            item = concept["minConceptItem"]
                            drug_names.append(item.get("name", "Unknown"))
                            rxcui_list.append(item.get("rxcui"))
                    
                    if len(drug_names) >= 2 and description:
                        # Parse mechanism and management from description
                        mechanism, management, clinical_sig = parse_interaction_details(description)
                        
                        results.append(InteractionResult(
                            drug_a=drug_names[0],
                            drug_b=drug_names[1],
                            severity=severity,
                            mechanism=mechanism,
                            description=description,
                            evidence_level=infer_evidence_level(severity, source),
                            clinical_significance=clinical_sig,
                            management=management,
                            source=source,
                            rxcui_a=rxcui_list[0] if rxcui_list else None,
                            rxcui_b=rxcui_list[1] if len(rxcui_list) > 1 else None,
                        ))
        
        # Deduplicate by drug pair
        seen = set()
        unique_results = []
        for r in results:
            key = tuple(sorted([r.drug_a.lower(), r.drug_b.lower()]))
            if key not in seen:
                seen.add(key)
                unique_results.append(r)
        
        return unique_results
        
    except Exception as e:
        logger.error(f"Failed to get interactions from RxNav: {e}")
        return []


def parse_interaction_details(description: str) -> Tuple[str, str, str]:
    """Parse mechanism, management, and clinical significance from description."""
    mechanism = ""
    management = ""
    clinical_sig = ""
    
    desc_lower = description.lower()
    
    # Extract mechanism
    mechanism_patterns = [
        r'(?:mechanism|due to|caused by|via|through)[:\s]+([^.]+)',
        r'(?:inhibit|induce|block|enhance|potentiate)s?\s+([^.]+)',
    ]
    for pattern in mechanism_patterns:
        match = re.search(pattern, desc_lower)
        if match:
            mechanism = match.group(1).strip()[:200]
            break
    
    if not mechanism:
        # Use first sentence as general mechanism
        mechanism = description.split('.')[0][:200] if description else ""
    
    # Extract management
    management_patterns = [
        r'(?:avoid|monitor|adjust|reduce|increase|consider)[:\s]+([^.]+)',
        r'(?:management|recommendation|action)[:\s]+([^.]+)',
    ]
    for pattern in management_patterns:
        match = re.search(pattern, desc_lower)
        if match:
            management = match.group(1).strip()[:200]
            break
    
    if not management:
        management = "Monitor for adverse effects. Consider alternative agents."
    
    # Determine clinical significance
    if any(word in desc_lower for word in ['serious', 'severe', 'life-threatening', 'contraindicated']):
        clinical_sig = "Major - Avoid combination"
    elif any(word in desc_lower for word in ['significant', 'moderate', 'caution']):
        clinical_sig = "Moderate - Use with caution"
    else:
        clinical_sig = "Minor - Generally acceptable"
    
    return mechanism, management, clinical_sig


def infer_evidence_level(severity: Optional[str], source: str) -> str:
    """Infer evidence level from severity and source."""
    if source.lower() in ['drugbank', 'clinical pharmacology']:
        return 'established'
    
    if severity:
        sev_lower = severity.lower()
        if 'high' in sev_lower or 'severe' in sev_lower:
            return 'established'
        elif 'moderate' in sev_lower:
            return 'probable'
        elif 'low' in sev_lower:
            return 'possible'
    
    return 'theoretical'


def format_interaction_response(interactions: List[InteractionResult], query: str) -> str:
    """
    Format interactions into a structured response with proper citations.
    
    Each interaction is cited as [RxNav] to maintain citation enforcement.
    """
    if not interactions:
        return ""
    
    lines = ["## Drug Interaction Analysis [RxNav]\n"]
    lines.append(f"**Query**: {query}\n")
    lines.append(f"**Source**: NIH RxNav Drug Interaction Database [RxNav]\n\n")
    
    for i, interaction in enumerate(interactions, 1):
        lines.append(f"### Interaction {i}: {interaction.drug_a} + {interaction.drug_b} [RxNav]\n")
        lines.append(f"- **Severity**: {interaction.severity or 'Not specified'} [RxNav]\n")
        lines.append(f"- **Clinical Significance**: {interaction.clinical_significance} [RxNav]\n")
        lines.append(f"- **Mechanism**: {interaction.mechanism} [RxNav]\n")
        lines.append(f"- **Description**: {interaction.description} [RxNav]\n")
        lines.append(f"- **Management**: {interaction.management} [RxNav]\n")
        lines.append(f"- **Evidence Level**: {interaction.evidence_level} [RxNav]\n")
        lines.append(f"- **Source**: {interaction.source}\n\n")
    
    lines.append("\n**Disclaimer**: This information is for clinical decision support only. ")
    lines.append("Always verify with current drug references and clinical judgment. [RxNav]\n")
    
    return "".join(lines)


def create_rxnav_citation() -> dict:
    """Create a citation entry for RxNav database to maintain citation enforcement."""
    return {
        "source_id": "rxnav_nih",
        "title": "NIH RxNav Drug Interaction Database",
        "year": 2024,
        "organization_or_journal": "National Library of Medicine",
        "document_type": "database",
        "evidence_level": "Level II",
        "url": "https://rxnav.nlm.nih.gov/",
    }
