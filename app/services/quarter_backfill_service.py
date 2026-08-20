from app.repositories.financial_result_repository import (
    FinancialResultRepository
)
from app.utils.quarter_utils import (
    get_quarter_from_qe_date,
    is_valid_period,
)


class QuarterBackfillService:
    """
    Backfills missing quarterly financial-result records
    for a company using NSE integrated filings.
    """

    def __init__(self, db, nse_service):
        self.repository = FinancialResultRepository(db)
        self.nse_service = nse_service

    def _usable_quarters(self, symbol: str):
        """
        Return the distinct usable quarters for a company from the DB.

        A quarter is usable only when its from/to period dates are
        present and valid. Duplicate quarters are counted once.
        """

        quarters = set()

        for result in self.repository.get_company_quarters(symbol):

            raw = result.raw_data or {}

            from_date = raw.get("fromDate")
            to_date = raw.get("toDate")

            if is_valid_period(from_date, to_date):
                quarters.add((from_date, to_date))

        return quarters

    def backfill_company(self, symbol: str, max_pages: int = 50):
        """
        Fetch NSE integrated filings and store missing quarters
        for the requested company.

        NSE provides only the period-end date (qe_Date); the quarter
        range is derived from it. Stops after four unique usable
        quarters are available.
        """

        existing_quarters = self._usable_quarters(symbol)

        print(
            f"EXISTING QUARTERS: "
            f"{len(existing_quarters)}"
        )

        if len(existing_quarters) >= 4:
            print("Already have 4 quarters.")
            return self.repository.get_company_quarters(symbol)

        for page in range(1, max_pages + 1):

            response = self.nse_service.get_integrated_financial_results(
                page=page,
                size=100
            )

            records = response.get("data", [])

            if not records:
                break

            print(
                f"PAGE {page} | RECORDS: {len(records)}"
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

                print(
                    f"NEW QUARTER: "
                    f"{quarter[0]} → {quarter[1]}"
                )

                self.repository.create(record)

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