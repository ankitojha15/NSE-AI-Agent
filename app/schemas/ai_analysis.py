from pydantic import BaseModel, Field


class LLMAnalysisResult(BaseModel):
    """
    Structured output contract for the LLM financial analysis.

    The LLM is required to produce exactly these fields. Pydantic
    validation rejects any response that deviates from this schema
    (missing fields, wrong types, or an out-of-range company score).
    """

    summary: str
    positive_factors: list[str] = Field(default_factory=list)
    negative_factors: list[str] = Field(default_factory=list)
    growth_analysis: list[str] = Field(default_factory=list)
    margin_analysis: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    company_score: int = Field(..., ge=0, le=100)
    score_explanation: str