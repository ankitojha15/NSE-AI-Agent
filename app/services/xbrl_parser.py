import xml.etree.ElementTree as ET


class XBRLParser:
    """
    Parse XBRL XML documents.

    Responsible only for reading XML.
    It does not download or store data.
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

    def extract_financial_data(self, root):
        """
        Extract important financial metrics from XBRL.

        Returns
        -------
        dict
            Dictionary containing extracted values.
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

        data = {}

        # Visit every XML element
        for element in root.iter():

            # Remove namespace
            tag = element.tag.split("}")[-1]

            if tag in required_tags:

                data[required_tags[tag]] = self._to_number(element.text)

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
            data["ebitda"] = (
                profit_before_tax
                + finance_cost
                + depreciation
            )


        # Operating Profit
        # Remove non-operating income
        if (
            data.get("ebitda") is not None
            and other_income is not None
        ):
            data["operating_profit"] = (
                data["ebitda"]
                - other_income
            )


        # Operating Profit Margin (OPM)
        if (
            sales
            and data.get("operating_profit") is not None
        ):
            data["opm"] = (
                data["operating_profit"]
                / sales
            ) * 100


        # Net Profit Margin
        if (
            sales
            and net_profit is not None
        ):
            data["net_profit_margin"] = (
                net_profit
                / sales
            ) * 100
            
        return data