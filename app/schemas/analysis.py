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
    """Structured AI analysis and company score."""

    symbol: str
    status: str
    llm_analysis_valid: bool = False
    structured_analysis: dict | None = None
    score: int | None = None
    score_explanation: str | None = None
    message: str | None = None
    persisted_id: int | None = None