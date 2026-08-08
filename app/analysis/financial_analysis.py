class FinancialAnalysis:
    """
    Performs financial calculations on extracted financial data.

    This class does NOT fetch data from NSE or the database.
    It only performs business calculations.
    """

    @staticmethod
    def calculate_growth(current, previous):
        """
        Calculate percentage growth.

        Formula:
            ((Current - Previous) / Previous) * 100

        Returns
        -------
        float | None
            Percentage growth or None if calculation
            cannot be performed.
        """

        # Cannot divide by zero
        if previous in (None, 0):
            return None

        # Current value missing
        if current is None:
            return None

        return ((current - previous) / previous) * 100

    @staticmethod
    def compare_periods(current: dict, previous: dict):
        """
        Compare two financial statements and calculate growth metrics.

        Parameters
        ----------
        current : dict
            Current period financial data.

        previous : dict
            Previous period financial data.

        Returns
        -------
        dict
            Growth metrics.
        """

        return {

            # Revenue Growth
            "sales_growth": FinancialAnalysis.calculate_growth(
                current.get("sales"),
                previous.get("sales")
            ),

            # Net Profit Growth
            "net_profit_growth": FinancialAnalysis.calculate_growth(
                current.get("net_profit"),
                previous.get("net_profit")
            ),

            # EBITDA Growth
            "ebitda_growth": FinancialAnalysis.calculate_growth(
                current.get("ebitda"),
                previous.get("ebitda")
            ),

            # EPS Growth
            "eps_growth": FinancialAnalysis.calculate_growth(
                current.get("basic_eps"),
                previous.get("basic_eps")
            )
        }

    @staticmethod
    def calculate_margin(value, sales):
        """
        Calculate margin as a percentage of sales.

        Formula:
            (value / sales) * 100
        """

        if sales in (None, 0):
            return None

        if value is None:
            return None

        return (value / sales) * 100


    @staticmethod
    def calculate_margins(financials: dict):
        """
        Calculate all important financial margins.

        Parameters
        ----------
        financials : dict
            Financial data extracted from XBRL.

        Returns
        -------
        dict
            Margin metrics.
        """

        sales = financials.get("sales")

        return {

            # EBITDA Margin
            "ebitda_margin": FinancialAnalysis.calculate_margin(
                financials.get("ebitda"),
                sales
            ),

            # Operating Profit Margin
            "opm": FinancialAnalysis.calculate_margin(
                financials.get("operating_profit"),
                sales
            ),

            # Net Profit Margin
            "net_profit_margin": FinancialAnalysis.calculate_margin(
                financials.get("net_profit"),
                sales
            )
        }

    @staticmethod
    def detect_trend(current, previous, threshold: float = 1.0):
        """
        Detect the trend between two values.

        Parameters
        ----------
        current : float
            Current period value.

        previous : float
            Previous period value.

        threshold : float
            Minimum percentage change required to consider
            the trend increasing or decreasing.

        Returns
        -------
        str | None
            "Increasing", "Decreasing", "Stable", or None.
        """

        growth = FinancialAnalysis.calculate_growth(
            current,
            previous
        )

        if growth is None:
            return None

        if growth > threshold:
            return "Increasing"

        if growth < -threshold:
            return "Decreasing"

        return "Stable"


    @staticmethod
    def generate_insights(current: dict, previous: dict):
        """
        Generate business insights by comparing two periods.
        """

        insights = []

        # -----------------------------
        # Growth calculations
        # -----------------------------
        sales_growth = FinancialAnalysis.calculate_growth(
            current.get("sales"),
            previous.get("sales")
        )

        profit_growth = FinancialAnalysis.calculate_growth(
            current.get("net_profit"),
            previous.get("net_profit")
        )

        ebitda_growth = FinancialAnalysis.calculate_growth(
            current.get("ebitda"),
            previous.get("ebitda")
        )

        # -----------------------------
        # Revenue
        # -----------------------------
        if sales_growth is not None:

            if sales_growth > 1:
                insights.append("Revenue increased.")

            elif sales_growth < -1:
                insights.append("Revenue decreased.")

            else:
                insights.append("Revenue remained stable.")

        # -----------------------------
        # Net Profit
        # -----------------------------
        if profit_growth is not None:

            if profit_growth > 1:
                insights.append("Net profit increased.")

            elif profit_growth < -1:
                insights.append("Net profit decreased.")

            else:
                insights.append("Net profit remained stable.")

        # -----------------------------
        # EBITDA
        # -----------------------------
        if ebitda_growth is not None:

            if ebitda_growth > 1:
                insights.append("EBITDA increased.")

            elif ebitda_growth < -1:
                insights.append("EBITDA decreased.")

        # -----------------------------
        # Business Rules
        # -----------------------------

        if (
            sales_growth is not None
            and profit_growth is not None
        ):

            if sales_growth > 0 and profit_growth < 0:
                insights.append(
                    "Revenue increased but net profit declined."
                )

            elif sales_growth < 0 and profit_growth > 0:
                insights.append(
                    "Revenue declined but net profit increased."
                )

            elif profit_growth > sales_growth:
                insights.append(
                    "Net profit is growing faster than revenue."
                )

            elif sales_growth > profit_growth:
                insights.append(
                    "Revenue is growing faster than net profit."
                )

        return insights