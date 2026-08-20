from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.models.analysis_result import AnalysisResult
from app.repositories.analysis_result_repository import AnalysisResultRepository
from app.repositories.financial_result_repository import FinancialResultRepository
from app.schemas.ai_analysis import LLMAnalysisResult
from app.workflows.analysis_workflow import AnalysisWorkflow


class FakeAIService:
    """
    Mocked LLM: returns a canned structured analysis.
    """

    def __init__(self, response="MOCKED LLM ANALYSIS TEXT", valid=True, score=78):
        self.response = response
        self.valid = valid
        self.score = score
        self.calls = 0
        self.last_contract = None

    def analyze_structured(self, contract):
        self.calls += 1
        self.last_contract = contract

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

    # ========== 1. VALID DATA -> FULL WORKFLOW ==========
    print("== 1. VALID DATA -> FULL WORKFLOW ==")
    db = make_db()
    seed(db, full_quarters())

    fake_ai = FakeAIService()
    workflow = AnalysisWorkflow(db, ai_service=fake_ai)

    result = workflow.run("ABC")

    assert result["status"] == "completed", result
    assert result["llm_analysis_valid"] is True
    assert result["structured_analysis"]["company_score"] == 78
    assert result["score"] == 78
    assert result["score_explanation"] == "Score 78 from mock"
    assert result["llm_analysis"] is not None
    assert fake_ai.calls == 1, f"LLM called {fake_ai.calls} times"
    assert fake_ai.last_contract is not None
    assert fake_ai.last_contract.symbol == "ABC"

    row = AnalysisResultRepository(db).get_by_symbol("ABC")
    assert row is not None
    assert row.status == "completed"
    assert row.score == 78
    assert "MOCKED LLM ANALYSIS TEXT" in row.llm_analysis
    assert "company_score" in row.llm_analysis
    assert row.contract_data["symbol"] == "ABC"
    assert result["persisted_id"] == row.id

    print("  OK -> completed run, LLM called once, structured result persisted")
    db.close()

    # ========== 2. MISSING DATA -> CONDITIONAL ROUTING ==========
    print("== 2. MISSING DATA -> CONDITIONAL ROUTING ==")
    db = make_db()

    fake_ai = FakeAIService()
    workflow = AnalysisWorkflow(db, ai_service=fake_ai)

    result = workflow.run("NODATA")

    assert result["status"] == "insufficient_data", result
    assert result["llm_analysis"] is None
    assert result["score"] is None
    assert fake_ai.calls == 0, "LLM must not be called for missing data"

    row = AnalysisResultRepository(db).get_by_symbol("NODATA")
    assert row is not None
    assert row.status == "insufficient_data"
    assert row.llm_analysis is None
    assert row.score is None
    assert row.error is not None
    assert "Not enough" in row.error

    print("  OK -> missing data routed to insufficient handler, LLM skipped")
    db.close()

    # ========== 3. INCOMPLETE DATA -> CONDITIONAL ROUTING ==========
    print("== 3. INCOMPLETE DATA (single filing) -> CONDITIONAL ROUTING ==")
    db = make_db()
    seed(db, [full_quarters()[0]])

    fake_ai = FakeAIService()
    workflow = AnalysisWorkflow(db, ai_service=fake_ai)

    result = workflow.run("ABC")

    assert result["status"] == "insufficient_data", result
    assert fake_ai.calls == 0

    row = AnalysisResultRepository(db).get_by_symbol("ABC")
    assert row.status == "insufficient_data"

    print("  OK -> incomplete data also skipped safely")
    db.close()

    # ========== 4. RE-RUN OVERWRITES (upsert) ==========
    print("== 4. RE-RUN OVERWRITES (upsert) ==")
    db = make_db()
    seed(db, full_quarters())

    workflow = AnalysisWorkflow(db, ai_service=FakeAIService("first"))
    first = workflow.run("ABC")

    workflow2 = AnalysisWorkflow(db, ai_service=FakeAIService("second"))
    second = workflow2.run("ABC")

    rows = db.query(AnalysisResult).filter_by(symbol="ABC").all()
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    assert first["persisted_id"] == second["persisted_id"]
    assert "second" in rows[0].llm_analysis

    print("  OK -> re-run updates the single row per company")
    db.close()

    # ========== 5. INVALID LLM RESPONSE -> SCORE FALLBACK ==========
    print("== 5. INVALID LLM RESPONSE -> SCORE FALLBACK ==")
    db = make_db()
    seed(db, full_quarters())

    fake_ai = FakeAIService(valid=False)  # simulate malformed LLM output
    workflow = AnalysisWorkflow(db, ai_service=fake_ai)

    result = workflow.run("ABC")

    assert result["status"] == "completed", result
    assert result["llm_analysis_valid"] is False
    assert result["structured_analysis"] is None
    assert isinstance(result["score"], int)
    assert 0 <= result["score"] <= 100, result["score"]
    assert result["score_explanation"], result
    assert fake_ai.calls == 1  # LLM was attempted once

    row = AnalysisResultRepository(db).get_by_symbol("ABC")
    assert row.status == "completed"
    assert row.score == result["score"]
    assert row.llm_analysis is None

    print("  OK -> invalid LLM response falls back to rule-based score")
    db.close()

    # ========== 6. GRAPH STRUCTURE ==========
    print("== 6. GRAPH STRUCTURE ==")
    db = make_db()
    workflow = AnalysisWorkflow(db, ai_service=FakeAIService())

    nodes = set(workflow.graph.get_graph().nodes.keys())
    expected = {
        "load_financial_data",
        "build_contract",
        "generate_llm_analysis",
        "generate_company_score",
        "persist_analysis_result",
        "handle_insufficient_data",
    }
    assert expected.issubset(nodes), nodes
    assert "__start__" in nodes and "__end__" in nodes

    print("  OK -> all required stages present")
    db.close()

    print("\nALL STEP 9 CHECKS PASSED")


if __name__ == "__main__":
    main()