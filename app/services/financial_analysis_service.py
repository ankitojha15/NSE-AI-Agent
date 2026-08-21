import calendar
from datetime import datetime

from app.repositories.financial_result_repository import (
    FinancialResultRepository
)
from app.utils.logger import logger
from app.utils.quarter_utils import quarter_label

print("### FINANCIAL_ANALYSIS_SERVICE LOADED ###")

# Simple in-memory cache for YoY historical lookups to avoid
# duplicate NSE calls when compare_latest_results is invoked
# multiple times for the same company in one pipeline run.
_yoy_cache: dict = {}

# --- Unit normalization (crore) ---
# XBRL parser normalizes monetary values to crore (÷10M) for
# iso4217 measures. Historical rows stored before that fix still
# hold raw INR values (e.g. 5,776,500,000). EPS is per-share,
# margins are percentages — never monetary.
CRORE = 10_000_000
MONETARY_METRICS = frozenset({
    "sales", "revenue", "total_income", "other_income",
    "total_expenses", "employee_expense", "finance_cost",
    "depreciation", "profit_before_tax", "tax",
    "ebitda", "operating_profit", "net_profit",
})
EPS_METRICS = frozenset({"basic_eps", "diluted_eps"})
# Any absolute monetary value above this is almost certainly raw INR.
_RAW_THRESHOLD = 500_000


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

    @staticmethod
    def _normalize_money(metric: str, value: float | None, financial_data: dict | None = None) -> float | None:
        """
        Ensure a monetary value is in crore, exactly once.

        - EPS / margin metrics are never converted.
        - If the financial_data dict explicitly says unit==crore, value
          is already normalized (from XBRL parser).
        - Otherwise, values with |value| > _RAW_THRESHOLD are treated
          as raw INR and divided by CRORE.
        """
        if value is None:
            return None
        if metric in EPS_METRICS:
            return value
        if metric in ("opm", "net_profit_margin"):
            return value
        # financial_data itself carries unit info from XBRL parser
        if financial_data and financial_data.get("unit") == "crore":
            return value
        if isinstance(financial_data, dict) and financial_data.get("conversion_factor") == CRORE:
            return value
        if metric in MONETARY_METRICS and abs(value) > _RAW_THRESHOLD:
            return round(value / CRORE, 2)
        return value

    @staticmethod
    def _normalized_data(raw_financial: dict | None, raw_row_data: dict | None = None) -> dict:
        """Return a copy of financial_data with monetary values normalized to crore."""
        if not raw_financial:
            return {}
        # Use the financial_data's own unit marker to decide if already normalized
        out = {}
        for k, v in raw_financial.items():
            if k in ("currency", "unit", "conversion_factor"):
                out[k] = v
                continue
            num = FinancialAnalysisService._to_number(v)
            if num is None:
                out[k] = v
                continue
            out[k] = FinancialAnalysisService._normalize_money(k, num, raw_financial)
        return out

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
        - Uses derive_period so legacy rows with only qe_Date are
          not silently dropped.
        """

        from app.utils.quarter_utils import derive_period

        history = self.repository.get_company_history(symbol)

        items = []

        for result in history:

            raw_data = result.raw_data or {}

            period = derive_period(raw_data)
            if period is None:
                continue

            from_date = self._parse_date(period[0])
            to_date = self._parse_date(period[1])

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

    def _yoy_historical_lookup(self, symbol: str, target_from, target_to):
        """
        Try to find the YoY quarter beyond the current DB.

        Uses NSE's corporates-financial-results API via NseService.
        Only for quarterly, same-company, same-period lookups.
        Returns a FinancialResult-like dict or None.
        Results are cached per (symbol, target period) within the process.
        """
        cache_key = (symbol, target_from.strftime("%Y%m%d"), target_to.strftime("%Y%m%d"))
        if cache_key in _yoy_cache:
            return _yoy_cache[cache_key]

        # Try NSE historical search for the exact YoY period.
        try:
            from app.services.nse_service import NseService
            from app.services.xbrl_parser import XBRLParser
            from app.services.xbrl_service import XBRLService

            nse = NseService()

            # NSE expects DD-MM-YYYY
            from_str = target_from.strftime("%d-%m-%Y")
            to_str = target_to.strftime("%d-%m-%Y")

            logger.info(
                "YOY HISTORICAL SEARCH | symbol: %s | target: %s → %s",
                symbol, from_str, to_str,
            )

            results = nse.get_financial_results(
                symbol=symbol,
                from_date=from_str,
                to_date=to_str,
            )

            # get_financial_results may return a dict with 'data' or a list
            if isinstance(results, dict):
                candidates = results.get("data") or results.get("results") or []
            else:
                candidates = results or []

            for cand in candidates:
                raw_from = cand.get("fromDate")
                raw_to = cand.get("toDate")
                # Also try qe_Date-derived period
                if not raw_from or not raw_to:
                    from app.utils.quarter_utils import get_quarter_from_qe_date
                    q = get_quarter_from_qe_date(cand.get("qe_Date") or cand.get("period"))
                    if q:
                        raw_from, raw_to = q

                try:
                    c_from = self._parse_date(raw_from)
                    c_to = self._parse_date(raw_to)
                except Exception:
                    continue

                if c_from == target_from and c_to == target_to:
                    # Found exact YoY quarter — persist it for future runs
                    seq = cand.get("seqNumber") or cand.get("seq_Id")
                    if seq and not self.repository.exists(str(seq)):
                        # Try to enrich with XBRL if available
                        if cand.get("xbrl"):
                            try:
                                xbrl_svc = XBRLService()
                                parser = XBRLParser()
                                xml = xbrl_svc.download_xbrl(cand["xbrl"])
                                root = parser.parse(xml)
                                cand["financial_data"] = parser.extract_financial_data(root)
                            except Exception:
                                pass
                        # Normalize symbol key for create()
                        if "symbol" not in cand and "sym" in cand:
                            cand["symbol"] = cand["sym"]
                        if "seq_Id" not in cand and "seqNumber" in cand:
                            cand["seq_Id"] = cand["seqNumber"]
                        try:
                            created = self.repository.create(cand)
                            logger.info(
                                "YOY HISTORICAL STORED | symbol: %s | seq: %s | period: %s → %s",
                                symbol, seq, raw_from, raw_to,
                            )
                            # Return as a quarter-like item
                            item = {
                                "result": created,
                                "from_date": c_from,
                                "to_date": c_to,
                            }
                            _yoy_cache[cache_key] = item
                            return item
                        except Exception:
                            logger.warning(
                                "YOY HISTORICAL STORE FAILED | symbol: %s | seq: %s",
                                symbol, seq, exc_info=True,
                            )
                    else:
                        # Already in DB but was missed by _collect_quarters (e.g. bad financial_data) — return it
                        existing = self.repository.get_by_seq_number(str(seq)) if seq else None
                        if existing:
                            item = {"result": existing, "from_date": c_from, "to_date": c_to}
                            _yoy_cache[cache_key] = item
                            return item

            logger.info(
                "YOY HISTORICAL NOT FOUND | symbol: %s | target: %s → %s | candidates checked: %d",
                symbol, from_str, to_str, len(candidates),
            )
            _yoy_cache[cache_key] = None
        except Exception:
            logger.warning(
                "YOY HISTORICAL SEARCH FAILED | symbol: %s",
                symbol, exc_info=True,
            )
            _yoy_cache[cache_key] = None

        return _yoy_cache.get(cache_key)

    def compare_latest_results(self, symbol: str):
        """
        Compare the latest quarter of a company:
        - QoQ against the consecutive previous quarter
        - YoY against the same quarter of the previous year

        When the YoY quarter is not in the local DB, a historical
        lookup against NSE is attempted for the exact same quarter
        one year earlier.

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
            "yoy_search_exhausted": False,
            "yoy_search_reason": None,
        }

        if len(quarters) < 2:
            return empty

        latest = quarters[0]
        # Normalize monetary values to crore exactly once
        _raw_latest = latest["result"].financial_data or {}
        _raw_latest_row = latest["result"].raw_data or {}
        latest_data = self._normalized_data(_raw_latest, _raw_latest_row)

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

        # Normalize comparison period data to crore
        def _norm(item):
            if not item:
                return {}
            fd = item["result"].financial_data or {}
            rd = item["result"].raw_data or {}
            return self._normalized_data(fd, rd)

        previous_data = _norm(previous)
        # yoy_data will be set below (with historical lookup fallback)
        yoy_data = _norm(yoy) if yoy else {}

        # --- YoY historical backfill when not in local DB ---
        yoy_search_exhausted = False
        yoy_search_reason = None

        if not yoy:
            yoy_target_from = self._add_months(latest["from_date"], -12)
            yoy_target_to = self._add_months(latest["to_date"], -12)
            yoy_from_str = yoy_target_from.strftime("%d-%b-%Y")
            yoy_to_str = yoy_target_to.strftime("%d-%b-%Y")

            cl = quarter_label(
                latest["from_date"].strftime("%d-%b-%Y"),
                latest["to_date"].strftime("%d-%b-%Y"),
            )
            tl = quarter_label(yoy_from_str, yoy_to_str)

            logger.info(
                "YOY TARGET PERIOD | symbol: %s | current: %s (%s) → target YoY: %s (%s)",
                symbol, cl["label"], cl["range"], tl["label"], tl["range"],
            )

            found = self._yoy_historical_lookup(symbol, yoy_target_from, yoy_target_to)

            if found:
                yoy = found
                yoy_data = _norm(yoy)
                logger.info(
                    "YOY MATCH: FOUND | symbol: %s | seq=%s | period: %s → %s",
                    symbol, found["result"].seq_number, yoy_from_str, yoy_to_str,
                )
            else:
                yoy_search_exhausted = True
                yoy_search_reason = (
                    f"no filing for {tl['label']} ({yoy_from_str} → {yoy_to_str}) "
                    f"after historical search"
                )
                logger.info(
                    "YOY MATCH: NOT FOUND after historical search | symbol: %s | target: %s → %s",
                    symbol, yoy_from_str, yoy_to_str,
                )

        # --- Diagnostics (period validation) ---
        cl_info = quarter_label(
            latest["from_date"].strftime("%d-%b-%Y"),
            latest["to_date"].strftime("%d-%b-%Y"),
        )
        logger.info(
            "PERIOD DIAGNOSTICS | symbol: %s | CURRENT PERIOD: %s | PREVIOUS QUARTER PERIOD: %s | YOY PERIOD: %s",
            symbol,
            cl_info["range"],
            f"{previous['from_date'].strftime('%d-%b-%Y')} → {previous['to_date'].strftime('%d-%b-%Y')}" if previous else "none",
            f"{yoy['from_date'].strftime('%d-%b-%Y')} → {yoy['to_date'].strftime('%d-%b-%Y')}" if yoy else "none",
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

            "yoy_search_exhausted": yoy_search_exhausted,
            "yoy_search_reason": yoy_search_reason,
        }