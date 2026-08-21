from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.financial_results import FinancialResult
from app.repositories.financial_result_repository import (
    FinancialResultRepository,
)
from app.schemas.ai_analysis import LLMAnalysisResult
from app.services.nse_service import NseService
from app.services.pipeline_service import PipelineService
from app.services.vector_service import stable_point_id


def filing(symbol, qe_date, seq, financial_data=None):
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
        "financial_data": financial_data,
    }


def equity_record(symbol):
    return {
        "symbol": symbol,
        "company_name": symbol + " Limited",
        "series": "EQ",
        "isin": "IN0000000000",
    }


class FakeNseService(NseService):
    """Offline NSE stand-in: real logic, canned data."""

    def __init__(self, companies, filings):
        self._companies = companies
        self._filings = filings
        self.get_all_calls = 0
        self.page_calls = 0

    def get_equity_master(self):
        return self._companies

    def get_all_integrated_filings(self, index="equities", size=100, max_pages=50):
        self.get_all_calls += 1
        return self._filings

    def get_integrated_financial_results(self, index="equities", page=1, size=100):
        self.page_calls += 1
        start = (page - 1) * size
        return {"data": self._filings[start:start + size]}

    def get_market_cap(self, symbol: str):
        # Deterministic mock market cap for tests
        return f"₹10,000 Cr ({symbol})"


class FakeAIService:
    """Mocked LLM: canned structured analysis, optional per-symbol failure."""

    def __init__(self, response="MOCKED LLM ANALYSIS TEXT", valid=True, score=78,
                 fail_symbols=None):
        self.response = response
        self.valid = valid
        self.score = score
        self.fail_symbols = set(fail_symbols or [])
        self.calls = []
        self.last_contract = None

    def analyze_structured(self, contract):
        self.calls.append(contract.symbol)
        self.last_contract = contract

        if contract.symbol in self.fail_symbols:
            raise RuntimeError("mocked LLM failure")

        if not self.valid:
            return None

        return LLMAnalysisResult(
            summary=self.response,
            positive_factors=["Revenue grew"],
            negative_factors=["Margins declined"],
            growth_analysis=["Sales up"],
            margin_analysis=["OPM steady"],
            risk_factors=["Concentration risk"],
            company_score=self.score,
            score_explanation=f"Score {self.score} from mock",
        )


class FakeQdrantClient:
    """In-memory stand-in for the Qdrant client."""

    def __init__(self):
        self.collections = {}
        self.points = {}
        self.upserts = []

    def collection_exists(self, collection_name):
        return collection_name in self.collections

    def create_collection(self, collection_name, vectors_config=None):
        self.collections[collection_name] = vectors_config
        self.points.setdefault(collection_name, {})

    def upsert(self, collection_name, points):
        self.upserts.append((collection_name, points))
        store = self.points.setdefault(collection_name, {})
        for point in points:
            store[point.id] = {
                "vector": point.vector,
                "payload": point.payload,
            }


class FakeTelegramService:
    """Mocked Telegram service: records calls, optional failure."""

    def __init__(self):
        self.calls = []
        self.fail = False

    def send_analysis_notification(
        self, symbol, analysis=None, structured_analysis=None, score=None,
        company_name=None, market_cap=None,
    ):
        self.calls.append(symbol)

        if self.fail:
            raise RuntimeError("mocked Telegram failure")

        return {"status": "sent", "symbol": symbol}


def full_quarters():
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


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def make_pipeline(db, nse, ai, qdrant, telegram=None):
    return PipelineService(
        db,
        nse_service=nse,
        ai_service=ai,
        vector_client=qdrant,
        telegram_service=telegram or FakeTelegramService(),
    )


