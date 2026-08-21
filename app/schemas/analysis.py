from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    """A single semantic search hit."""

    point_id: str
    score: float
    payload: dict = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Semantic search over stored company analyses."""

    query: str
    limit: int
    results: list[SearchResultItem] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    """Structured AI analysis (score kept internally, not user-facing)."""

    symbol: str
    status: str
    llm_analysis_valid: bool = False
    structured_analysis: dict | None = None
    # Kept for backwards compat but not populated for user-facing use.
    score: int | None = None
    score_explanation: str | None = None
    message: str | None = None
    persisted_id: int | None = None