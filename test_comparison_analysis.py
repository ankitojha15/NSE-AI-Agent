from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.models.financial_results import FinancialResult
from app.repositories.financial_result_repository import FinancialResultRepository
from app.services.financial_analysis_service import FinancialAnalysisService


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

    # ========== 1. VALID QOQ COMPARISON ==========
    print("== 1. VALID QoQ COMPARISON ==")
    db = make_db()
    seed(db, full_quarters())
    analysis = FinancialAnalysisService(db).compare_latest_results("ABC")

    qoq = analysis["qoq"]

    assert analysis["latest_seq"] == "101", analysis
    assert analysis["previous_seq"] == "102", analysis
    assert analysis["periods"]["latest"]["from"] == "01-Jan-2026"
    assert analysis["periods"]["previous"]["from"] == "01-Oct-2025"

    # Growth metrics
    assert qoq["sales"]["growth_percent"] == 33.33, qoq["sales"]
    assert qoq["ebitda"]["growth_percent"] == 33.33, qoq["ebitda"]
    assert qoq["net_profit"]["growth_percent"] == 20.0, qoq["net_profit"]
    assert qoq["basic_eps"]["growth_percent"] == 20.0, qoq["basic_eps"]

    # Margin metrics (percentage points)
    assert qoq["opm"]["change"] == 2.0, qoq["opm"]
    assert qoq["net_profit_margin"]["change"] == -1.67, qoq["net_profit_margin"]

    # Metric coverage: Revenue/Sales, EBITDA, Net Profit, EPS, Margins
    for metric in ("sales", "ebitda", "net_profit",
                   "basic_eps", "opm", "net_profit_margin"):
        assert metric in qoq, f"{metric} missing from QoQ"

    print("  OK -> QoQ uses consecutive valid quarters")
    db.close()

    # ========== 2. VALID YOY COMPARISON ==========
    print("== 2. VALID YoY COMPARISON ==")
    db = make_db()
    seed(db, full_quarters())
    analysis = FinancialAnalysisService(db).compare_latest_results("ABC")

    yoy = analysis["yoy"]

    assert analysis["yoy_seq"] == "105", analysis
    assert analysis["periods"]["yoy"]["from"] == "01-Jan-2025"

    assert yoy["sales"]["growth_percent"] == 14.29, yoy["sales"]
    assert yoy["net_profit"]["growth_percent"] == 9.09, yoy["net_profit"]
    assert yoy["basic_eps"]["growth_percent"] == 9.09, yoy["basic_eps"]
    assert yoy["ebitda"]["growth_percent"] == 20.0, yoy["ebitda"]
    assert yoy["opm"]["change"] == 1.0, yoy["opm"]

    print("  OK -> YoY uses same quarter previous year")
    db.close()

    # ========== 3. MISSING QUARTER ==========
    print("== 3. MISSING QUARTER ==")
    db = make_db()
    # Remove Q3 FY26 -> Q4 FY26 has no adjacent previous quarter.
    seed(db, [f for f in full_quarters() if f["seq_Id"] != "102"])
    analysis = FinancialAnalysisService(db).compare_latest_results("ABC")

    assert analysis["qoq"] == {}, analysis["qoq"]
    assert analysis["yoy"] != {}, analysis["yoy"]

    print("  OK -> gap prevents mismatched QoQ; YoY still valid")

    # Insufficient quarters (only one filing)
    db = make_db()
    seed(db, [full_quarters()[0]])
    analysis = FinancialAnalysisService(db).compare_latest_results("ABC")
    assert analysis["qoq"] == {} and analysis["yoy"] == {}
    assert "message" in analysis
    print("  OK -> <2 quarters returns graceful empty result")
    db.close()

    # ========== 4. MISSING METRIC ==========
    print("== 4. MISSING METRIC ==")
    db = make_db()
    filings = full_quarters()
    prev = next(f for f in filings if f["seq_Id"] == "102")
    prev["financial_data"] = {
        k: v for k, v in prev["financial_data"].items()
        if k != "ebitda"
    }
    seed(db, filings)
    analysis = FinancialAnalysisService(db).compare_latest_results("ABC")

    assert "ebitda" not in analysis["qoq"]
    assert "sales" in analysis["qoq"]
    assert "net_profit" in analysis["qoq"]
    assert analysis["qoq"]["sales"]["growth_percent"] == 33.33

    print("  OK -> missing metric skipped, others compared")
    db.close()

    # ========== 5. ZERO PREVIOUS VALUE ==========
    print("== 5. ZERO PREVIOUS VALUE ==")
    db = make_db()
    filings = full_quarters()
    next(f for f in filings if f["seq_Id"] == "102")["financial_data"]["net_profit"] = 0
    seed(db, filings)
    analysis = FinancialAnalysisService(db).compare_latest_results("ABC")

    assert analysis["qoq"]["net_profit"]["latest"] == 60.0
    assert analysis["qoq"]["net_profit"]["previous"] == 0.0
    assert analysis["qoq"]["net_profit"]["growth_percent"] is None
    assert "sales" in analysis["qoq"]

    print("  OK -> zero previous value never divides by zero")

    # Non-numeric previous value
    db = make_db()
    filings = full_quarters()
    next(f for f in filings if f["seq_Id"] == "102")["financial_data"]["sales"] = "not-a-number"
    seed(db, filings)
    analysis = FinancialAnalysisService(db).compare_latest_results("ABC")
    assert "sales" not in analysis["qoq"]
    assert "net_profit" in analysis["qoq"]
    print("  OK -> non-numeric value skipped safely")
    db.close()

    # ========== 6. INVALID DATES ==========
    print("== 6. INVALID DATES ==")
    db = make_db()
    seed(db, full_quarters())
    latest_row = (
        db.query(FinancialResult)
        .filter(FinancialResult.seq_number == "101")
        .first()
    )
    latest_row.raw_data = {
        **latest_row.raw_data,
        "fromDate": "invalid-date",
        "toDate": "2026-99-31",
        "qe_Date": None,
        "period": None,
    }
    db.commit()

    analysis = FinancialAnalysisService(db).compare_latest_results("ABC")

    # Corrupt latest quarter excluded -> Q3 FY26 becomes latest.
    assert analysis["latest_seq"] == "102", analysis
    assert analysis["qoq"] != {}, analysis["qoq"]
    assert analysis["yoy"] == {}, analysis["yoy"]

    print("  OK -> invalid reporting periods excluded")
    db.close()

    # ========== 7. MULTIPLE COMPANIES ==========
    print("== 7. MULTIPLE COMPANIES ==")
    db = make_db()
    seed(db, full_quarters() + [
        filing("ZZZ", "31-MAR-2026", 901, {
            "sales": 100, "net_profit": 10, "opm": 10.0,
        }),
    ])
    service = FinancialAnalysisService(db)

    a = service.compare_latest_results("ABC")
    z = service.compare_latest_results("ZZZ")

    assert a["symbol"] == "ABC" and a["qoq"] != {} and a["yoy"] != {}
    assert z["symbol"] == "ZZZ" and z["qoq"] == {} and z["yoy"] == {}
    assert a["qoq"]["sales"]["latest"] == 400.0
    assert z["latest"] == {}  # insufficient data -> graceful empty result

    print("  OK -> companies compared independently")
    db.close()

    print("\nALL STEP 7 CHECKS PASSED")


if __name__ == "__main__":
    main()