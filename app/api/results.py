from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.repositories.financial_result_repository import (
    FinancialResultRepository
)
from app.schemas.results import (
    ComparisonResponse,
    FinancialResultItem,
    InsightsResponse,
)
from app.services.financial_analysis_service import (
    FinancialAnalysisService
)
from app.services.financial_insight_service import FinancialInsightService


router = APIRouter(
    prefix="/companies",
    tags=["Financial Results"],
)


def _validate_symbol(symbol: str):
    symbol = (symbol or "").strip().upper()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="symbol is required",
        )

    return symbol


@router.get("/{symbol}/results", response_model=list[FinancialResultItem])
def get_financial_results(
    symbol: str,
    db: Session = Depends(get_db),
):
    """
    Financial results history for a company, latest filing first.
    """

    symbol = _validate_symbol(symbol)

    results = FinancialResultRepository(db).get_company_history(symbol)

    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No financial results found for {symbol}",
        )

    return results


@router.get("/{symbol}/comparison", response_model=ComparisonResponse)
def get_comparison(
    symbol: str,
    db: Session = Depends(get_db),
):
    """
    QoQ / YoY comparison for the latest quarter of a company.
    """

    symbol = _validate_symbol(symbol)

    analysis = FinancialAnalysisService(db).compare_latest_results(symbol)

    if analysis.get("message"):
        raise HTTPException(
            status_code=404,
            detail=f"{analysis['message']} for {symbol}",
        )

    # Normalize the analysis "periods" (from/to) to the response
    # schema field names (from_date/to_date).
    periods = analysis.get("periods") or {}

    def convert_period(period):
        if not period:
            return None
        return {
            "from_date": period.get("from"),
            "to_date": period.get("to"),
        }

    analysis["periods"] = {
        "latest": convert_period(periods.get("latest")),
        "previous": convert_period(periods.get("previous")),
        "yoy": convert_period(periods.get("yoy")),
    }

    return analysis


@router.get("/{symbol}/insights", response_model=InsightsResponse)
def get_insights(
    symbol: str,
    db: Session = Depends(get_db),
):
    """
    Rule-based financial insights for the latest quarter.
    """

    symbol = _validate_symbol(symbol)

    analysis = FinancialAnalysisService(db).compare_latest_results(symbol)

    if analysis.get("message"):
        raise HTTPException(
            status_code=404,
            detail=f"{analysis['message']} for {symbol}",
        )

    return FinancialInsightService().analyze(analysis)