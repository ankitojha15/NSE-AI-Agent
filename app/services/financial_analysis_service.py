from app.repositories.financial_result_repository import FinancialResultRepository


print("### FINANCIAL_ANALYSIS_SERVICE LOADED ###")


class FinancialAnalysisService:
    """
    Compares financial results of a company.
    """

    def __init__(self, db):
        """
        Initialize the analysis service with a database session.
        """
        self.repository = FinancialResultRepository(db)

    def compare_latest_results(self, symbol: str):

        print(">>> NEW FINANCIAL ANALYSIS SERVICE RUNNING <<<")

        history = self.repository.get_company_history(symbol)

        if len(history) < 2:
            return None

        latest = history[0]
        previous = history[1]

        latest_data = latest.financial_data or {}
        previous_data = previous.financial_data or {}

        latest_to_date = (latest.raw_data or {}).get("toDate")

        print(">>> latest_to_date:", latest_to_date)

        yoy_result = None

        if latest_to_date:

            from datetime import datetime

            latest_date = datetime.strptime(
                latest_to_date,
                "%d-%b-%Y"
            )

            yoy_target_date = latest_date.replace(
                year=latest_date.year - 1
            )

            if latest_date.month == 3:
                yoy_target_from = yoy_target_date.replace(
                    month=1,
                    day=1
                )

            elif latest_date.month == 6:
                yoy_target_from = yoy_target_date.replace(
                    month=4,
                    day=1
                )

            elif latest_date.month == 9:
                yoy_target_from = yoy_target_date.replace(
                    month=7,
                    day=1
                )

            elif latest_date.month == 12:
                yoy_target_from = yoy_target_date.replace(
                    month=10,
                    day=1
                )

            else:
                yoy_target_from = None

            if yoy_target_from:

                target_from = yoy_target_from.strftime(
                    "%d-%b-%Y"
                )

                target_to = yoy_target_date.strftime(
                    "%d-%b-%Y"
                )

                print("YOY TARGET FROM:", target_from)
                print("YOY TARGET TO:", target_to)

                yoy_result = self.repository.get_yoy_result(
                    symbol,
                    target_from,
                    target_to
                )

                print(
                    "YOY RESULT:",
                    yoy_result.seq_number
                    if yoy_result
                    else None
                )

        yoy_data = (
            yoy_result.financial_data
            if yoy_result and yoy_result.financial_data
            else {}
        )

        def growth(current, previous):

            if previous in (None, 0):
                return None

            return (
                (current - previous)
                / abs(previous)
            ) * 100

        def compare_metrics(current_data, previous_data):

            comparison = {}

            metrics = [
                "sales",
                "revenue",
                "ebitda",
                "operating_profit",
                "net_profit",
                "basic_eps",
                "diluted_eps",
            ]

            for metric in metrics:

                current = current_data.get(metric)
                previous_value = previous_data.get(metric)

                if (
                    current is not None
                    and previous_value is not None
                ):

                    comparison[metric] = {
                        "latest": current,
                        "previous": previous_value,
                        "growth_percent": growth(
                            current,
                            previous_value
                        )
                    }

            current_opm = current_data.get("opm")
            previous_opm = previous_data.get("opm")

            if (
                current_opm is not None
                and previous_opm is not None
            ):

                comparison["opm"] = {
                    "latest": current_opm,
                    "previous": previous_opm,
                    "change": (
                        current_opm
                        - previous_opm
                    )
                }

            return comparison

        return {

            "symbol": symbol,

            "latest_date": latest.filing_date,

            "previous_date": previous.filing_date,

            "qoq": compare_metrics(
                latest_data,
                previous_data
            ),

            "yoy": (
                compare_metrics(
                    latest_data,
                    yoy_data
                )
                if yoy_result
                else None
            ),

            "latest": latest_data,

            "previous": previous_data,

            "same_quarter_last_year": yoy_data,

            "latest_raw_data": latest.raw_data or {}
        }