def test_complete_flow():
    print("== 1. COMPLETE PIPELINE FLOW ==")

    db = make_db()
    nse = FakeNseService([equity_record("ABC")], full_quarters())
    ai = FakeAIService()
    qdrant = FakeQdrantClient()

    pipeline = make_pipeline(db, nse, ai, qdrant)
    summary = pipeline.run(max_pages=50)

    assert summary["success"] is True, summary
    assert summary["companies_success"] == 1, summary
    assert summary["companies_failed"] == 0, summary

    assert summary["stages"]["sync_companies"]["new"] == 1
    assert summary["stages"]["discover_filings"]["fetched"] == 5
    assert summary["stages"]["store_filings"]["created"] == 5
    assert summary["stages"]["extract_financial_data"]["updated"] == 0

    company = summary["companies"][0]
    assert company["symbol"] == "ABC"
    assert company["status"] == "ok"
    assert company["score"] == 78
    assert company["llm_analysis_valid"] is True
    assert company["persisted_id"] is not None

    assert db.query(Company).filter_by(symbol="ABC").count() == 1
    assert db.query(FinancialResult).count() == 5
    assert db.query(AnalysisResult).filter_by(symbol="ABC").count() == 1

    analysis_row = db.query(AnalysisResult).filter_by(symbol="ABC").one()
    assert analysis_row.score == 78

    assert ai.calls == ["ABC"]
    assert len(qdrant.points["company_analyses"]) == 1
    payload = qdrant.points["company_analyses"][stable_point_id("ABC")]["payload"]
    assert payload["symbol"] == "ABC"
    assert payload["company_score"] == 78

    # Feed fetched once; backfill reused it instead of re-paginating.
    assert nse.get_all_calls == 1, nse.get_all_calls
    assert nse.page_calls == 0, nse.page_calls

    print("PASS: full pipeline completed, LLM called once, "
          "analysis persisted, vector stored")


def test_idempotent_execution():
    print("== 2. REPEATED / IDEMPOTENT EXECUTION ==")

    db = make_db()
    nse = FakeNseService([equity_record("ABC")], full_quarters())
    ai = FakeAIService()
    qdrant = FakeQdrantClient()

    first = make_pipeline(db, nse, ai, qdrant).run(max_pages=50)
    second = make_pipeline(db, nse, ai, qdrant).run(max_pages=50)

    assert first["success"] is True
    assert second["success"] is True

    assert second["stages"]["store_filings"]["created"] == 0
    assert second["stages"]["store_filings"]["existing"] == 5

    assert db.query(Company).filter_by(symbol="ABC").count() == 1
    assert db.query(FinancialResult).count() == 5
    assert db.query(AnalysisResult).filter_by(symbol="ABC").count() == 1
    assert len(qdrant.points["company_analyses"]) == 1

    # Each scheduler cycle fetched the feed once; backfill re-paginated
    # neither cycle, and no duplicate quarters/rows were created.
    assert nse.get_all_calls == 2, nse.get_all_calls
    assert nse.page_calls == 0, nse.page_calls

    print("PASS: second run produced no duplicate rows or vectors")


def test_individual_stage_failure():
    print("== 3. INDIVIDUAL COMPANY FAILURE DOES NOT STOP PIPELINE ==")

    db = make_db()
    filings = full_quarters() + [
        filing("BAD", "31-MAR-2026", 201, {
            "sales": 100, "ebitda": 30, "net_profit": 10,
            "basic_eps": 1.0, "opm": 10.0, "net_profit_margin": 10.0,
        }),
        filing("BAD", "31-DEC-2025", 202, {
            "sales": 90, "ebitda": 25, "net_profit": 9,
            "basic_eps": 0.9, "opm": 9.0, "net_profit_margin": 10.0,
        }),
        filing("BAD", "30-SEP-2025", 203, {
            "sales": 95, "ebitda": 28, "net_profit": 8,
            "basic_eps": 0.8, "opm": 10.0, "net_profit_margin": 8.4,
        }),
        filing("BAD", "30-JUN-2025", 204, {
            "sales": 80, "ebitda": 22, "net_profit": 7,
            "basic_eps": 0.7, "opm": 9.0, "net_profit_margin": 8.75,
        }),
    ]
    nse = FakeNseService(
        [equity_record("ABC"), equity_record("BAD")],
        filings,
    )
    ai = FakeAIService(fail_symbols={"BAD"})
    qdrant = FakeQdrantClient()

    pipeline = make_pipeline(db, nse, ai, qdrant)
    summary = pipeline.run(max_pages=50)

    assert summary["success"] is True
    assert summary["companies_success"] == 1
    assert summary["companies_failed"] == 1

    statuses = {c["symbol"]: c["status"] for c in summary["companies"]}
    assert statuses["BAD"] == "failed"
    assert statuses["ABC"] == "ok"

    print("PASS: failing company did not stop ABC from completing")


