from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.rag.pipeline import get_rag_pipeline

router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=8000)


@router.post(
    "/ask",
    dependencies=[Depends(get_current_user)],
)
def ask_ai(request: QueryRequest):
    return get_rag_pipeline().run(request.question)
