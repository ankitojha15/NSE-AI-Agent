import calendar
from datetime import datetime

from app.repositories.financial_result_repository import (
    FinancialResultRepository
)


print("### FINANCIAL_ANALYSIS_SERVICE LOADED ###")


DATE_FORMATS = (
    "%d-%b-%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
)


GROWTH_METRICS = (
    "sales",
    "revenue",
    "ebitda",
    "operating_profit",
    "net_profit",
    "basic_eps",
    "diluted_eps",
)


MARGIN_METRICS = (
    "opm",
    "net_profit_margin",
)


class FinancialAnalysisService:
    """
    Canonical service for QoQ and YoY financial comparison.

    Comparison rules:
    - QoQ compares the latest quarter with its immediately preceding
      consecutive quarter. A gap in reporting periods is never treated
      as a QoQ comparison.
    - YoY compares the latest quarter with the same quarter of the
      previous year.
    - Only valid, numeric values are compared. Missing, zero, invalid
      or non-numeric values are handled safely.
    - Mismatched or unrelated reporting periods are never compared.

    This is the single source of truth for comparison logic (the
    previous FinancialComparisonService has been consolidated here).
    """

    def __init__(self, db):
        self.repository = FinancialResultRepository(db)

    # ----------------------------------------------------------
    # Date / value helpers
    # ----------------------------------------------------------

    @staticmethod
    def _parse_date(value):
        """
        Parse an NSE quarter date into a datetime.

        Returns None when the value is missing or unparseable.
        """

        if not value:
            return None

        if isinstance(value, datetime):
            return value

        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(str(value), fmt)
            except ValueError:
                continue

        return None

    @staticmethod
    def _add_months(date_value, months):
        """
        Shift a date by a number of months, clamping to the last day
        of the target month when necessary.
        """

        month_index = date_value.month - 1 + months
        year = date_value.year + (month_index // 12)
        month = (month_index % 12) + 1

        day = min(
            date_value.day,
            calendar.monthrange(year, month)[1]
        )

        return date_value.replace(
            year=year,
            month=month,
            day=day
        )

    @staticmethod
    def _to_number(value):
        """
        Coerce a value to a float.

        Returns None for missing, boolean or non-numeric values.
        """

        if value is None or isinstance(value, bool):
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    # ----------------------------------------------------------
    # Quarter collection
    # ----------------------------------------------------------

    def _collect_quarters(self, symbol):
        """
        Return validated, deduplicated quarters for a company,
        latest reporting period first.

        Each item is:
            {
                "result": FinancialResult,
                "from_date": datetime,
                "to_date": datetime,
            }

        Rules:
        - Invalid or unusable reporting periods are excluded.
        - Duplicate filings for the same quarter are counted once
          (the most recent filing wins).
        """

        history = self.repository.get_company_history(symbol)

        items = []

        for result in history:

            raw_data = result.raw_data or {}

            from_date = self._parse_date(raw_data.get("fromDate"))
            to_date = self._parse_date(raw_data.get("toDate"))

            if from_date is None or to_date is None:
                continue

            if to_date < from_date:
                continue

            items.append(
                {
                    "result": result,
                    "from_date": from_date,
                    "to_date": to_date,
                }
            )

        unique_quarters = {}

        for item in items:

            quarter_key = (item["from_date"], item["to_date"])

            if quarter_key not in unique_quarters:
                unique_quarters[quarter_key] = item

        return sorted(
            unique_quarters.values(),
            key=lambda item: item["from_date"],
            reverse=True
        )

    # ----------------------------------------------------------
    # Metric comparison
    # ----------------------------------------------------------

    def _compare_metrics(self, current_data, previous_data):
        """
        Compare two quarters metric by metric.

        Growth metrics (crore / EPS) report a percentage growth.
        Margin metrics (percentages) report a change in percentage
        points.

        A metric is included only when both values are present and
        numeric. Zero or invalid previous values never cause errors;
        growth is reported as None in those cases.
        """

        current_data = current_data or {}
        previous_data = previous_data or {}

        comparison = {}

        for metric in GROWTH_METRICS:

            current = self._to_number(current_data.get(metric))
            previous = self._to_number(previous_data.get(metric))

            if current is None or previous is None:
                continue

            growth_percent = None

            if previous != 0:
                growth_percent = round(
                    ((current - previous) / abs(previous)) * 100,
                    2
                )

            comparison[metric] = {
                "latest": current,
                "previous": previous,
                "growth_percent": growth_percent,
            }

        for metric in MARGIN_METRICS:

            current = self._to_number(current_data.get(metric))
            previous = self._to_number(previous_data.get(metric))

            if current is None or previous is None:
                continue

            comparison[metric] = {
                "latest": current,
                "previous": previous,
                "change": round(current - previous, 2),
            }

        return comparison

    # ----------------------------------------------------------
    # Main comparison
    # ----------------------------------------------------------

    def compare_latest_results(self, symbol: str):
        """
        Compare the latest quarter of a company:
        - QoQ against the consecutive previous quarter
        - YoY against the same quarter of the previous year

        Returns a consistent structured result suitable for the
        downstream AI workflow.
        """

        quarters = self._collect_quarters(symbol)

        empty = {
            "symbol": symbol,
            "qoq": {},
            "yoy": {},
            "latest": {},
            "previous": {},
            "same_quarter_last_year": {},
            "latest_raw_data": {},
            "latest_seq": None,
            "previous_seq": None,
            "yoy_seq": None,
            "message": "Not enough valid quarterly data available",
        }

        if len(quarters) < 2:
            return empty

        latest = quarters[0]
        latest_data = latest["result"].financial_data or {}

        # ----------------------------------------------------------
        # Previous quarter (QoQ)
        #
        # Only an immediately adjacent quarter range is a valid QoQ
        # comparison period.
        # ----------------------------------------------------------

        previous = None

        expected_previous_from = self._add_months(
            latest["from_date"],
            -3
        )

        if quarters[1]["from_date"] == expected_previous_from:
            previous = quarters[1]

        # ----------------------------------------------------------
        # Same quarter previous year (YoY)
        # ----------------------------------------------------------

        yoy = None

        for item in quarters:

            if (
                self._add_months(item["from_date"], 12)
                == latest["from_date"]
            ):
                yoy = item
                break

        previous_data = (
            previous["result"].financial_data
            if previous
            else {}
        )

        yoy_data = (
            yoy["result"].financial_data
            if yoy
            else {}
        )

        return {
            "symbol": symbol,

            "latest_seq": latest["result"].seq_number,
            "latest_date": latest["result"].filing_date,

            "previous_seq": (
                previous["result"].seq_number
                if previous
                else None
            ),
            "previous_date": (
                previous["result"].filing_date
                if previous
                else None
            ),

            "yoy_seq": (
                yoy["result"].seq_number
                if yoy
                else None
            ),

            "qoq": (
                self._compare_metrics(latest_data, previous_data)
                if previous
                else {}
            ),

            "yoy": (
                self._compare_metrics(latest_data, yoy_data)
                if yoy
                else {}
            ),

            "latest": latest_data,
            "previous": previous_data,
            "same_quarter_last_year": yoy_data,

            "latest_raw_data": latest["result"].raw_data or {},

            "periods": {
                "latest": {
                    "from": latest["from_date"].strftime("%d-%b-%Y"),
                    "to": latest["to_date"].strftime("%d-%b-%Y"),
                },
                "previous": (
                    {
                        "from": previous["from_date"].strftime("%d-%b-%Y"),
                        "to": previous["to_date"].strftime("%d-%b-%Y"),
                    }
                    if previous
                    else None
                ),
                "yoy": (
                    {
                        "from": yoy["from_date"].strftime("%d-%b-%Y"),
                        "to": yoy["to_date"].strftime("%d-%b-%Y"),
                    }
                    if yoy
                    else None
                ),
            },
        }