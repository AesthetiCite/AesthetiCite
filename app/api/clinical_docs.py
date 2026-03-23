"""
Clinical Document Generators API
- Prior Authorization Letters
- Patient Instruction Sheets
- ICD-10 Coding Suggestions
- Discharge Summaries
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os
from openai import OpenAI

router = APIRouter(prefix="/clinical-docs", tags=["clinical-docs"])

client = OpenAI(
    api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", ""),
    base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")
)


class PriorAuthRequest(BaseModel):
    patient_name: str
    patient_dob: str
    insurance_company: str
    insurance_id: str
    diagnosis: str
    procedure: str
    clinical_justification: str
    physician_name: str
    physician_npi: Optional[str] = None
    urgency: Optional[str] = "routine"


class PriorAuthResponse(BaseModel):
    letter: str
    icd10_codes: List[str]
    cpt_codes: List[str]


class PatientInstructionRequest(BaseModel):
    procedure: str
    diagnosis: Optional[str] = None
    language: Optional[str] = "en"
    reading_level: Optional[str] = "6th grade"
    include_warnings: Optional[bool] = True
    include_follow_up: Optional[bool] = True


class PatientInstructionResponse(BaseModel):
    title: str
    instructions: str
    warnings: Optional[str] = None
    follow_up: Optional[str] = None
    emergency_signs: Optional[str] = None


class ICD10Request(BaseModel):
    clinical_notes: str
    specialty: Optional[str] = "general"


class ICD10Code(BaseModel):
    code: str
    description: str
    confidence: str


class ICD10Response(BaseModel):
    primary_diagnosis: ICD10Code
    secondary_diagnoses: List[ICD10Code]
    rule_out_diagnoses: List[ICD10Code]


class DischargeSummaryRequest(BaseModel):
    patient_name: str
    admission_date: str
    discharge_date: str
    admitting_diagnosis: str
    procedures_performed: List[str]
    hospital_course: str
    discharge_diagnosis: str
    medications: List[str]
    follow_up_instructions: str
    physician_name: str


class DischargeSummaryResponse(BaseModel):
    summary: str
    icd10_codes: List[str]
    cpt_codes: List[str]


@router.post("/prior-auth", response_model=PriorAuthResponse)
async def generate_prior_auth(request: PriorAuthRequest):
    """Generate a prior authorization letter for insurance approval."""
    
    prompt = f"""Generate a professional prior authorization letter for insurance approval.

Patient Information:
- Name: {request.patient_name}
- DOB: {request.patient_dob}
- Insurance: {request.insurance_company}
- Insurance ID: {request.insurance_id}

Clinical Details:
- Diagnosis: {request.diagnosis}
- Requested Procedure: {request.procedure}
- Clinical Justification: {request.clinical_justification}
- Urgency: {request.urgency}

Physician:
- Name: {request.physician_name}
- NPI: {request.physician_npi or "N/A"}

Please generate:
1. A formal prior authorization letter with medical necessity justification
2. Relevant ICD-10 diagnosis codes
3. Relevant CPT procedure codes

