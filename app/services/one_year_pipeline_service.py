from collections import defaultdict

from app.services.quarter_backfill_service import QuarterBackfillService
from app.utils.quarter_utils import get_quarter_from_qe_date


class OneYearPipelineService:
    """
    Identifies companies that have four distinct quarterly filings.
    """

    def __init__(self, nse_service, db=None, filing_records=None):
        self.nse_service = nse_service
        self.db = db
        self.filing_records = filing_records

    def get_eligible_companies(self, max_pages: int = 50):
        """
        Fetch integrated filings and return companies having at least
        four distinct usable quarters.

        NSE provides only the period-end date (qe_Date); the quarter
        range is derived from it. A quarter is usable only when the
        period-end date is valid, and duplicate quarters for the same
        company are counted once.
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

                quarter = get_quarter_from_qe_date(
                    record.get("qe_Date")
                )

                if not symbol or quarter is None:
                    continue

                quarterly_data[symbol].add(quarter)

        eligible = {
            symbol: sorted(periods, reverse=True)[:4]
            for symbol, periods in quarterly_data.items()
            if len(periods) >= 4
        }

        return eligible

    def ensure_company_quarters(
        self,
        symbol: str,
        min_quarters: int = 4,
        max_pages: int = 50,
        filing_records: list | None = None
    ):
        """
        Ensure a company has at least min_quarters usable quarters.

        When the company has fewer than the required number of usable
        quarters in the database, QuarterBackfillService is triggered
        automatically. The available quarters are re-checked afterwards.

        filing_records, when provided, is the already-discovered
        integrated-filings feed (fetched once per pipeline run) so no
        NSE pages are re-downloaded for this company.

        Requires a database session (passed via the constructor).

        Returns
        -------
        dict
            Summary: symbol, quarter_count, required, eligible,
            backfilled, quarters.
        """

        if self.db is None:
            raise ValueError("A database session is required")

        records = (
            filing_records
            if filing_records is not None
            else self.filing_records
        )

        backfill_service = QuarterBackfillService(
            self.db,
            self.nse_service,
            filing_records=records,
        )

        return backfill_service.ensure_minimum_quarters(
            symbol,
            min_quarters=min_quarters,
            max_pages=max_pages
        )