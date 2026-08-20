from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult


class AnalysisResultRepository:
    """
    Handles database operations for the workflow analysis results.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_by_symbol(self, symbol: str):
        return (
            self.db.query(AnalysisResult)
            .filter(AnalysisResult.symbol == symbol)
            .first()
        )

    def save(
        self,
        symbol: str,
        status: str,
        contract_data: dict | None = None,
        llm_analysis: str | None = None,
        score: int | None = None,
        score_explanation: str | None = None,
        error: str | None = None,
    ):
        """
        Insert or update the analysis result for a company.

        A company has a single analysis result (symbol is unique);
        re-running the workflow overwrites the existing row.
        """

        existing = self.get_by_symbol(symbol)

        if existing is not None:
            existing.status = status
            existing.contract_data = contract_data
            existing.llm_analysis = llm_analysis
            existing.score = score
            existing.score_explanation = score_explanation
            existing.error = error

            self.db.commit()
            self.db.refresh(existing)

            return existing, "updated"

        result = AnalysisResult(
            symbol=symbol,
            status=status,
            contract_data=contract_data,
            llm_analysis=llm_analysis,
            score=score,
            score_explanation=score_explanation,
            error=error,
        )

        self.db.add(result)

        try:
            self.db.commit()
        except IntegrityError:
            # A concurrent workflow created this company's row.
            self.db.rollback()
            return self.save(
                symbol,
                status,
                contract_data,
                llm_analysis,
                score,
                score_explanation,
                error,
            )

        self.db.refresh(result)

        return result, "created"