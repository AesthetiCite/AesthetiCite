#!/usr/bin/env python3
"""
Prescribing Information Ingestion Script

Ingests FDA-approved prescribing information (PI) documents for major aesthetic products.
Creates structured chunks for:
- Indications
- Contraindications  
- Dosing and Administration
- Warnings and Precautions
- Adverse Reactions

Usage:
    python -m app.scripts.ingest_prescribing_info
"""
from __future__ import annotations
import os
import sys
import json
import hashlib
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.rag.embedder import embed_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Prescribing Information Data for Major Aesthetic Products
# =============================================================================

PRESCRIBING_INFO = {
    # Neurotoxins
    "Botox Cosmetic (OnabotulinumtoxinA)": {
        "manufacturer": "Allergan",
        "fda_approval": "2002-04-12",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """BOTOX® Cosmetic (onabotulinumtoxinA) is indicated for the temporary improvement in the appearance of:
• Moderate to severe glabellar lines associated with corrugator and/or procerus muscle activity in adult patients
• Moderate to severe lateral canthal lines (crow's feet lines) associated with orbicularis oculi activity in adult patients
• Moderate to severe forehead lines associated with frontalis muscle activity in adult patients""",
            
            "contraindications": """BOTOX® Cosmetic is contraindicated in:
• Patients with known hypersensitivity to any botulinum toxin preparation or to any of the components in the formulation
• Presence of infection at the proposed injection site(s)""",
            
            "dosing": """Glabellar Lines: The recommended dose is 20 Units administered as 5 intramuscular injections of 4 Units each:
- 2 injections in each corrugator muscle
- 1 injection in the procerus muscle

Lateral Canthal Lines: The recommended dose is 24 Units total, administered as 12 Units per side (3 injection sites of 4 Units each) into the lateral portion of the orbicularis oculi muscle.

Forehead Lines: The recommended dose is 20 Units administered as 5 intramuscular injections of 4 Units each into the frontalis muscle.

Maximum Recommended Dose: The maximum cumulative dose in a 3-month interval should not exceed 400 Units.

Reconstitution: Use preservative-free 0.9% Sodium Chloride Injection, USP. Recommended dilutions:
- 100 Unit vial: 2.5 mL for 4 Units/0.1 mL or 4 mL for 2.5 Units/0.1 mL""",
            
            "warnings": """WARNING: DISTANT SPREAD OF TOXIN EFFECT
The effects of BOTOX® and all botulinum toxin products may spread from the area of injection to produce symptoms consistent with botulinum toxin effects. These symptoms have been reported hours to weeks after injection. Swallowing and breathing difficulties can be life threatening and there have been reports of death.

Important Warnings:
• Lack of interchangeability between botulinum toxin products
• Spread of toxin effects beyond injection site
• Hypersensitivity reactions including anaphylaxis
• Pre-existing neuromuscular disorders may be exacerbated
• Dysphagia and breathing difficulties""",
            
            "adverse_reactions": """Most Common Adverse Reactions (≥2%):
• Eyelid ptosis (glabellar lines: 3%)
• Facial paresis (forehead lines: 2%)
• Headache (all areas: 3-9%)
• Injection site reactions (pain, swelling, erythema)
• Brow ptosis
• Eyelid edema"""
        }
    },
    
    "Dysport (AbobotulinumtoxinA)": {
        "manufacturer": "Galderma",
        "fda_approval": "2009-04-29",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """DYSPORT® (abobotulinumtoxinA) is indicated for the temporary improvement in the appearance of:
• Moderate to severe glabellar lines associated with procerus and corrugator muscle activity in adults less than 65 years of age""",
            
            "contraindications": """DYSPORT® is contraindicated in:
• Patients with known hypersensitivity to any botulinum toxin preparation or components of the formulation
• Patients with infection at the proposed injection site
• Patients with known hypersensitivity to cow's milk protein""",
            
            "dosing": """Glabellar Lines: The recommended dose is 50 Units administered as 5 intramuscular injections of 10 Units each:
- 2 injections in each corrugator muscle
- 1 injection in the procerus muscle

Injection Volume: 0.05 mL to 0.1 mL per injection site
Reconstitution: Add 2.5 mL of preservative-free 0.9% sodium chloride injection, USP to obtain 10 Units per 0.05 mL

Note: Units of biological activity of DYSPORT cannot be compared to or converted into Units of other botulinum toxin products.""",
            
            "warnings": """WARNING: DISTANT SPREAD OF TOXIN EFFECT
The effects of DYSPORT® may spread from the area of injection to produce symptoms consistent with botulinum toxin effects. These symptoms have been reported hours to weeks after injection.

Important Warnings:
• No interchangeability with other botulinum toxin products
• Spread of toxin effects
• Hypersensitivity reactions
• Pre-existing neuromuscular disorders
• Dysphagia and breathing difficulties""",
            
            "adverse_reactions": """Most Common Adverse Reactions (≥2%):
• Injection site reactions (pain, edema, erythema)
• Nasopharyngitis
• Headache
• Eyelid ptosis
• Sinusitis
• Nausea"""
        }
    },
    
    "Xeomin (IncobotulinumtoxinA)": {
        "manufacturer": "Merz Pharmaceuticals",
        "fda_approval": "2011-07-21",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """XEOMIN® (incobotulinumtoxinA) is indicated for the temporary improvement in the appearance of:
• Moderate to severe glabellar lines associated with corrugator and/or procerus muscle activity in adult patients""",
            
            "dosing": """Glabellar Lines: The recommended total dose is 20 Units administered as 5 intramuscular injections of 4 Units each:
- 2 injections in each corrugator muscle
- 1 injection in the procerus muscle

Reconstitution: Add 1.25 mL of preservative-free 0.9% Sodium Chloride Injection, USP to obtain 4 Units per 0.1 mL.

Administration: Use 30-33 gauge needle. Inject perpendicular to the skin surface.""",
            
            "warnings": """WARNING: DISTANT SPREAD OF TOXIN EFFECT
Postmarketing reports indicate that the effects of XEOMIN® and all botulinum toxin products may spread from the area of injection to produce symptoms consistent with botulinum toxin effects.

Note: There are no data to support interchangeability with other botulinum toxin products.""",
            
            "adverse_reactions": """Most Common Adverse Reactions (≥2%):
• Headache (5.4%)
• Injection site hematoma
• Injection site reaction
• Blepharoptosis (1.3%)"""
        }
    },
    
    # Hyaluronic Acid Fillers
    "Juvederm Ultra XC": {
        "manufacturer": "Allergan",
        "fda_approval": "2010-06-02",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """JUVÉDERM® Ultra XC injectable gel is indicated for injection into the mid-to-deep dermis for correction of moderate to severe facial wrinkles and folds (such as nasolabial folds).""",
            
            "contraindications": """JUVÉDERM® Ultra XC is contraindicated in:
• Patients with severe allergies with history of anaphylaxis
• Patients with history of allergies to gram-positive bacterial proteins
• Patients with bleeding disorders
• Known hypersensitivity to lidocaine or amide-type local anesthetics
• Known hypersensitivity to hyaluronic acid""",
            
            "dosing": """Administration:
• Inject into the mid-to-deep dermis using a 30-gauge needle
• Inject product slowly and evenly using serial puncture, linear threading, or fanning technique
• Massage the treated area after injection
• Typical treatment requires less than 1.5 mL per treatment
• Touch-up treatments may be needed

Maximum Volume: The maximum recommended dose per treatment session has not been established. Inject the minimum amount of product needed to achieve the desired correction.""",
            
            "warnings": """Important Warnings:
• VASCULAR OCCLUSION: Injection into blood vessels may cause embolization, occlusion, ischemia, infarction, or tissue necrosis
• Product should not be used in patients with known hypersensitivity
• Avoid injection into areas with active inflammation or infection
• Use caution in patients on anticoagulant therapy
• Late-onset inflammatory adverse events have been reported

Signs of Vascular Occlusion:
• Blanching
• Pain
• Dusky discoloration
• Delayed onset of pain

Emergency Management:
• Stop injection immediately
• Inject hyaluronidase (if using HA filler)
• Apply warm compresses
• Apply nitroglycerin paste
• Consider aspirin""",
            
            "adverse_reactions": """Most Common Adverse Reactions:
• Injection site reactions (redness, swelling, pain, tenderness, firmness, lumps/bumps, bruising, itching, discoloration)
• Duration: Typically resolve within 7 days

Serious Adverse Reactions:
• Vascular occlusion (rare but serious)
• Granuloma formation
• Hypersensitivity reactions"""
        }
    },
    
    "Juvederm Voluma XC": {
        "manufacturer": "Allergan",
        "fda_approval": "2013-10-22",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """JUVÉDERM® VOLUMA® XC injectable gel is indicated for deep injection in the cheek area for correction of age-related volume deficit in the midface in adults over the age of 21.""",
            
            "dosing": """Administration:
• Inject into the supraperiosteal or subcutaneous plane using a 25- or 27-gauge needle or 18-gauge cannula
• Maximum recommended dose is 20 mL per treatment session
• Duration of effect: Up to 24 months

Injection Technique:
• Deep injection in the malar, submalar, and zygomatic regions
• Injection should be placed above the periosteum or in the subcutaneous tissue
• Aspiration before injection is recommended
• Inject slowly""",
            
            "warnings": """VASCULAR OCCLUSION WARNING:
Accidental intravascular injection may lead to:
• Embolization
• Occlusion of blood vessels
• Ischemia
• Infarction
• Tissue necrosis

Important Safety Information:
• Use caution in patients on anticoagulant therapy
• Delayed onset adverse reactions reported
• Avoid use with implants or permanent fillers in the same area""",
            
            "adverse_reactions": """Most Common Adverse Reactions:
• Tenderness (88%)
• Swelling (82%)
• Firmness (49%)
• Lumps/Bumps (35%)
• Bruising (31%)
• Pain (24%)
• Redness (23%)
• Discoloration (8%)
• Itching (7%)

Duration: Most injection-related reactions resolve within 30 days"""
        }
    },
    
    "Restylane": {
        "manufacturer": "Galderma",
        "fda_approval": "2003-12-12",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """RESTYLANE® is indicated for:
• Mid-to-deep dermal implantation for correction of moderate to severe facial wrinkles and folds, such as nasolabial folds
• Submucosal implantation for lip augmentation in patients over 21 years of age""",
            
            "dosing": """Administration:
• Inject into mid-to-deep dermis using 30-gauge or smaller needle
• Typical injection volume: 1.0 mL per treatment
• Maximum injection volume not established
• Touch-up treatments at 2-4 weeks may be needed

Lip Augmentation:
• Inject into submucosal plane
• Use serial puncture or linear threading technique""",
            
            "warnings": """Warnings and Precautions:
• Risk of vascular occlusion with intravascular injection
• Do not inject into blood vessels
• Use caution in patients on anticoagulants
• Do not use in patients with severe allergies
• Inflammatory reactions may occur

Vascular Compromise Management:
1. Stop injection immediately
2. Inject hyaluronidase
3. Apply warm compresses
4. Massage the area
5. Monitor closely""",
            
            "adverse_reactions": """Most Common Adverse Reactions:
• Bruising
• Redness
• Swelling
• Pain
• Tenderness
• Itching

Duration: Most reactions resolve within 7 days
Serious: Vascular occlusion, granulomas (rare)"""
        }
    },
    
    "Sculptra Aesthetic": {
        "manufacturer": "Galderma",
        "fda_approval": "2009-07-28",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """SCULPTRA® Aesthetic is indicated for correction of shallow to deep nasolabial fold contour deficiencies and other facial wrinkles in which deep dermal grid pattern injection technique is appropriate.""",
            
            "contraindications": """SCULPTRA® Aesthetic is contraindicated in:
• Areas of active skin infection or inflammation
• Patients allergic to any ingredient of the product""",
            
            "dosing": """Reconstitution:
• Reconstitute with 5 mL of Sterile Water for Injection, USP
• Allow to stand for minimum of 2 hours (preferably 24-72 hours before use)
• Add 1-2 mL of lidocaine prior to injection

Administration:
• Deep dermal or subcutaneous injection only
• Use 26-gauge needle
• Inject in a grid pattern with 1 cm between injection sites
• Typically 1 vial per cheek per treatment session
• Usually 3 treatment sessions at 3-4 week intervals

Maximum Dose: Do not exceed 2 vials (total 4-8 mL reconstituted product) per treatment session""",
            
            "warnings": """Important Warnings:
• Do not overcorrect – volume increases over time
• Not for injection into the lips
• Not for periorbital area
• Nodule formation may occur
• Product should not be injected intravascularly""",
            
            "adverse_reactions": """Most Common Adverse Reactions:
• Injection site reactions (ecchymosis, hematoma, edema)
• Subcutaneous nodules (early onset, usually resolves)
• Delayed-onset nodules (papules, granulomas)

Nodule Management:
• Massage may help early nodules
• Intralesional corticosteroids for persistent nodules
• 5-FU for granulomas"""
        }
    },
    
    "Radiesse": {
        "manufacturer": "Merz Pharmaceuticals",
        "fda_approval": "2006-12-22",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """RADIESSE® is indicated for:
• Subdermal implantation for correction of moderate to severe facial wrinkles and folds, such as nasolabial folds
• Subdermal implantation for correction of volume deficit in the dorsum of the hands""",
            
            "contraindications": """RADIESSE® is contraindicated in:
• Patients with known hypersensitivity to any of the product components
• Patients with bleeding disorders
• Patients with active skin infection in or near treatment area""",
            
            "dosing": """Facial Wrinkles:
• Inject into the deep dermis or immediate subdermal layer
• Use 27-gauge needle
• Typical volume: 1.0-1.5 mL per treatment
• Overcorrection not recommended

Hand Rejuvenation:
• Inject into the subcutaneous tissue of the dorsum of the hand
• 1.5 mL per hand per treatment session
• Massage immediately after injection

Note: RADIESSE is not reversible with hyaluronidase.""",
            
            "warnings": """Important Warnings:
• Not for lip augmentation
• Not for injection in the periorbital area or glabella
• Risk of vascular occlusion
• Cannot be dissolved with hyaluronidase
• Nodule formation possible

Avoid injection into:
• Blood vessels
• Areas with active inflammation
• Near permanent implants""",
            
            "adverse_reactions": """Most Common Adverse Reactions:
• Bruising
• Erythema
• Swelling
• Pain
• Itching

Serious Adverse Reactions:
• Nodules
• Granulomas
• Vascular occlusion (cannot be reversed with hyaluronidase)"""
        }
    },
    
    "Belotero Balance": {
        "manufacturer": "Merz Pharmaceuticals",
        "fda_approval": "2011-11-14",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """BELOTERO BALANCE® is indicated for injection into the mid-to-deep dermis for correction of moderate to severe facial wrinkles and folds, such as nasolabial folds.""",
            
            "dosing": """Administration:
• Inject into mid-to-deep dermis
• Use 30-gauge needle
• Serial puncture, linear threading, or fanning technique
• Typical treatment volume: Less than 3 mL

Special Consideration:
• Belotero Balance integrates seamlessly into skin tissue
• Can be used in superficial areas where other fillers might show""",
            
            "warnings": """Warnings and Precautions:
• Risk of vascular occlusion
• Do not inject intravascularly
• Use caution in patients on anticoagulant therapy
• Avoid use with permanent implants in same area

Contraindicated in:
• Patients with severe allergies
• Known hypersensitivity to hyaluronic acid
• Active skin infections""",
            
            "adverse_reactions": """Most Common Adverse Reactions:
• Bruising
• Redness
• Swelling
• Pain
• Tenderness
• Itching
• Nodules

Duration: Most reactions resolve within 1-2 weeks"""
        }
    },
    
    # Local Anesthetics (commonly used in aesthetic procedures)
    "Lidocaine": {
        "manufacturer": "Various",
        "fda_approval": "1948-01-01",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """Lidocaine injection is indicated for:
• Local or regional anesthesia
• Infiltration anesthesia
• Peripheral nerve block
• Sympathetic nerve block
• Epidural block""",
            
            "dosing": """Maximum Recommended Doses:
WITHOUT Epinephrine:
• Adults: 4.5 mg/kg up to 300 mg total
• Not to exceed 4.5 mg/kg or 300 mg per procedure

WITH Epinephrine (1:100,000 or 1:200,000):
• Adults: 7 mg/kg up to 500 mg total
• Not to exceed 7 mg/kg or 500 mg per procedure

Pediatric:
• Maximum: 4.5 mg/kg (without epinephrine)
• Maximum: 7 mg/kg (with epinephrine)

Concentration and Volume:
• 0.5% (5 mg/mL): Large volumes for infiltration
• 1% (10 mg/mL): Most common for local infiltration
• 2% (20 mg/mL): Nerve blocks, smaller volumes

Example Calculations:
• 70 kg patient, plain lidocaine: 70 × 4.5 = 315 mg max (use 300 mg)
• 70 kg patient, with epinephrine: 70 × 7 = 490 mg max (use 490 mg)""",
            
            "warnings": """WARNING: LOCAL ANESTHETIC SYSTEMIC TOXICITY (LAST)
Signs and Symptoms:
CNS: Perioral numbness, metallic taste, tinnitus, dizziness, visual disturbances, tremor, convulsions
Cardiovascular: Hypotension, bradycardia, arrhythmias, cardiac arrest

TREATMENT OF LAST:
1. Stop injection immediately
2. Call for help
3. Airway management - 100% oxygen
4. Seizure suppression with benzodiazepines
5. LIPID EMULSION THERAPY:
   • 20% lipid emulsion bolus: 1.5 mL/kg over 1 minute
   • Continuous infusion: 0.25 mL/kg/min for at least 10 minutes
   • Repeat bolus 1-2 times for persistent cardiovascular collapse
   • Maximum dose: 10 mL/kg over first 30 minutes
6. Prolonged CPR may be required""",
            
            "adverse_reactions": """Adverse Reactions:
CNS: Lightheadedness, nervousness, apprehension, euphoria, confusion, dizziness, drowsiness, tinnitus, blurred vision, tremors, convulsions

Cardiovascular: Bradycardia, hypotension, cardiovascular collapse

Allergic: True allergy rare; usually preservative (methylparaben) related"""
        }
    },
    
    # Hyaluronidase
    "Hylenex (Hyaluronidase)": {
        "manufacturer": "Halozyme",
        "fda_approval": "2005-12-02",
        "document_type": "prescribing_information",
        "domain": "aesthetic_medicine",
        "sections": {
            "indications": """HYLENEX® recombinant (hyaluronidase human injection) is indicated for:
• Adjuvant to increase the dispersion and absorption of other injected drugs
• Adjuvant in subcutaneous fluid administration for achieving hydration
• Adjuvant in subcutaneous urography for improving resorption of radiopaque agents

Off-Label Use in Aesthetics:
• Dissolution of hyaluronic acid filler complications
• Emergency treatment of vascular occlusion from HA fillers""",
            
            "dosing": """Standard Dosing for Dispersion:
• 150 units facilitates dispersion of other injected drugs
• Reconstitute if needed; use within 6 hours

For HA Filler Dissolution (Off-Label):
Vascular Occlusion Emergency:
• Initial dose: 200-300 units injected into affected area
• May repeat every 60-90 minutes as needed
• Some protocols suggest up to 500-1500 units for severe occlusion
• Inject directly into the area of compromise
• Massage area after injection
• Apply warm compresses

Correction of Overcorrection/Lumps:
• 10-75 units per site
• Multiple injection points may be needed
• Start with lower doses, can always add more

Note: There is no universally agreed upon dose. Start conservatively and reassess.""",
            
            "warnings": """Warnings and Precautions:
• Hypersensitivity reactions possible
• Avoid injection near sites of infection
• Product may enhance absorption of toxins
• Use caution in areas with friable tissues

Contraindications:
• Known hypersensitivity to hyaluronidase or any ingredient""",
            
            "adverse_reactions": """Adverse Reactions:
• Local injection site reactions (erythema, edema)
• Urticaria
• Allergic reactions (rare)
• Enhanced absorption of co-administered drugs"""
        }
    },
}


