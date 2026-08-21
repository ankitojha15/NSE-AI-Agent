import math
import xml.etree.ElementTree as ET

from app.utils.logger import logger


# 1 crore = 10,000,000 units of the base currency.
# Monetary values in XBRL are reported in absolute currency units.
# For consistent analysis they are normalized to crores.
CRORE = 10_000_000


class XBRLParser:
    """
    Parse XBRL XML documents.

    Responsible only for reading XML and extracting normalized
    financial data. It does not download or store data.
    """

    def parse(self, xml_content: str):
        """
        Convert XML text into an ElementTree object.

        Parameters
        ----------
        xml_content : str
            Raw XML downloaded from NSE.

        Returns
        -------
        Element
            Root element of the XML tree.
        """

        return ET.fromstring(xml_content)

    def print_financial_tags(self, root):
        """
        Print financial tags that belong to the BSE/NSE taxonomy.
        """

        found = set()

        for element in root.iter():

            if "in-bse-fin" in element.tag:
                found.add(element.tag)

        for tag in sorted(found):
            print(tag)

    def export_tags(self, root, filename: str = "tags.txt"):
        """
        Export all unique XML tags to a text file.
        """

        tags = sorted({element.tag for element in root.iter()})

        with open(filename, "w") as file:
            for tag in tags:
                file.write(tag + "\n")

        print(f"Exported {len(tags)} tags.")

    def _to_number(self, value):
        """
        Convert XBRL value into float.

        Returns None if conversion fails.
        """

        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_units(self, root):
        """
        Build a map of XBRL unit ids to their measure text.
        """

        units = {}

        for element in root.iter():

            if element.tag.split("}")[-1] != "unit":
                continue

            unit_id = element.get("id")

            for child in element:

                if child.tag.split("}")[-1] != "measure":
                    continue

                units[unit_id] = (child.text or "").strip()
                break

        return units

    def _detect_currency(self, units):
        """
        Detect the reporting currency from the XBRL units.

        Returns
        -------
        str | None
            ISO currency code (e.g. "INR") or None.
        """

        for measure in units.values():

            if measure.startswith("iso4217:"):
                return measure.split(":")[1]

        return None

    def _normalize_monetary(self, value, measure):
        """
        Convert a monetary value into crores.

        Only iso4217 measures are monetary amounts and get scaled.
        Per-share values (e.g. EPS) and ratios are left unchanged.

        Returns None when the value cannot be converted.
        """

        if value is None:
            return None

        if measure and measure.startswith("iso4217:"):
            return round(value / CRORE, 2)

        return value

    def _extract_contexts(self, root):
        """
        Build a map of context id -> (startDate, endDate) for period filtering.

        XBRL filings for Q4 audited results contain both quarterly (OneD,
        3 months) and annual (FourD, 12 months) contexts. We must pick
        the quarterly one for QoQ.
        """

        contexts = {}

        for element in root.iter():
            if element.tag.split("}")[-1] != "context":
                continue

            ctx_id = element.get("id")
            if not ctx_id:
                continue

            start = None
            end = None

            for child in element:
                if child.tag.split("}")[-1] == "period":
                    for sub in child:
                        tag = sub.tag.split("}")[-1]
                        if tag == "startDate":
                            start = (sub.text or "").strip()
                        elif tag == "endDate":
                            end = (sub.text or "").strip()
                        elif tag == "instant":
                            # Annual instant - not quarterly
                            end = (sub.text or "").strip()

            if start and end:
                contexts[ctx_id] = (start, end)
            elif end:
                # Instant context - treat as single day period
                contexts[ctx_id] = (end, end)

        return contexts

    def _is_quarterly_context(self, start, end):
        """Return True if the period duration looks like a quarter (~89-93 days)."""

        if not start or not end:
            return False

        try:
            from datetime import datetime

            s = datetime.strptime(start, "%Y-%m-%d")
            e = datetime.strptime(end, "%Y-%m-%d")
            delta = (e - s).days + 1  # inclusive
            return 85 <= delta <= 95
        except Exception:
            return False

    def _sanitize(self, data):
        """
        Remove non-finite values (NaN, Infinity) from the data.
        """

        for key, value in list(data.items()):

            if isinstance(value, float) and not math.isfinite(value):
                data[key] = None

        return data

    def extract_financial_data(self, root, expected_from=None, expected_to=None):
        """
        Extract and normalize important financial metrics from XBRL.

        Monetary values are normalized into crores. The original
        currency and unit information is preserved in the metadata
        keys. Missing tags are skipped safely.

        Returns
        -------
        dict
            Dictionary containing normalized values plus
            "currency" and "unit" metadata.
        """

        # Tags we care about
        required_tags = {
            "RevenueFromOperations": "sales",
            "Income": "total_income",
            "OtherIncome": "other_income",
            "Expenses": "total_expenses",
            "EmployeeBenefitExpense": "employee_expense",
            "FinanceCosts": "finance_cost",
            "DepreciationDepletionAndAmortisationExpense": "depreciation",
            "ProfitBeforeTax": "profit_before_tax",
            "TaxExpense": "tax",
            "ProfitLossForPeriod": "net_profit",
            "BasicEarningsLossPerShareFromContinuingOperations": "basic_eps",
            "DilutedEarningsLossPerShareFromContinuingOperations": "diluted_eps"
        }

        units = self._extract_units(root)

        currency = self._detect_currency(units)

        contexts = self._extract_contexts(root)

        # If expected period is known, we strictly match it.
        # Otherwise, we prefer quarterly contexts over annual.
        expected_start = None
        expected_end = None
        if expected_from and expected_to:
            try:
                from datetime import datetime
                # expected_from/to are like "01-Jan-2026" — convert to YYYY-MM-DD for comparison
                # Try to parse both formats
                for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
                    try:
                        expected_start = datetime.strptime(expected_from, fmt).strftime("%Y-%m-%d")
                        break
                    except Exception:
                        continue
                for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
                    try:
                        expected_end = datetime.strptime(expected_to, fmt).strftime("%Y-%m-%d")
                        break
                    except Exception:
                        continue
            except Exception:
                pass

        data = {}
        # Track which metrics we have already filled with a quarterly context
        # so we don't overwrite them with an annual context later.
        filled_quarterly = set()

        # Visit every XML element
        for element in root.iter():

            # Remove namespace
            tag = element.tag.split("}")[-1]

            if tag in required_tags:

                # Context-based filtering: prefer quarterly period
                ctx_id = element.get("contextRef")
                ctx_start, ctx_end = contexts.get(ctx_id, (None, None))

                # If we know the expected filing period, only accept exact match
                if expected_start and expected_end:
                    if ctx_start != expected_start or ctx_end != expected_end:
                        continue
                else:
                    # No expected period: skip annual contexts, only take quarterly
                    if ctx_start and ctx_end and not self._is_quarterly_context(ctx_start, ctx_end):
                        # If we already have a quarterly value for this metric, skip annual
                        # Otherwise, allow it as fallback only if no quarterly found yet
                        metric_key = required_tags[tag]
                        if metric_key in filled_quarterly:
                            continue
                        # Check if this is annual (12 months) — skip to prefer quarterly later
                        # But if no quarterly exists at all, we'll take it as last resort
                        # For now, skip non-quarterly and see if quarterly comes later
                        # To handle ordering where annual comes after quarterly, we check:
                        # If metric already filled with quarterly, skip annual
                        if metric_key in data:
                            # Data already has a value — check if existing was quarterly
                            # If current is annual and existing is quarterly, skip
                            continue

                value = self._to_number(element.text)

                measure = units.get(element.get("unitRef"))

                metric_key = required_tags[tag]
                normalized = self._normalize_monetary(value, measure)

                # Track if this was a quarterly context
                is_q = self._is_quarterly_context(ctx_start, ctx_end) if ctx_start and ctx_end else True
                if is_q:
                    filled_quarterly.add(metric_key)

                data[metric_key] = normalized

        # ---------------------------------------------------------
        # Calculate derived financial metrics
        # ---------------------------------------------------------

        sales = data.get("sales")
        other_income = data.get("other_income", 0)
        finance_cost = data.get("finance_cost", 0)
        depreciation = data.get("depreciation", 0)
        profit_before_tax = data.get("profit_before_tax")
        net_profit = data.get("net_profit")

        # EBITDA
        # Formula:
        # EBITDA = Profit Before Tax + Finance Cost + Depreciation
        if (
            profit_before_tax is not None
            and finance_cost is not None
            and depreciation is not None
        ):
            data["ebitda"] = round(
                profit_before_tax
                + finance_cost
                + depreciation,
                2
            )

        # Operating Profit
        # Remove non-operating income
        if (
            data.get("ebitda") is not None
            and other_income is not None
        ):
            data["operating_profit"] = round(
                data["ebitda"]
                - other_income,
                2
            )

        # Operating Profit Margin (OPM)
        if (
            sales
            and data.get("operating_profit") is not None
        ):
            data["opm"] = round(
                (
                    data["operating_profit"]
                    / sales
                ) * 100,
                2
            )

        # Net Profit Margin
        if (
            sales
            and net_profit is not None
        ):
            data["net_profit_margin"] = round(
                (
                    net_profit
                    / sales
                ) * 100,
                2
            )

        # ---------------------------------------------------------
        # Validation and metadata
        # ---------------------------------------------------------

        data = self._sanitize(data)

        for metric in ("sales", "net_profit"):

            if metric not in data:

                logger.warning(
                    "XBRL METRIC MISSING: %s",
                    metric
                )

        data["currency"] = currency or "INR"

        data["unit"] = "crore"

        data["conversion_factor"] = CRORE

        return data