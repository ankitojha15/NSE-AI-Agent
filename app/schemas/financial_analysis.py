from pydantic import BaseModel, Field


class MetricSnapshot(BaseModel):
    """
    A single quarter's key financial metrics.

    Every field is optional so that missing or incomplete
    financial data is represented safely (None) instead of
    causing validation errors.
    """

    sales: float | None = None
    revenue: float | None = None
    ebitda: float | None = None
    operating_profit: float | None = None
    net_profit: float | None = None
    basic_eps: float | None = None
    diluted_eps: float | None = None
    opm: float | None = None
    net_profit_margin: float | None = None


class MetricComparison(BaseModel):
    """
    A metric compared between two periods.

    - growth_percent is used for absolute metrics (crore / EPS).
    - change is used for margin metrics (percentage points).
    """

    metric: str
    latest: float
    previous: float
    growth_percent: float | None = None
    change: float | None = None


class PeriodInfo(BaseModel):
    """A validated reporting period range."""

    from_date: str | None = None
    to_date: str | None = None


class PeriodsBlock(BaseModel):
    latest: PeriodInfo | None = None
    previous: PeriodInfo | None = None
    yoy: PeriodInfo | None = None


class InsightsBlock(BaseModel):
    """
    Rule-based financial insights.

    Mirrors the output of FinancialInsightService.analyze.
    """

    positive: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)
    growth_analysis: list[str] = Field(default_factory=list)
    margin_analysis: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class Completeness(BaseModel):
    """
    Signals how complete the financial analysis is.

    Used by the downstream AI workflow to decide how much
    confidence to place in the result.
    """

    has_latest: bool = False
    has_previous: bool = False
    has_qoq: bool = False
    has_yoy: bool = False
    missing_metrics: list[str] = Field(default_factory=list)


class FinancialAnalysisContract(BaseModel):
    """
    Stable Pydantic data contract for financial analysis output.

    This is the canonical structured input for the future
    LangGraph / LLM workflow. Build it with
    FinancialAnalysisContractService.build(symbol).
    """

    symbol: str
    latest: MetricSnapshot = Field(default_factory=MetricSnapshot)
    previous: MetricSnapshot | None = None
    same_quarter_last_year: MetricSnapshot | None = None
    qoq: dict[str, MetricComparison] = Field(default_factory=dict)
    yoy: dict[str, MetricComparison] = Field(default_factory=dict)
    insights: InsightsBlock = Field(default_factory=InsightsBlock)
    periods: PeriodsBlock = Field(default_factory=PeriodsBlock)
    completeness: Completeness = Field(default_factory=Completeness)
    message: str | None = None