def generate_source_id(product_name: str, section: str) -> str:
    """Generate a unique source ID for a PI section."""
    content = f"{product_name}_{section}"
    return f"PI_{hashlib.sha256(content.encode()).hexdigest()[:12]}"


def chunk_section_text(text: str, max_chunk_size: int = 1500) -> List[str]:
    """Split section text into chunks while preserving structure."""
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    paragraphs = text.split('\n\n')
    current_chunk = ""
    
    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_chunk_size:
            current_chunk += para + "\n\n"
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks


def ingest_prescribing_info():
    """Ingest all prescribing information into the database."""
    db = SessionLocal()
    
    try:
        total_docs = 0
        total_chunks = 0
        
        for product_name, info in PRESCRIBING_INFO.items():
            logger.info(f"Ingesting PI for: {product_name}")
            
            # Create document for each section
            for section_name, section_text in info["sections"].items():
                source_id = generate_source_id(product_name, section_name)
                title = f"{product_name} - {section_name.replace('_', ' ').title()}"
                
                # Check if document already exists
                existing = db.execute(text("""
                    SELECT id FROM documents WHERE source_id = :source_id
                """), {"source_id": source_id}).first()
                
                if existing:
                    logger.info(f"  Skipping existing: {title}")
                    continue
                
                # Insert document
                doc_result = db.execute(text("""
                    INSERT INTO documents (
                        source_id, title, year, organization_or_journal,
                        document_type, domain, status, created_at
                    ) VALUES (
                        :source_id, :title, :year, :org,
                        :doc_type, :domain, 'active', NOW()
                    )
                    RETURNING id;
                """), {
                    "source_id": source_id,
                    "title": title,
                    "year": int(info["fda_approval"][:4]),
                    "org": info["manufacturer"],
                    "doc_type": "prescribing_information",
                    "domain": info["domain"],
                })
                row = doc_result.fetchone()
                if row is None:
                    logger.warning(f"  Failed to insert document: {title}")
                    continue
                doc_id = row[0]
                total_docs += 1
                
                # Chunk the section text
                chunks = chunk_section_text(section_text)
                
                for i, chunk_text in enumerate(chunks):
                    # Generate embedding
                    embedding = embed_text(chunk_text)
                    
                    # Insert chunk
                    db.execute(text("""
                        INSERT INTO chunks (
                            document_id, page_or_section, text, embedding,
                            evidence_level, created_at
                        ) VALUES (
                            :doc_id, :section, :text, :embedding,
                            :evidence_level, NOW()
                        );
                    """), {
                        "doc_id": doc_id,
                        "section": f"{section_name}_{i+1}" if len(chunks) > 1 else section_name,
                        "text": chunk_text,
                        "embedding": str(embedding),
                        "evidence_level": "Level I" if section_name in ["dosing", "warnings"] else "Level II",
                    })
                    total_chunks += 1
                
                logger.info(f"  Added: {title} ({len(chunks)} chunks)")
        
        db.commit()
        logger.info(f"\n✅ Ingestion complete: {total_docs} documents, {total_chunks} chunks")
        
        return {"documents": total_docs, "chunks": total_chunks}
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ingestion failed: {e}")
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    logger.info("Starting Prescribing Information ingestion...")
    logger.info(f"Products to ingest: {len(PRESCRIBING_INFO)}")
    
    result = ingest_prescribing_info()
    
    logger.info("\n" + "="*50)
    logger.info("INGESTION SUMMARY")
    logger.info("="*50)
    logger.info(f"Documents created: {result['documents']}")
    logger.info(f"Chunks created: {result['chunks']}")
    logger.info(f"Products covered: {len(PRESCRIBING_INFO)}")
    
    # List products
    logger.info("\nProducts ingested:")
    for product in PRESCRIBING_INFO.keys():
        logger.info(f"  • {product}")


if __name__ == "__main__":
    main()
