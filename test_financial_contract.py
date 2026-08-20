from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.repositories.financial_result_repository import FinancialResultRepository
from app.services.financial_contract_service import FinancialAnalysisContractService


def filing(symbol, qe_date, seq, financial_data):
    return {
        "seq_Id": str(seq),
        "symbol": symbol,
        "cmName": symbol + " Limited",
        "creation_Date": "10-Aug-2026 12:00:00",
        "qe_Date": qe_date,
        "audited": "Yes",
        "consolidated": "No",
        "xbrl": "http://example.com/x.xml",
        "financial_data": financial_data,
    }


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed(db, filings):
    repo = FinancialResultRepository(db)
    for f in filings:
        repo.create(f)


def full_quarters():
    """
    Five consecutive quarters for ABC:
    Q4 FY26 (latest) ... Q3 FY26 ... Q2 FY26 ... Q1 FY26 ... Q4 FY25
    """
    return [
        filing("ABC", "31-MAR-2026", 101, {
            "sales": 400, "ebitda": 120, "net_profit": 60,
            "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0,
        }),
        filing("ABC", "31-DEC-2025", 102, {
            "sales": 300, "ebitda": 90, "net_profit": 50,
            "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67,
        }),
        filing("ABC", "30-SEP-2025", 103, {
            "sales": 320, "ebitda": 100, "net_profit": 40,
            "basic_eps": 4.0, "opm": 21.0, "net_profit_margin": 12.5,
        }),
        filing("ABC", "30-JUN-2025", 104, {
            "sales": 280, "ebitda": 85, "net_profit": 45,
            "basic_eps": 4.5, "opm": 19.0, "net_profit_margin": 16.07,
        }),
        filing("ABC", "31-MAR-2025", 105, {
            "sales": 350, "ebitda": 100, "net_profit": 55,
            "basic_eps": 5.5, "opm": 21.0, "net_profit_margin": 15.71,
        }),
    ]


def main():

    # ========== 1. VALID FINANCIAL DATA ==========
    print("== 1. VALID FINANCIAL DATA ==")
    db = make_db()
    seed(db, full_quarters())
    contract = FinancialAnalysisContractService(db).build("ABC")

    # Latest snapshot: Revenue/Sales, EBITDA, Net Profit, EPS, OPM, NPM
    assert contract.latest.sales == 400.0, contract.latest
    assert contract.latest.ebitda == 120.0
    assert contract.latest.net_profit == 60.0
    assert contract.latest.basic_eps == 6.0
    assert contract.latest.opm == 22.0
    assert contract.latest.net_profit_margin == 15.0

    # QoQ / YoY comparisons populated
    assert contract.qoq["sales"].growth_percent == 33.33
    assert contract.qoq["opm"].change == 2.0
    assert contract.yoy["sales"].growth_percent == 14.29
    assert contract.yoy["net_profit"].growth_percent == 9.09

    # Rule-based insights
    assert contract.insights.positive, contract.insights
    assert contract.insights.growth_analysis, contract.insights

    # Periods
    assert contract.periods.latest.from_date == "01-Jan-2026"
    assert contract.periods.previous.from_date == "01-Oct-2025"
    assert contract.periods.yoy.from_date == "01-Jan-2025"

    # Completeness
    assert contract.completeness.has_latest is True
    assert contract.completeness.has_previous is True
    assert contract.completeness.has_qoq is True
    assert contract.completeness.has_yoy is True
    assert contract.completeness.missing_metrics == []

    # JSON-ready for the future LangGraph/LLM workflow
    dumped = contract.model_dump()
    assert isinstance(dumped, dict)
    assert dumped["qoq"]["sales"]["metric"] == "sales"
    json_str = contract.model_dump_json()
    assert '"symbol":"ABC"' in json_str

    print("  OK -> valid data produces a complete contract")
    db.close()

    # ========== 2. INCOMPLETE FINANCIAL DATA ==========
    print("== 2. INCOMPLETE FINANCIAL DATA ==")

    # 2a. Missing metric in the latest quarter
    db = make_db()
    filings = full_quarters()
    latest = next(f for f in filings if f["seq_Id"] == "101")
    latest["financial_data"]["ebitda"] = None
    latest["financial_data"]["net_profit"] = "not-a-number"
    seed(db, filings)
    contract = FinancialAnalysisContractService(db).build("ABC")

    assert contract.latest.sales == 400.0
    assert contract.latest.ebitda is None
    assert contract.latest.net_profit is None
    assert "ebitda" in contract.completeness.missing_metrics
    assert "net_profit" in contract.completeness.missing_metrics
    assert "ebitda" not in contract.qoq
    assert contract.qoq["sales"].growth_percent == 33.33
    assert contract.completeness.has_qoq is True

    print("  OK -> missing metrics degrade safely")
    db.close()

    # 2b. Too few quarters (only one filing)
    db = make_db()
    seed(db, [full_quarters()[0]])
    contract = FinancialAnalysisContractService(db).build("ABC")

    assert contract.message is not None
    assert contract.qoq == {} and contract.yoy == {}
    assert contract.latest.sales is None
    assert contract.completeness.has_latest is False
    assert contract.completeness.has_qoq is False
    assert sorted(contract.completeness.missing_metrics) == sorted(
        ["sales", "ebitda", "net_profit", "basic_eps", "opm",
         "net_profit_margin"]
    )

    print("  OK -> too few quarters degrades gracefully")
    db.close()

    # ========== 3. MISSING FINANCIAL DATA ==========
    print("== 3. MISSING FINANCIAL DATA ==")
    db = make_db()
    contract = FinancialAnalysisContractService(db).build("NODATA")

    assert contract.symbol == "NODATA"
    assert contract.message is not None
    assert contract.latest.sales is None
    assert contract.qoq == {} and contract.yoy == {}
    assert contract.insights.positive == []
    assert contract.insights.risk_flags == []
    assert contract.completeness.has_latest is False
    assert contract.completeness.has_yoy is False
    assert len(contract.completeness.missing_metrics) == 6
    assert contract.periods.latest is None

    json_str = contract.model_dump_json()
    assert '"symbol":"NODATA"' in json_str

    print("  OK -> missing data produces a safe empty contract")
    db.close()

    print("\nALL STEP 8 CHECKS PASSED")


if __name__ == "__main__":
    main()