from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.repositories.financial_result_repository import FinancialResultRepository
from app.services.one_year_pipeline_service import OneYearPipelineService
from app.services.quarter_backfill_service import QuarterBackfillService


def filing(symbol, qe_date, seq):
    """Build an NSE-style integrated filing record."""
    return {
        "seq_Id": str(seq),
        "symbol": symbol,
        "cmName": symbol + " Limited",
        "creation_Date": "10-Aug-2026 12:00:00",
        "qe_Date": qe_date,
        "audited": "Yes",
        "consolidated": "No",
        "xbrl": "http://example.com/x.xml",
    }


class FakeNseService:
    """Replaces NSE with canned paginated filings."""

    def __init__(self, records):
        self.records = records

    def get_integrated_financial_results(self, page=1, size=100):
        start = (page - 1) * size
        return {"data": self.records[start:start + size]}


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed(db, filings):
    repo = FinancialResultRepository(db)
    for f in filings:
        repo.create(f)


def main():

    # ========== 1. FEWER THAN 4 QUARTERS -> backfill to 4 ==========
    print("== 1. FEWER THAN 4 QUARTERS (successful backfill) ==")
    db = make_db()
    seed(db, [
        filing("ABC", "31-MAR-2026", 1),
        filing("ABC", "31-DEC-2025", 2),
    ])
    nse = FakeNseService([
        filing("ABC", "30-SEP-2025", 3),
        filing("ABC", "30-JUN-2025", 4),
        filing("ABC", "31-MAR-2025", 5),
    ])
    result = QuarterBackfillService(db, nse).ensure_minimum_quarters("ABC")
    assert result["quarter_count"] == 4, result
    assert result["eligible"] is True, result
    assert result["backfilled"] == 2, result
    print("  OK ->", result["quarter_count"], "quarters, eligible")
    db.close()

    # ========== 2. EXACTLY 4 QUARTERS ==========
    print("== 2. EXACTLY 4 QUARTERS ==")
    db = make_db()
    seed(db, [
        filing("ABC", "31-MAR-2026", 1),
        filing("ABC", "31-DEC-2025", 2),
        filing("ABC", "30-SEP-2025", 3),
        filing("ABC", "30-JUN-2025", 4),
    ])
    result = QuarterBackfillService(db, FakeNseService([])).ensure_minimum_quarters("ABC")
    assert result["quarter_count"] == 4 and result["eligible"] is True
    assert result["backfilled"] == 0, result
    print("  OK ->", result["quarter_count"], "quarters, no backfill needed")
    db.close()

    # ========== 3. MORE THAN 4 QUARTERS ==========
    print("== 3. MORE THAN 4 QUARTERS ==")
    db = make_db()
    seed(db, [
        filing("ABC", "31-MAR-2026", 1),
        filing("ABC", "31-DEC-2025", 2),
        filing("ABC", "30-SEP-2025", 3),
        filing("ABC", "30-JUN-2025", 4),
        filing("ABC", "31-MAR-2025", 5),
    ])
    result = QuarterBackfillService(db, FakeNseService([])).ensure_minimum_quarters("ABC")
    assert result["quarter_count"] == 5 and result["eligible"] is True
    assert result["backfilled"] == 0, result
    print("  OK ->", result["quarter_count"], "quarters, still eligible")
    db.close()

    # ========== 4. DUPLICATE QUARTER RECORDS ==========
    print("== 4. DUPLICATE QUARTER RECORDS ==")
    db = make_db()
    # Two different seq_Id filings for the SAME quarter.
    seed(db, [
        filing("ABC", "31-MAR-2026", 1),
        filing("ABC", "31-MAR-2026", 2),  # duplicate quarter, different seq
    ])
    repo = FinancialResultRepository(db)
    quarters = QuarterBackfillService(db, FakeNseService([]))._usable_quarters("ABC")
    assert len(quarters) == 1, f"duplicates counted: {quarters}"
    result = QuarterBackfillService(db, FakeNseService([
        filing("ABC", "31-DEC-2025", 3),
        filing("ABC", "30-SEP-2025", 4),
        filing("ABC", "30-JUN-2025", 5),
    ])).ensure_minimum_quarters("ABC")
    assert result["quarter_count"] == 4 and result["eligible"] is True
    assert result["backfilled"] == 3, result
    total_rows = db.query(__import__("app.models.financial_results", fromlist=["FinancialResult"]).FinancialResult).filter(
        __import__("app.models.financial_results", fromlist=["FinancialResult"]).FinancialResult.symbol == "ABC"
    ).count()
    assert total_rows == 5, f"unexpected rows: {total_rows}"
    print("  OK -> 4 distinct quarters, duplicate seq_Id avoided, rows:", total_rows)
    db.close()

    # ========== 5. INSUFFICIENT HISTORY AFTER BACKFILL ==========
    print("== 5. INSUFFICIENT HISTORY AFTER BACKFILL ==")
    db = make_db()
    seed(db, [
        filing("ABC", "31-MAR-2026", 1),
        filing("ABC", "31-DEC-2025", 2),
    ])
    nse = FakeNseService([
        filing("ABC", "30-SEP-2025", 3),  # only one more quarter available
        filing("OTHER", "30-JUN-2025", 4),
    ])
    result = QuarterBackfillService(db, nse).ensure_minimum_quarters("ABC")
    assert result["quarter_count"] == 3, result
    assert result["eligible"] is False, result
    assert result["backfilled"] == 1, result
    print("  OK ->", result["quarter_count"], "quarters, not eligible")
    db.close()

    # ========== 6. ELIGIBLE COMPANIES FROM NSE DATA ==========
    print("== 6. get_eligible_companies (>=4 usable quarters) ==")
    nse = FakeNseService([
        filing("AAA", "31-MAR-2026", 1),
        filing("AAA", "31-DEC-2025", 2),
        filing("AAA", "30-SEP-2025", 3),
        filing("AAA", "30-JUN-2025", 4),   # AAA: 4 distinct quarters
        filing("AAA", "30-JUN-2025", 99),  # duplicate quarter -> counted once
        filing("BBB", "31-MAR-2026", 10),
        filing("BBB", "31-DEC-2025", 11),  # BBB: only 2 quarters
        filing("CCC", "not-a-date", 20),   # invalid period -> skipped
    ])
    eligible = OneYearPipelineService(nse).get_eligible_companies()
    assert "AAA" in eligible, eligible
    assert "BBB" not in eligible, eligible
    assert "CCC" not in eligible, eligible
    print("  OK -> eligible:", list(eligible.keys()))

    # ========== 7. ensure_company_quarters via pipeline service ==========
    print("== 7. OneYearPipelineService.ensure_company_quarters ==")
    db = make_db()
    seed(db, [filing("XYZ", "31-MAR-2026", 1)])
    nse = FakeNseService([
        filing("XYZ", "31-DEC-2025", 2),
        filing("XYZ", "30-SEP-2025", 3),
        filing("XYZ", "30-JUN-2025", 4),
    ])
    result = OneYearPipelineService(nse, db).ensure_company_quarters("XYZ")
    assert result["eligible"] is True and result["quarter_count"] == 4
    assert result["backfilled"] == 3, result
    print("  OK ->", result["quarter_count"], "quarters after automatic backfill")
    db.close()

    print("\nALL STEP 6 CHECKS PASSED")


if __name__ == "__main__":
    main()