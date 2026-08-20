from app.repositories.financial_result_repository import (
    FinancialResultRepository
)


class QuarterBackfillService:
    """
    Backfills missing quarterly financial-result records
    for a company using NSE integrated filings.
    """

    def __init__(self, db, nse_service):
        self.repository = FinancialResultRepository(db)
        self.nse_service = nse_service

    def backfill_company(self, symbol: str, max_pages: int = 50):
        """
        Fetch NSE integrated filings and store missing quarters
        for the requested company.

        Stops after four unique quarters are available.
        """

        existing = self.repository.get_company_quarters(symbol)

        existing_quarters = set()

        for result in existing:
            raw = result.raw_data or {}

            from_date = raw.get("fromDate")
            to_date = raw.get("toDate")

            if from_date and to_date:
                existing_quarters.add(
                    (from_date, to_date)
                )

        print(
            f"EXISTING QUARTERS: "
            f"{len(existing_quarters)}"
        )

        if len(existing_quarters) >= 4:
            print("Already have 4 quarters.")
            return existing

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

                from_date = record.get("fromDate")
                to_date = record.get("toDate")

                if not from_date or not to_date:
                    continue

                quarter_key = (
                    from_date,
                    to_date
                )

                if quarter_key in existing_quarters:
                    continue

                print(
                    f"NEW QUARTER: "
                    f"{from_date} → {to_date}"
                )

                self.repository.create(record)

                existing_quarters.add(
                    quarter_key
                )

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