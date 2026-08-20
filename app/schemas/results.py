from pydantic import BaseModel, ConfigDict, Field


class FinancialResultItem(BaseModel):
    """A single financial result filing."""

    model_config = ConfigDict(from_attributes=True)

    seq_number: str
    symbol: str | None = None
    company_name: str | None = None
    filing_date: str | None = None
    period: str | None = None
    audited: str | None = None
    consolidated: str | None = None
    xbrl_url: str | None = None
    financial_data: dict | None = None


class MetricComparisonResult(BaseModel):
    """One metric compared between two periods."""

    latest: float
    previous: float
    growth_percent: float | None = None
    change: float | None = None


class PeriodResult(BaseModel):
    from_date: str | None = None
    to_date: str | None = None


class ComparisonPeriods(BaseModel):
    latest: PeriodResult | None = None
    previous: PeriodResult | None = None
    yoy: PeriodResult | None = None


class ComparisonResponse(BaseModel):
    """QoQ / YoY comparison for the latest quarter."""

    symbol: str
    latest_seq: str | None = None
    latest_date: str | None = None
    previous_seq: str | None = None
    previous_date: str | None = None
    yoy_seq: str | None = None

    qoq: dict[str, MetricComparisonResult] = Field(default_factory=dict)
    yoy: dict[str, MetricComparisonResult] = Field(default_factory=dict)

    latest: dict = Field(default_factory=dict)
    previous: dict = Field(default_factory=dict)
    same_quarter_last_year: dict = Field(default_factory=dict)

    periods: ComparisonPeriods = Field(default_factory=ComparisonPeriods)


class InsightsResponse(BaseModel):
    """Rule-based financial insights."""

    positive: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)
    margin_analysis: list[str] = Field(default_factory=list)
    growth_analysis: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)