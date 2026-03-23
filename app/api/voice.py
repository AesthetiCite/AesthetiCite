"""
Voice Transcription API
Speech-to-text for clinical notes using OpenAI Whisper
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from typing import Optional
import os
import tempfile
from openai import OpenAI

router = APIRouter(prefix="/voice", tags=["voice"])

client = OpenAI(
    api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", ""),
    base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")
)


class TranscriptionResponse(BaseModel):
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None


class ClinicalNoteResponse(BaseModel):
    transcript: str
    structured_note: str
    chief_complaint: Optional[str] = None
    history: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None
    icd10_suggestions: list[str] = []


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None)
):
    """Transcribe audio file to text using OpenAI Whisper."""
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    allowed_types = ["audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/ogg", "audio/m4a"]
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {file.content_type}")
    
    try:
        content = await file.read()
        
        suffix = ".webm"
        if file.filename:
            if file.filename.endswith(".mp3"):
                suffix = ".mp3"
            elif file.filename.endswith(".wav"):
                suffix = ".wav"
            elif file.filename.endswith(".m4a"):
                suffix = ".m4a"
            elif file.filename.endswith(".ogg"):
                suffix = ".ogg"
            elif file.filename.endswith(".mp4"):
                suffix = ".mp4"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            with open(tmp_path, "rb") as audio_file:
                params = {
                    "model": "gpt-4o-mini-transcribe",
                    "file": audio_file,
                    "response_format": "json"
                }
                if language:
                    params["language"] = language
                
                transcript = client.audio.transcriptions.create(**params)
            
            return TranscriptionResponse(
                text=transcript.text,
                language=language
            )
        finally:
            os.unlink(tmp_path)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.post("/clinical-note", response_model=ClinicalNoteResponse)
async def transcribe_clinical_note(
    file: UploadFile = File(...),
    specialty: Optional[str] = Form("general")
):
    """Transcribe audio and structure into a clinical note format."""
    
    transcript_response = await transcribe_audio(file)
    transcript = transcript_response.text
    
    prompt = f"""Convert this clinical encounter transcript into a structured clinical note.

Transcript:
{transcript}

Specialty context: {specialty}

Generate a structured clinical note in JSON format with these fields:
- structured_note: The full formatted clinical note (SOAP format preferred)
- chief_complaint: Main reason for visit
- history: Relevant history from the encounter
- assessment: Clinical assessment/diagnosis
- plan: Treatment plan
- icd10_suggestions: Array of suggested ICD-10 codes based on the encounter

Preserve all clinically relevant information from the transcript."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a medical scribe AI. Convert clinical encounter transcripts into accurate, well-structured clinical documentation."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=2000
        )
        
        import json
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
        
        return ClinicalNoteResponse(
            transcript=transcript,
            structured_note=result.get("structured_note", ""),
            chief_complaint=result.get("chief_complaint"),
            history=result.get("history"),
            assessment=result.get("assessment"),
            plan=result.get("plan"),
            icd10_suggestions=result.get("icd10_suggestions", [])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to structure note: {str(e)}")
