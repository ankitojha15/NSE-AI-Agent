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
            raw_data=result_data
        )

        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)

        return result