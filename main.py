import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from openai import OpenAI

from app.core.config import settings
from app.core.safety import safety_screen
from app.rag.retriever import retrieve
from app.rag.citations import to_citations
from app.schemas.ask import AskRequest, AskResponse, Citation


db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://")
engine = create_engine(db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(String(500), nullable=False)
    answer = Column(Text, nullable=True)
    embedding = Column(Vector(1536), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="EvidenceDoc API",
    description="AI-powered evidence search API",
    version="1.0.0",
    lifespan=lifespan
)


client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL
)


def build_context_from_sources(sources: list[dict]) -> str:
    if not sources:
        return ""
    context_parts = []
    for i, src in enumerate(sources, 1):
        context_parts.append(f"[{i}] {src.get('title', '')} ({src.get('year', 'n.d.')}): {src.get('text', '')}")
    return "\n\n".join(context_parts)


def build_system_prompt(request: AskRequest) -> str:
    mode_instruction = ""
    if request.mode == "clinic":
        mode_instruction = "Provide a concise, clinically actionable answer."
    else:
        mode_instruction = "Provide a comprehensive deep-dive analysis with detailed explanations."
    
    return f"""You are an expert medical research assistant providing evidence-based answers.
Domain: {request.domain}
{mode_instruction}
Include citation markers like [1], [2], [3] throughout your response.
Always cite authoritative sources like clinical guidelines, systematic reviews, and consensus statements."""


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    safety = safety_screen(request.question)
    if not safety.allowed:
        return AskResponse(
            answer="",
            citations=[],
            refusal=True,
            refusal_reason=safety.refusal_reason
        )

    system_prompt = build_system_prompt(request)
    
    if safety.escalation_note:
        system_prompt += f"\n\nIMPORTANT SAFETY NOTE: {safety.escalation_note}"

    sources = retrieve(request.question, request.domain)
    citations = to_citations(sources)
    
    if len(citations) < settings.MIN_CITATIONS_REQUIRED:
        return AskResponse(
            answer="",
            citations=[],
            refusal=True,
            refusal_reason="Unable to find sufficient evidence-based sources for this query."
        )

    context = build_context_from_sources(sources)
    user_message = f"Context from sources:\n{context}\n\nQuestion: {request.question}" if context else request.question

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=settings.MAX_CONTEXT_CHARS
        )

        answer = response.choices[0].message.content or ""
        
        db = SessionLocal()
        try:
            search_record = SearchHistory(query=request.question, answer=answer)
            db.add(search_record)
            db.commit()
        finally:
            db.close()

        return AskResponse(
            answer=answer,
            citations=citations
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec B104