Format the response as JSON with these fields:
- letter: The full prior authorization letter text
- icd10_codes: Array of relevant ICD-10 codes
- cpt_codes: Array of relevant CPT codes"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a medical documentation specialist. Generate professional, accurate clinical documents with appropriate medical coding."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=2000
        )
        
        import json
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
        
        return PriorAuthResponse(
            letter=result.get("letter", ""),
            icd10_codes=result.get("icd10_codes", []),
            cpt_codes=result.get("cpt_codes", [])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate prior auth: {str(e)}")


@router.post("/patient-instructions", response_model=PatientInstructionResponse)
async def generate_patient_instructions(request: PatientInstructionRequest):
    """Generate patient-friendly instruction sheets."""
    
    language_instruction = ""
    if request.language != "en":
        language_map = {
            "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
            "it": "Italian", "ar": "Arabic", "zh": "Chinese", "ja": "Japanese",
            "ko": "Korean", "ru": "Russian", "hi": "Hindi", "tr": "Turkish"
        }
        lang_name = language_map.get(request.language or "en", request.language or "en")
        language_instruction = f"Write the instructions in {lang_name}."
    
    prompt = f"""Generate patient instruction sheet for: {request.procedure}
{f"Diagnosis: {request.diagnosis}" if request.diagnosis else ""}

Requirements:
- Reading level: {request.reading_level}
- Include warnings: {request.include_warnings}
- Include follow-up: {request.include_follow_up}
{language_instruction}

Generate a clear, patient-friendly instruction sheet. Format as JSON with:
- title: Title of the instruction sheet
- instructions: Step-by-step care instructions
- warnings: Warning signs to watch for (if applicable)
- follow_up: Follow-up care instructions (if applicable)
- emergency_signs: When to seek emergency care"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a patient education specialist. Create clear, easy-to-understand medical instructions that patients can follow at home."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=1500
        )
        
        import json
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
        
        def to_str(val):
            if val is None:
                return None
            if isinstance(val, list):
                return "\n".join(str(v) for v in val)
            return str(val)
        
        return PatientInstructionResponse(
            title=to_str(result.get("title", "")),
            instructions=to_str(result.get("instructions", "")),
            warnings=to_str(result.get("warnings")),
            follow_up=to_str(result.get("follow_up")),
            emergency_signs=to_str(result.get("emergency_signs"))
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate instructions: {str(e)}")


@router.post("/icd10-codes", response_model=ICD10Response)
async def suggest_icd10_codes(request: ICD10Request):
    """Suggest ICD-10 codes from clinical notes."""
    
    prompt = f"""Analyze these clinical notes and suggest appropriate ICD-10 diagnosis codes.

Clinical Notes:
{request.clinical_notes}

Specialty Context: {request.specialty}

Provide ICD-10 codes in JSON format:
- primary_diagnosis: Object with code, description, confidence (high/medium/low)
- secondary_diagnoses: Array of objects with code, description, confidence
- rule_out_diagnoses: Array of objects with code, description, confidence

Be specific and accurate with ICD-10-CM codes."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a certified medical coder (CPC, CCS) specializing in ICD-10-CM coding. Provide accurate, specific diagnosis codes based on clinical documentation."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=1000
        )
        
        import json
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
        
        primary = result.get("primary_diagnosis", {})
        secondary = result.get("secondary_diagnoses", [])
        rule_out = result.get("rule_out_diagnoses", [])
        
        return ICD10Response(
            primary_diagnosis=ICD10Code(
                code=primary.get("code", ""),
                description=primary.get("description", ""),
                confidence=primary.get("confidence", "medium")
            ),
            secondary_diagnoses=[
                ICD10Code(code=d.get("code", ""), description=d.get("description", ""), confidence=d.get("confidence", "medium"))
                for d in secondary
            ],
            rule_out_diagnoses=[
                ICD10Code(code=d.get("code", ""), description=d.get("description", ""), confidence=d.get("confidence", "medium"))
                for d in rule_out
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to suggest codes: {str(e)}")


@router.post("/discharge-summary", response_model=DischargeSummaryResponse)
async def generate_discharge_summary(request: DischargeSummaryRequest):
    """Generate a comprehensive discharge summary."""
    
    procedures_text = "\n".join(f"- {p}" for p in request.procedures_performed)
    medications_text = "\n".join(f"- {m}" for m in request.medications)
    
    prompt = f"""Generate a professional hospital discharge summary.

Patient: {request.patient_name}
Admission Date: {request.admission_date}
Discharge Date: {request.discharge_date}

Admitting Diagnosis: {request.admitting_diagnosis}
Discharge Diagnosis: {request.discharge_diagnosis}

Procedures Performed:
{procedures_text}

Hospital Course:
{request.hospital_course}

Discharge Medications:
{medications_text}

Follow-up Instructions:
{request.follow_up_instructions}

Attending Physician: {request.physician_name}

Generate a complete discharge summary in JSON format:
- summary: The full discharge summary document
- icd10_codes: Array of relevant ICD-10 codes for the admission
- cpt_codes: Array of CPT codes for procedures performed"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a hospital medical records specialist. Generate accurate, comprehensive discharge summaries that meet documentation standards."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=2500
        )
        
        import json
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
        
        return DischargeSummaryResponse(
            summary=result.get("summary", ""),
            icd10_codes=result.get("icd10_codes", []),
            cpt_codes=result.get("cpt_codes", [])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")
