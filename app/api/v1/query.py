"""REST Q&A endpoint: one question in, one grounded answer out (no streaming)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.v1.auth import User, get_current_user
from app.core.ratelimit import ask_limiter, enforce_rate_limit
from app.rag.pipeline import get_rag_pipeline

router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=8000)


@router.post("/ask")
def ask_ai(request: QueryRequest, user: User = Depends(get_current_user)):
    enforce_rate_limit(ask_limiter, user.id, "Too many questions — please slow down")
    return get_rag_pipeline().run(request.question)
