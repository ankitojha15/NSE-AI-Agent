from app.repositories.financial_result_repository import FinancialResultRepository


class FinancialAnalysisService:
    """
    Compares financial results of a company.
    """

    def __init__(self, db):
        """
        Initialize the analysis service with a database session.
        """
        self.repository = FinancialResultRepository(db)

    def compare_latest_results(self, symbol: str):
        history = self.repository.get_company_history(symbol)

        if len(history) < 2:
            return None

        latest = history[0]
        previous = history[1]

        latest_data = latest.financial_data or {}
        previous_data = previous.financial_data or {}

        def growth(current, previous):
            if previous in (None, 0):
                return None
            return ((current - previous) / abs(previous)) * 100

        comparison = {}

        metrics = [
            "sales",
            "revenue",
            "ebitda",
            "operating_profit",
            "net_profit",
            "basic_eps",
            "diluted_eps",
        ]

        for metric in metrics:
            current = latest_data.get(metric)
            previous_value = previous_data.get(metric)

            if current is not None and previous_value is not None:
                comparison[metric] = {
                    "latest": current,
                    "previous": previous_value,
                    "growth_percent": growth(
                        current,
                        previous_value
                    )
                }

        # OPM is a percentage, so compare the difference directly.
        latest_opm = latest_data.get("opm")
        previous_opm = previous_data.get("opm")

        if latest_opm is not None and previous_opm is not None:
            comparison["opm"] = {
                "latest": latest_opm,
                "previous": previous_opm,
                "change": latest_opm - previous_opm
            }

        return {
            "symbol": symbol,
            "latest_date": latest.filing_date,
            "previous_date": previous.filing_date,
            "comparison": comparison
        }