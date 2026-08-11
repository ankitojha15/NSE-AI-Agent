class FinancialInsightService:
    """
    Converts financial comparison data into
    structured financial insights.
    """

    def analyze(self, analysis: dict):
        """
        Analyze QoQ and YoY financial performance.
        """

        qoq = analysis.get("qoq") or {}
        yoy = analysis.get("yoy") or {}

        insights = {
            "positive": [],
            "negative": [],
            "margin_analysis": [],
            "growth_analysis": [],
            "risk_flags": []
        }

        # -------------------------
        # YOY ANALYSIS
        # -------------------------

        for metric, data in yoy.items():

            growth = data.get("growth_percent")

            if growth is None:
                continue

            if growth > 10:
                insights["positive"].append(
                    f"{metric} increased strongly by "
                    f"{growth:.2f}% YoY."
                )

            elif growth > 0:
                insights["positive"].append(
                    f"{metric} increased by "
                    f"{growth:.2f}% YoY."
                )

            elif growth < -10:
                insights["negative"].append(
                    f"{metric} declined significantly by "
                    f"{abs(growth):.2f}% YoY."
                )

            elif growth < 0:
                insights["negative"].append(
                    f"{metric} declined by "
                    f"{abs(growth):.2f}% YoY."
                )

        # -------------------------
        # QOQ ANALYSIS
        # -------------------------

        for metric, data in qoq.items():

            growth = data.get("growth_percent")

            if growth is None:
                continue

            if growth > 10:
                insights["growth_analysis"].append(
                    f"{metric} grew strongly QoQ by "
                    f"{growth:.2f}%."
                )

            elif growth < -10:
                insights["growth_analysis"].append(
                    f"{metric} declined significantly QoQ by "
                    f"{abs(growth):.2f}%."
                )

        # -------------------------
        # MARGIN ANALYSIS
        # -------------------------

        if "opm" in qoq:

            opm_change = qoq["opm"].get("change")

            if opm_change is not None:

                if opm_change > 0:
                    insights["margin_analysis"].append(
                        f"Operating margin improved by "
                        f"{opm_change:.2f} percentage points QoQ."
                    )

                elif opm_change < 0:
                    insights["margin_analysis"].append(
                        f"Operating margin declined by "
                        f"{abs(opm_change):.2f} percentage points QoQ."
                    )

        if "opm" in yoy:

            opm_change = yoy["opm"].get("change")

            if opm_change is not None:

                if opm_change > 0:
                    insights["margin_analysis"].append(
                        f"Operating margin improved by "
                        f"{opm_change:.2f} percentage points YoY."
                    )

                elif opm_change < 0:
                    insights["margin_analysis"].append(
                        f"Operating margin declined by "
                        f"{abs(opm_change):.2f} percentage points YoY."
                    )

        return insights