def test_insufficient_quarterly_data():
    print("== 4. INSUFFICIENT QUARTERLY DATA ==")

    db = make_db()
    nse = FakeNseService(
        [equity_record("LOW")],
        [filing("LOW", "31-MAR-2026", 301, {
            "sales": 100, "ebitda": 30, "net_profit": 10,
            "basic_eps": 1.0, "opm": 10.0, "net_profit_margin": 10.0,
        })],
    )
    ai = FakeAIService()
    qdrant = FakeQdrantClient()

    pipeline = make_pipeline(db, nse, ai, qdrant)
    summary = pipeline.run(max_pages=50)

    assert summary["success"] is True
    assert summary["companies_insufficient"] == 1
    assert summary["companies_success"] == 0

    company = summary["companies"][0]
    assert company["status"] == "insufficient_quarters"
    assert company["quarter_count"] == 1

    assert ai.calls == []
    assert len(qdrant.points.get("company_analyses", {})) == 0

    print("PASS: company with one quarter skipped without LLM or vector call")


def test_feed_fetched_once_multiple_companies():
    print("== 5. FEED FETCHED ONCE, REUSED ACROSS COMPANIES ==")

    db = make_db()
    filings = full_quarters() + [
        # DEF has only 2 quarters in the feed -> insufficient.
        filing("DEF", "31-MAR-2026", 301, {
            "sales": 100, "ebitda": 30, "net_profit": 10,
            "basic_eps": 1.0, "opm": 10.0, "net_profit_margin": 10.0,
        }),
        filing("DEF", "31-DEC-2025", 302, {
            "sales": 90, "ebitda": 25, "net_profit": 9,
            "basic_eps": 0.9, "opm": 9.0, "net_profit_margin": 10.0,
        }),
    ]
    nse = FakeNseService(
        [equity_record("ABC"), equity_record("DEF")],
        filings,
    )
    ai = FakeAIService()
    qdrant = FakeQdrantClient()

    pipeline = make_pipeline(db, nse, ai, qdrant)
    summary = pipeline.run(max_pages=50)

    assert summary["companies_success"] == 1
    assert summary["companies_insufficient"] == 1

    statuses = {c["symbol"]: c["status"] for c in summary["companies"]}
    assert statuses["ABC"] == "ok"
    assert statuses["DEF"] == "insufficient_quarters"

    # One feed fetch for the whole run; no per-company NSE pagination.
    assert nse.get_all_calls == 1, nse.get_all_calls
    assert nse.page_calls == 0, nse.page_calls

    print("PASS: one feed fetch served every company's backfill")


def test_mocked_llm_and_qdrant():
    print("== 6. MOCKED LLM + MOCKED QDRANT STORAGE ==")

    db = make_db()
    nse = FakeNseService([equity_record("ABC")], full_quarters())
    ai = FakeAIService(valid=False, score=40)
    qdrant = FakeQdrantClient()

    pipeline = make_pipeline(db, nse, ai, qdrant)
    summary = pipeline.run(max_pages=50)

    assert summary["success"] is True
    company = summary["companies"][0]
    assert company["status"] == "ok"

    # Invalid LLM response -> rule-based fallback score, no vector skip.
    assert company["llm_analysis_valid"] is False
    assert company["score"] is not None

    print("PASS: invalid LLM handled with fallback; "
          "no live LLM or Qdrant was contacted")


