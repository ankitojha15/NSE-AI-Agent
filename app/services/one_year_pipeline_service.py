from collections import defaultdict


class OneYearPipelineService:
    """
    Identifies companies that have four distinct quarterly filings.
    """

    def __init__(self, nse_service):
        self.nse_service = nse_service

    def get_eligible_companies(self, max_pages: int = 50):
        """
        Fetch integrated filings and return companies
        having at least four distinct quarters.
        """

        quarterly_data = defaultdict(set)

        for page in range(1, max_pages + 1):
            response = self.nse_service.get_integrated_financial_results(
                page=page,
                size=100
            )

            records = response.get("data", [])

            if not records:
                break

            print(f"PAGE {page} | RECORDS: {len(records)}")

            for record in records:
                symbol = record.get("symbol")
                period = record.get("toDate")

                if not symbol or not period:
                    continue

                quarterly_data[symbol].add(period)

        eligible = {
            symbol: sorted(periods, reverse=True)[:4]
            for symbol, periods in quarterly_data.items()
            if len(periods) >= 4
        }

        return eligible