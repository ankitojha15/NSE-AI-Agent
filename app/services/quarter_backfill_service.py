from app.repositories.financial_result_repository import (
    FinancialResultRepository
)
from app.utils.quarter_utils import (
    derive_period,
    get_quarter_from_qe_date,
)


class QuarterBackfillService:
    """
    Backfills missing quarterly financial-result records
    for a company using NSE integrated filings.
    """

    def __init__(self, db, nse_service, filing_records=None):
        self.repository = FinancialResultRepository(db)
        self.nse_service = nse_service
        self.filing_records = filing_records
        self._feed_cache = None

    def _usable_quarters(self, symbol: str):
        """
        Return the distinct usable quarters for a company from the DB.

        A quarter is usable when its period can be derived (fromDate /
        toDate, qe_Date or period). Duplicate quarters are counted once.
        """

        quarters = set()

        for result in self.repository.get_company_quarters(symbol):

            period = derive_period(result.raw_data or {})

            if period is not None:
                quarters.add(period)

        return quarters

    def _get_feed_records(self, max_pages: int):
        """
        Return the integrated-filings feed to scan for backfill.

        When filing_records were provided (e.g. the pipeline feed
        fetched once per run), they are reused and no NSE request is
        made. Otherwise the feed is fetched from NSE once and cached
        on this instance so repeated companies never re-download the
        same pages.
        """

        if self.filing_records is not None:
            return self.filing_records

        if self._feed_cache is None:

            records = []

            for page in range(1, max_pages + 1):

                response = self.nse_service.get_integrated_financial_results(
                    page=page,
                    size=100
                )

                page_records = response.get("data", [])

                if not page_records:
                    break

                records.extend(page_records)

            self._feed_cache = records

        return self._feed_cache

    def backfill_company(self, symbol: str, max_pages: int = 50):
        """
        Backfill missing quarters for a company using the available
        integrated-filings feed.

        When a prepared feed was supplied (pipeline reuse), the feed is
        scanned once in memory and no NSE pages are re-fetched for this
        company. Stops after four unique usable quarters are available.
        """

        existing_quarters = self._usable_quarters(symbol)

        print(
            f"EXISTING QUARTERS: "
            f"{len(existing_quarters)}"
        )

        if len(existing_quarters) >= 4:
            print("Already have 4 quarters.")
            return self.repository.get_company_quarters(symbol)

        records = self._get_feed_records(max_pages)

        available_matches = sum(
            1
            for record in records
            if (
                (record.get("symbol") or record.get("sym")) == symbol
                and get_quarter_from_qe_date(record.get("qe_Date")) is not None
            )
        )

        print(
            f"AVAILABLE MATCHING FILINGS: "
            f"{available_matches}"
        )

        for record in records:

            record_symbol = (
                record.get("symbol")
                or record.get("sym")
            )

            if record_symbol != symbol:
                continue

            quarter = get_quarter_from_qe_date(
                record.get("qe_Date")
            )

            if quarter is None:
                continue

            if quarter in existing_quarters:
                continue

            seq_id = record.get("seq_Id") or record.get("seqNumber")

            before = (
                self.repository.get_by_seq_number(seq_id)
                if seq_id else None
            )

            created = self.repository.create(record)

            # A row is genuinely new only when create() actually
            # persisted a different record than the one already stored
            # for this sequence number.
            persisted = (
                created is not None
                and (before is None or created.id != before.id)
            )

            if not persisted:
                print(
                    f"SKIPPED (not persisted): "
                    f"{symbol} | {quarter[0]} → {quarter[1]}"
                )
                continue

            print(
                f"NEW QUARTER: "
                f"{quarter[0]} → {quarter[1]}"
            )

            existing_quarters.add(quarter)

            if len(existing_quarters) >= 4:
                print(
                    "\nBACKFILL COMPLETE"
                )

                return self.repository.get_company_quarters(
                    symbol
                )

        print(
            "\nBACKFILL FINISHED"
        )

        return self.repository.get_company_quarters(
            symbol
        )

    def ensure_minimum_quarters(
        self,
        symbol: str,
        min_quarters: int = 4,
        max_pages: int = 50
    ):
        """
        Ensure a company has at least min_quarters usable quarters.

        1. Counts the company's distinct usable quarters.
        2. Triggers backfill when fewer than the required number.
        3. Re-checks the available quarters after backfill.

        Returns
        -------
        dict
            {
                "symbol": symbol,
                "quarter_count": int,
                "required": min_quarters,
                "eligible": bool,
                "backfilled": int,
                "quarters": [{"fromDate": ..., "toDate": ...}, ...]
            }
        """

        before = self._usable_quarters(symbol)

        backfilled = 0

        if len(before) < min_quarters:

            self.backfill_company(symbol, max_pages=max_pages)

            backfilled = (
                len(self._usable_quarters(symbol))
                - len(before)
            )

        quarters = self._usable_quarters(symbol)

        print(
            f"QUARTERS AFTER BACKFILL: "
            f"{len(quarters)}"
        )

        print(
            "STATUS: "
            f"{'ready_for_analysis' if len(quarters) >= min_quarters else 'insufficient_quarters'}"
        )

        return {
            "symbol": symbol,
            "quarter_count": len(quarters),
            "required": min_quarters,
            "eligible": len(quarters) >= min_quarters,
            "backfilled": backfilled,
            "quarters": [
                {"fromDate": quarter[0], "toDate": quarter[1]}
                for quarter in sorted(quarters)
            ],
        }