import contextlib
import io

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.models.financial_results import FinancialResult
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
        self.page_calls = 0

    def get_integrated_financial_results(self, page=1, size=100):
        self.page_calls += 1
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


def insert_legacy(db, symbol, qe_date, seq):
    """
    Insert a legacy-style row that stores only the period-end date
    (qe_Date) and no fromDate/toDate in raw_data.
    """
    raw = {
        "seq_Id": str(seq),
        "symbol": symbol,
        "cmName": symbol + " Limited",
        "creation_Date": "10-Aug-2026 12:00:00",
        "qe_Date": qe_date,
        "audited": "Audited",
        "consolidated": "Consolidated",
        "xbrl": None,
    }
    row = FinancialResult(
        seq_number=str(seq),
        symbol=symbol,
        company_name=symbol + " Limited",
        period=None,
        raw_data=raw,
    )
    db.add(row)
    db.commit()
    return row


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

    # ========== 8. FEED REUSE (no NSE re-fetch per company) ==========
    print("== 8. prepared feed reused for backfill ==")
    db = make_db()
    seed(db, [
        filing("ABC", "31-MAR-2026", 1),
        filing("ABC", "31-DEC-2025", 2),
    ])
    nse = FakeNseService([])  # would expose re-fetching
    feed = [
        filing("ABC", "30-SEP-2025", 3),
        filing("ABC", "30-JUN-2025", 4),
        filing("OTHER", "31-MAR-2026", 90),
    ]
    service = QuarterBackfillService(db, nse, filing_records=feed)
    result = service.ensure_minimum_quarters("ABC")
    assert result["quarter_count"] == 4 and result["eligible"] is True
    assert result["backfilled"] == 2, result
    assert nse.page_calls == 0, f"feed re-fetched: {nse.page_calls}"
    print("  OK -> 4 quarters from the reused feed, 0 NSE page calls")
    db.close()

    # ========== 9. LEGACY ROW (qe_Date only) IS A USABLE QUARTER ==========
    print("== 9. legacy row with qe_Date but no from/to dates ==")
    db = make_db()
    insert_legacy(db, "LEG", "30-JUN-2026", 9001)
    quarters = QuarterBackfillService(
        db, FakeNseService([])
    )._usable_quarters("LEG")
    assert ("01-Apr-2026", "30-Jun-2026") in quarters, quarters
    assert len(quarters) == 1, quarters
    result = QuarterBackfillService(
        db, FakeNseService([])
    ).ensure_minimum_quarters("LEG")
    assert result["quarter_count"] == 1 and result["eligible"] is False
    print("  OK -> legacy row counted without modifying the database")
    db.close()

    # ========== 10. CONSOLIDATED + STANDALONE = ONE QUARTER ==========
    print("== 10. consolidated + standalone same quarter = one quarter ==")
    db = make_db()
    seed(db, [
        filing("DUO", "31-MAR-2026", 1001),
        filing("DUO", "31-MAR-2026", 1002),
    ])
    rows = FinancialResultRepository(db).get_company_quarters("DUO")
    assert len(rows) == 1, f"expected 1 quarter, got {len(rows)}"
    print("  OK -> duplicate filings for one period counted once")
    db.close()

    # ========== 11. EXISTING SEQ -> NO NEW QUARTER ==========
    print("== 11. existing seq produces no NEW QUARTER ==")
    db = make_db()
    insert_legacy(db, "REV", "30-JUN-2026", 1101)
    feed = [filing("REV", "30-JUN-2026", 1101)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = QuarterBackfillService(
            db, FakeNseService([]), filing_records=feed
        ).ensure_minimum_quarters("REV")
    out = buf.getvalue()
    assert result["quarter_count"] == 1, result
    assert "NEW QUARTER" not in out, out
    print("  OK -> no misleading NEW QUARTER for an already-stored filing")
    db.close()

    # ========== 12. GENUINELY NEW QUARTER -> PERSISTED ==========
    print("== 12. genuinely new quarter is persisted and counted ==")
    db = make_db()
    seed(db, [filing("NEW", "31-MAR-2026", 1201)])
    feed = [filing("NEW", "30-JUN-2026", 1202)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = QuarterBackfillService(
            db, FakeNseService([]), filing_records=feed
        ).ensure_minimum_quarters("NEW")
    out = buf.getvalue()
    assert result["quarter_count"] == 2, result
    assert "NEW QUARTER" in out, out
    print("  OK -> new quarter persisted and counted once")
    db.close()

    # ========== 13. SEQ EXISTS BUT NO-OP INSERT IS NOT PROGRESS ==========
    print("== 13. no-op insert (same seq) is not counted as progress ==")
    db = make_db()
    # Legacy row whose period cannot be derived at all.
    raw = {
        "seq_Id": "1301", "symbol": "NOP",
        "cmName": "NOP Limited", "creation_Date": "10-Aug-2026 12:00:00",
        "qe_Date": "not-a-date", "audited": "Audited",
        "consolidated": "Consolidated", "xbrl": None,
    }
    db.add(FinancialResult(
        seq_number="1301", symbol="NOP",
        company_name="NOP Limited", raw_data=raw,
    ))
    db.commit()
    feed = [filing("NOP", "30-JUN-2026", 1301)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = QuarterBackfillService(
            db, FakeNseService([]), filing_records=feed
        ).ensure_minimum_quarters("NOP")
    out = buf.getvalue()
    assert result["quarter_count"] == 0, result
    assert "NEW QUARTER" not in out, out
    print("  OK -> no-op insert never reported as a new quarter")
    db.close()

    print("\nALL STEP 6 CHECKS PASSED")


if __name__ == "__main__":
    main()