def test_legacy_rows_count_toward_quarters():
    print("== 7. LEGACY ROWS (qe_Date, no dates) COUNT AS QUARTERS ==")

    db = make_db()

    valid = [
        filing("LEG", "31-MAR-2026", 501, {
            "sales": 400, "ebitda": 120, "net_profit": 60,
            "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0,
        }),
        filing("LEG", "31-DEC-2025", 502, {
            "sales": 300, "ebitda": 90, "net_profit": 50,
            "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67,
        }),
        filing("LEG", "30-SEP-2025", 503, {
            "sales": 320, "ebitda": 100, "net_profit": 40,
            "basic_eps": 4.0, "opm": 21.0, "net_profit_margin": 12.5,
        }),
    ]

    repo = FinancialResultRepository(db)
    for f in valid:
        repo.create(f)

    # 4th quarter stored as a legacy row: qe_Date only, no from/to dates.
    legacy = {
        "seq_Id": "999999",
        "symbol": "LEG",
        "cmName": "LEG Limited",
        "creation_Date": "10-Aug-2026 12:00:00",
        "qe_Date": "30-JUN-2026",
        "audited": "Audited",
        "consolidated": "Consolidated",
        "xbrl": None,
        "financial_data": {
            "sales": 450, "ebitda": 130, "net_profit": 70,
            "basic_eps": 7.0, "opm": 23.0, "net_profit_margin": 15.5,
        },
    }
    db.add(FinancialResult(
        seq_number="999999",
        symbol="LEG",
        company_name="LEG Limited",
        period=None,
        raw_data=legacy,
        financial_data=legacy["financial_data"],
    ))
    db.commit()

    # Feed returns the legacy quarter under the SAME seq (no new insert).
    feed = valid + [filing("LEG", "30-JUN-2026", "999999", {
        "sales": 450, "ebitda": 130, "net_profit": 70,
        "basic_eps": 7.0, "opm": 23.0, "net_profit_margin": 15.5,
    })]

    nse = FakeNseService([equity_record("LEG")], feed)
    ai = FakeAIService()
    qdrant = FakeQdrantClient()

    pipeline = make_pipeline(db, nse, ai, qdrant)
    summary = pipeline.run(max_pages=50)

    assert summary["companies_success"] == 1, summary
    company = summary["companies"][0]
    assert company["status"] == "ok", company
    assert company["quarter_count"] == 4, company
    assert ai.calls == ["LEG"], ai.calls
    assert len(qdrant.points["company_analyses"]) == 1

    print("PASS: legacy 4th quarter counted; company reached analysis")


def test_telegram_after_success_and_non_fatal():
    print("== 8. TELEGRAM NOTIFICATION (after success, non-fatal) ==")

    db = make_db()
    nse = FakeNseService([equity_record("ABC")], full_quarters())
    ai = FakeAIService()
    qdrant = FakeQdrantClient()
    telegram = FakeTelegramService()

    summary = make_pipeline(
        db, nse, ai, qdrant, telegram=telegram
    ).run(max_pages=50)

    company = summary["companies"][0]
    assert company["status"] == "ok", company
    assert company["telegram_status"] == "sent", company
    assert telegram.calls == ["ABC"], telegram.calls

    print("  OK -> notification sent after successful analysis")

    db = make_db()
    nse = FakeNseService([equity_record("ABC")], full_quarters())
    ai = FakeAIService()
    qdrant = FakeQdrantClient()
    telegram = FakeTelegramService()
    telegram.fail = True

    summary = make_pipeline(
        db, nse, ai, qdrant, telegram=telegram
    ).run(max_pages=50)

    company = summary["companies"][0]
    assert company["status"] == "ok", company
    assert company["telegram_status"] == "failed", company
    assert summary["companies_success"] == 1, summary

    print("  OK -> Telegram failure never marks the company failed")


def main():
    test_complete_flow()
    test_idempotent_execution()
    test_individual_stage_failure()
    test_insufficient_quarterly_data()
    test_feed_fetched_once_multiple_companies()
    test_mocked_llm_and_qdrant()
    test_legacy_rows_count_toward_quarters()
    test_telegram_after_success_and_non_fatal()
    print("\nALL PIPELINE TESTS PASSED")


if __name__ == "__main__":
    main()