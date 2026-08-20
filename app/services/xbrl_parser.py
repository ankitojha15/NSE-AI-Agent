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

    def _sanitize(self, data):
        """
        Remove non-finite values (NaN, Infinity) from the data.
        """

        for key, value in list(data.items()):

            if isinstance(value, float) and not math.isfinite(value):
                data[key] = None

        return data

    def extract_financial_data(self, root):
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

        data = {}

        # Visit every XML element
        for element in root.iter():

            # Remove namespace
            tag = element.tag.split("}")[-1]

            if tag in required_tags:

                value = self._to_number(element.text)

                measure = units.get(element.get("unitRef"))

                data[required_tags[tag]] = self._normalize_monetary(
                    value,
                    measure
                )

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