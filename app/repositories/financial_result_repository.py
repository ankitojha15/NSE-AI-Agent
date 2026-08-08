from sqlalchemy.orm import Session

from app.models.financial_results import FinancialResult


class FinancialResultRepository:
    """
    Handles all database operations related to financial results.
    """

    def __init__(self, db: Session):
        self.db = db

    def exists(self, seq_number: str) -> bool:
        """
        Check whether a financial result already exists.
        """
        return (
            self.db.query(FinancialResult)
            .filter(FinancialResult.seq_number == seq_number)
            .first()
            is not None
        )

    def create(self, result_data: dict):
        """
        Store a new financial result.
        """

        result = FinancialResult(
            seq_number=result_data.get("seqNumber"),
            symbol=result_data.get("symbol"),
            company_name=result_data.get("companyName"),
            filing_date=result_data.get("filingDate"),
            period=result_data.get("period"),
            audited=result_data.get("audited"),
            consolidated=result_data.get("consolidated"),
            xbrl_url=result_data.get("xbrl"),
            raw_data=result_data,
            financial_data=result_data.get("financial_data")
        )

        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)

        return result

    def get_company_history(self, symbol: str):
        """
        Return all financial results of a company ordered
        by filing date (latest first).
        """

        return (
            self.db.query(FinancialResult)
            .filter(
                FinancialResult.symbol == symbol
            )
            .order_by(
                FinancialResult.filing_date.desc()
            )
            .all()
        )

    def get_latest_result(self, symbol: str):
        """
        Return the latest financial result for a company.
        """

        return (
            self.db.query(FinancialResult)
            .filter(
                FinancialResult.symbol == symbol
            )
            .order_by(
                FinancialResult.filing_date.desc()
            )
            .first()
        )


    def get_previous_result(self, symbol: str):
        """
        Return the previous financial result for a company.
        """

        return (
            self.db.query(FinancialResult)
            .filter(
                FinancialResult.symbol == symbol
            )
            .order_by(
                FinancialResult.filing_date.desc()
            )
            .offset(1)
            .first()
        )

