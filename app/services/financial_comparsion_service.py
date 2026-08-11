from app.repositories.financial_result_repository import (
    FinancialResultRepository
)


class FinancialComparisonService:

    def __init__(self, db):
        self.repository = FinancialResultRepository(db)

    def compare(self, symbol: str):

        results = self.repository.get_company_history(symbol)

        if len(results) < 2:
            return {
                "symbol": symbol,
                "message": "Not enough historical data"
            }

        latest = results[0]
        previous = results[1]

        return {
            "symbol": symbol,

            "latest_seq": latest.seq_number,
            "previous_seq": previous.seq_number,

            "latest_financial_data": latest.financial_data,
            "previous_financial_data": previous.financial_data
        }

    def calculate_qoq(self, latest_data, previous_data):
        """
        Calculate Quarter-over-Quarter percentage changes.
        """

        metrics = [
            "sales",
            "ebitda",
            "operating_profit",
            "net_profit",
            "basic_eps",
            "diluted_eps",
            "opm",
            "net_profit_margin"
        ]

        comparison = {}

        for metric in metrics:

            latest = latest_data.get(metric)
            previous = previous_data.get(metric)

            if latest is None or previous is None:
                comparison[metric] = None
                continue

            if previous == 0:
                comparison[metric] = None
                continue

            change = ((latest - previous) / abs(previous)) * 100

            comparison[metric] = round(change, 2)

        return comparison

