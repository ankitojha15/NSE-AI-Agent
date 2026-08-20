from app.schemas.financial_analysis import (
    Completeness,
    FinancialAnalysisContract,
    InsightsBlock,
    MetricComparison,
    MetricSnapshot,
    PeriodInfo,
    PeriodsBlock,
)
from app.services.financial_analysis_service import FinancialAnalysisService
from app.services.financial_insight_service import FinancialInsightService


SNAPSHOT_FIELDS = (
    "sales",
    "revenue",
    "ebitda",
    "operating_profit",
    "net_profit",
    "basic_eps",
    "diluted_eps",
    "opm",
    "net_profit_margin",
)


REQUIRED_METRICS = (
    "sales",
    "ebitda",
    "net_profit",
    "basic_eps",
    "opm",
    "net_profit_margin",
)


class FinancialAnalysisContractService:
    """
    Builds the stable FinancialAnalysisContract for a company.

    Uses FinancialAnalysisService for QoQ / YoY calculations and
    FinancialInsightService for rule-based financial insights.
    Missing or incomplete financial data is handled safely.
    """

    def __init__(self, db):
        self.analysis_service = FinancialAnalysisService(db)
        self.insight_service = FinancialInsightService()

    @staticmethod
    def _to_number(value):
        if value is None or isinstance(value, bool):
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _snapshot(data: dict | None):
        data = data or {}

        return MetricSnapshot(
            **{
                field: FinancialAnalysisContractService._to_number(
                    data.get(field)
                )
                for field in SNAPSHOT_FIELDS
            }
        )

    @staticmethod
    def _comparisons(data: dict | None):
        comparisons = {}

        for metric, item in (data or {}).items():

            comparisons[metric] = MetricComparison(
                metric=metric,
                latest=FinancialAnalysisContractService._to_number(
                    item.get("latest")
                ),
                previous=FinancialAnalysisContractService._to_number(
                    item.get("previous")
                ),
                growth_percent=FinancialAnalysisContractService._to_number(
                    item.get("growth_percent")
                ),
                change=FinancialAnalysisContractService._to_number(
                    item.get("change")
                ),
            )

        return comparisons

    @staticmethod
    def _period_info(period: dict | None):
        if not period:
            return None

        return PeriodInfo(
            from_date=period.get("from"),
            to_date=period.get("to"),
        )

    def build(self, symbol: str) -> FinancialAnalysisContract:
        """
        Build the financial analysis contract for a company.

        Never raises on missing or incomplete data: every section
        degrades gracefully and the completeness block records what
        is unavailable.
        """

        analysis = self.analysis_service.compare_latest_results(symbol)

        latest_snapshot = self._snapshot(analysis.get("latest"))

        previous_snapshot = (
            self._snapshot(analysis.get("previous"))
            if analysis.get("previous")
            else None
        )

        yoy_snapshot = (
            self._snapshot(analysis.get("same_quarter_last_year"))
            if analysis.get("same_quarter_last_year")
            else None
        )

        qoq = self._comparisons(analysis.get("qoq"))
        yoy = self._comparisons(analysis.get("yoy"))

        insights = InsightsBlock(
            **self.insight_service.analyze(analysis)
        )

        periods = PeriodsBlock(
            latest=self._period_info(
                (analysis.get("periods") or {}).get("latest")
            ),
            previous=self._period_info(
                (analysis.get("periods") or {}).get("previous")
            ),
            yoy=self._period_info(
                (analysis.get("periods") or {}).get("yoy")
            ),
        )

        missing_metrics = [
            metric
            for metric in REQUIRED_METRICS
            if getattr(latest_snapshot, metric) is None
        ]

        completeness = Completeness(
            has_latest=bool(analysis.get("latest")),
            has_previous=bool(analysis.get("previous")),
            has_qoq=bool(qoq),
            has_yoy=bool(yoy),
            missing_metrics=missing_metrics,
        )

        return FinancialAnalysisContract(
            symbol=symbol,
            latest=latest_snapshot,
            previous=previous_snapshot,
            same_quarter_last_year=yoy_snapshot,
            qoq=qoq,
            yoy=yoy,
            insights=insights,
            periods=periods,
            completeness=completeness,
            message=analysis.get("message"),
        )