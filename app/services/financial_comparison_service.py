from datetime import datetime

from app.repositories.financial_result_repository import (
    FinancialResultRepository
)


class FinancialComparisonService:
    """
    Service responsible for calculating QoQ and YoY
    financial comparisons.
    """

    def __init__(self, db):
        self.repository = FinancialResultRepository(db)

    def compare(self, symbol: str):
        """
        Compare the latest quarter with:
        - Previous quarter (QoQ)
        - Same quarter previous year (YoY)
        """

        results = self.repository.get_company_history(symbol)

        if not results:
            return {
                "symbol": symbol,
                "message": "No historical data available"
            }

        # --------------------------------------------------
        # Extract quarter dates from raw NSE data
        # --------------------------------------------------

        valid_results = []

        for result in results:

            raw_data = result.raw_data or {}

            from_date = raw_data.get("fromDate")
            to_date = raw_data.get("toDate")

            if not from_date or not to_date:
                continue

            try:
                parsed_from_date = datetime.strptime(
                    from_date,
                    "%d-%b-%Y"
                )

            except ValueError:
                continue

            valid_results.append(
                {
                    "result": result,
                    "from_date": parsed_from_date,
                    "to_date": to_date
                }
            )

        if not valid_results:
            return {
                "symbol": symbol,
                "message": "No valid quarterly data available"
            }

        # --------------------------------------------------
        # Remove duplicate filings for the same quarter
        # --------------------------------------------------

        unique_quarters = {}

        for item in valid_results:

            quarter_key = (
                item["from_date"],
                item["to_date"]
            )

            # Keep only one filing for each quarter
            if quarter_key not in unique_quarters:
                unique_quarters[quarter_key] = item

        # --------------------------------------------------
        # Sort latest quarter first
        # --------------------------------------------------

        quarters = sorted(
            unique_quarters.values(),
            key=lambda x: x["from_date"],
            reverse=True
        )

        # --------------------------------------------------
        # Latest quarter
        # --------------------------------------------------

        latest = quarters[0]["result"]

        # --------------------------------------------------
        # Previous quarter
        # --------------------------------------------------

        previous = None

        if len(quarters) >= 2:
            previous = quarters[1]["result"]

        # --------------------------------------------------
        # Same quarter previous year
        #
        # Four quarters back
        # --------------------------------------------------

        yoy = None

        if len(quarters) >= 5:
            yoy = quarters[4]["result"]

        # --------------------------------------------------
        # Percentage change
        # --------------------------------------------------

        def percentage_change(current, previous_value):

            if previous_value in (None, 0):
                return None

            return round(
                (
                    (current - previous_value)
                    / abs(previous_value)
                ) * 100,
                2
            )

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

        # --------------------------------------------------
        # QoQ
        # --------------------------------------------------

        qoq = {}

        if previous:

            latest_data = latest.financial_data or {}
            previous_data = previous.financial_data or {}

            for metric in metrics:

                current = latest_data.get(metric)
                previous_value = previous_data.get(metric)

                if current is not None and previous_value is not None:
                    qoq[metric] = percentage_change(
                        current,
                        previous_value
                    )

        # --------------------------------------------------
        # YoY
        # --------------------------------------------------

        yoy_comparison = {}

        if yoy:

            latest_data = latest.financial_data or {}
            yoy_data = yoy.financial_data or {}

            for metric in metrics:

                current = latest_data.get(metric)
                previous_year = yoy_data.get(metric)

                if current is not None and previous_year is not None:
                    yoy_comparison[metric] = percentage_change(
                        current,
                        previous_year
                    )

        # --------------------------------------------------
        # Final response
        # --------------------------------------------------

        return {
            "symbol": symbol,

            "latest_seq": latest.seq_number,

            "latest_financial_data": latest.financial_data,

            "qoq": {
                "previous_seq": (
                    previous.seq_number
                    if previous
                    else None
                ),
                "comparison": qoq
            },

            "yoy": {
                "previous_year_seq": (
                    yoy.seq_number
                    if yoy
                    else None
                ),
                "comparison": yoy_comparison
            }
        }