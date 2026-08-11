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