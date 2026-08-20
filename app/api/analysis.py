from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.analysis import (
    AnalysisResponse,
    SearchResponse,
)
from app.services.vector_service import VectorService
from app.workflows.analysis_workflow import AnalysisWorkflow


router = APIRouter(
    prefix="/companies",
    tags=["AI Analysis"],
)


def get_workflow(db: Session = Depends(get_db)) -> AnalysisWorkflow:
    """
    Dependency factory so tests can override it with a mocked workflow.
    """
    return AnalysisWorkflow(db)


def get_vector_service() -> VectorService:
    """
    Dependency factory so tests can override it with a mocked client.
    """
    return VectorService()


@router.get("/{symbol}/analysis", response_model=AnalysisResponse)
def get_analysis(
    symbol: str,
    workflow: AnalysisWorkflow = Depends(get_workflow),
):
    """
    Run the LangGraph analysis workflow and return the structured
    AI analysis plus the company score.
    """

    symbol = (symbol or "").strip().upper()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="symbol is required",
        )

    state = workflow.run(symbol)

    if state.get("status") == "insufficient_data":
        raise HTTPException(
            status_code=404,
            detail=(
                f"Insufficient financial data to analyze {symbol}"
            ),
        )

    return AnalysisResponse(
        symbol=state["symbol"],
        status=state["status"],
        llm_analysis_valid=state.get("llm_analysis_valid", False),
        structured_analysis=state.get("structured_analysis"),
        score=state.get("score"),
        score_explanation=state.get("score_explanation"),
        message=state.get("error"),
        persisted_id=state.get("persisted_id"),
    )


# NOTE: this route must be registered before the company router's
# "/companies/{company_id}" route so "search" is not captured as an
# id. See app/main.py include order.
@router.get("/search", response_model=SearchResponse)
def search_analyses(
    q: str = Query(..., min_length=1, description="Search text"),
    limit: int = Query(5, ge=1, le=50, description="Max results"),
    vector_service: VectorService = Depends(get_vector_service),
):
    """
    Semantic similarity search over stored company analyses.
    """

    query_text = (q or "").strip()

    results = vector_service.search(query_text, limit=limit)

    return SearchResponse(
        query=query_text,
        limit=limit,
        results=results,
    )