from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.utils.quarter_utils import get_quarter_dates
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

    def get_by_seq_number(self, seq_number: str):
        """
        Return an existing financial result using NSE sequence number.
        """
        return (
            self.db.query(FinancialResult)
            .filter(FinancialResult.seq_number == seq_number)
            .first()
        )

    def create(self, result_data: dict):
        """
        Store a new integrated financial result.

        Safe against duplicate sequence numbers: if the filing already
        exists, the existing record is returned instead of inserting a
        duplicate. Missing financial_data is backfilled when the new
        data provides it.
        """

        # Integrated Filing API uses seq_Id.
        seq_number = result_data.get("seq_Id") or result_data.get("seqNumber")

        existing = self.get_by_seq_number(seq_number)

        if existing:
            if (
                not existing.financial_data
                and result_data.get("financial_data")
            ):
                return self.update_financial_data(
                    seq_number,
                    result_data["financial_data"]
                )

            return existing

        from_date, to_date = get_quarter_dates(
        result_data.get("qe_Date")
        )

        result_data["fromDate"] = from_date
        result_data["toDate"] = to_date

        result = FinancialResult(
            seq_number=seq_number,
            symbol=result_data.get("symbol"),
            company_name=result_data.get("cmName"),
            filing_date=result_data.get("creation_Date"),
            period=result_data.get("qe_Date"),
            audited=result_data.get("audited"),
            consolidated=result_data.get("consolidated"),
            xbrl_url=result_data.get("xbrl"),
            raw_data=result_data,
            financial_data=result_data.get("financial_data")
        )

        self.db.add(result)

        print("DB INSERT START:", seq_number)

        try:
            self.db.commit()
        except IntegrityError:
            # A concurrent insert won the race for this sequence number.
            # Return the already-stored record instead of crashing.
            self.db.rollback()
            return self.get_by_seq_number(seq_number)

        print("DB COMMIT COMPLETE:", seq_number)

        self.db.refresh(result)

        print("DB REFRESH COMPLETE:", seq_number)

        return result

    def upsert(self, result_data: dict):
        """
        Insert a new filing or update an existing one.

        Filings are matched by their unique NSE sequence number
        (seq_Id / seqNumber) so the same filing is never stored twice.

        If the filing already exists but its financial_data is missing
        while new financial data is available, the existing record is
        updated instead of inserting a duplicate.

        Returns
        -------
        (FinancialResult, str)
            The filing record and its state:
            "created", "updated", or "unchanged".
        """

        seq_number = result_data.get("seq_Id") or result_data.get("seqNumber")

        existing = self.get_by_seq_number(seq_number)

        if existing is None:
            return self.create(result_data), "created"

        if (
            not existing.financial_data
            and result_data.get("financial_data")
        ):
            return (
                self.update_financial_data(
                    seq_number,
                    result_data["financial_data"]
                ),
                "updated"
            )

        return existing, "unchanged"

    def update_financial_data(
        self,
        seq_number: str,
        financial_data: dict
    ):
        """
        Update financial data for an existing result.
        """

        result = (
            self.db.query(FinancialResult)
            .filter(
                FinancialResult.seq_number == seq_number
            )
            .first()
        )

        if not result:
            return None

        result.financial_data = financial_data

        self.db.commit()
        self.db.refresh(result)

        return result

    def get_company_history(self, symbol: str):
        """
        Return all financial results of a company.
        Latest filing first.
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

    def get_company_quarters(self, symbol: str):
        """
        Return all unique quarterly financial results for a company.

        Duplicate NSE filings for the same quarter are removed.
        """

        results = (
            self.db.query(FinancialResult)
            .filter(
                FinancialResult.symbol == symbol
            )
            .order_by(
                FinancialResult.filing_date.desc()
            )
            .all()
        )

        unique_quarters = {}

        for result in results:

            raw_data = result.raw_data or {}

            from_date = raw_data.get("fromDate")
            to_date = raw_data.get("toDate")

            if not from_date or not to_date:
                continue

            quarter_key = (from_date, to_date)

            if quarter_key not in unique_quarters:
                unique_quarters[quarter_key] = result

        return list(unique_quarters.values())

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

    def get_yoy_result(
        self,
        symbol: str,
        target_from_date: str,
        target_to_date: str
    ):
        """
        Return the result for the same quarter
        from the previous financial year.
        """

        results = (
            self.db.query(FinancialResult)
            .filter(
                FinancialResult.symbol == symbol
            )
            .all()
        )

        for result in results:

            raw_data = result.raw_data or {}

            if (
                raw_data.get("fromDate") == target_from_date
                and raw_data.get("toDate") == target_to_date
            ):
                return result

        return None

