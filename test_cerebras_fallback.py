import json
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.models.analysis_result import AnalysisResult
from app.repositories.analysis_result_repository import AnalysisResultRepository
from app.repositories.financial_result_repository import FinancialResultRepository
from app.schemas.ai_analysis import LLMAnalysisResult
from app.schemas.financial_analysis import Completeness, FinancialAnalysisContract, MetricSnapshot
from app.services.ai_analysis_service import AIAnalysisService
from app.workflows.analysis_workflow import AnalysisWorkflow


# Helpers

class FakeRateLimitError(Exception):
    def __init__(self, msg="429 Too Many Requests: rate limit exceeded"):
        super().__init__(msg)
        self.status_code = 429

class FakeAuthError(Exception):
    def __init__(self, msg="401 Unauthorized: invalid api key"):
        super().__init__(msg)
        self.status_code = 401

class FakeLLM:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = 0
        self.last_prompt = None
    def invoke(self, prompt):
        self.calls += 1
        self.last_prompt = prompt
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.content)

def make_contract(symbol="ABC"):
    return FinancialAnalysisContract(
        symbol=symbol,
        latest=MetricSnapshot(sales=400, ebitda=120, net_profit=60, basic_eps=6, opm=22, net_profit_margin=15),
        qoq={}, yoy={},
        completeness=Completeness(has_latest=True, missing_metrics=[]),
    )

VALID_PAYLOAD = {
    "summary": "Strong quarter",
    "positive_factors": ["Revenue up"],
    "negative_factors": [],
    "growth_analysis": ["Sales up"],
    "margin_analysis": ["OPM up"],
    "risk_factors": ["None"],
    "company_score": 80,
    "score_explanation": "Good",
}

def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()

def filing(symbol, qe_date, seq, fd):
    return {"seq_Id": str(seq), "symbol": symbol, "cmName": symbol+" Ltd", "creation_Date": "10-Aug-2026 12:00:00", "qe_Date": qe_date, "audited": "Yes", "consolidated": "No", "xbrl": None, "financial_data": fd}

def seed(db, filings):
    repo = FinancialResultRepository(db)
    for f in filings:
        repo.create(f)

def full_quarters():
    return [
        filing("ABC", "31-MAR-2026", 101, {"sales":400,"ebitda":120,"net_profit":60,"basic_eps":6,"opm":22,"net_profit_margin":15}),
        filing("ABC", "31-DEC-2025", 102, {"sales":300,"ebitda":90,"net_profit":50,"basic_eps":5,"opm":20,"net_profit_margin":16}),
        filing("ABC", "30-SEP-2025", 103, {"sales":320,"ebitda":100,"net_profit":40,"basic_eps":4,"opm":21,"net_profit_margin":12}),
        filing("ABC", "30-JUN-2025", 104, {"sales":280,"ebitda":85,"net_profit":45,"basic_eps":4.5,"opm":19,"net_profit_margin":16}),
        filing("ABC", "31-MAR-2025", 105, {"sales":350,"ebitda":100,"net_profit":55,"basic_eps":5.5,"opm":21,"net_profit_margin":15}),
    ]

def main():
    # ========== 1. Groq success -> Cerebras not called ==========
    print("== 1. Groq success -> Cerebras not called ==")
    groq = FakeLLM(content=json.dumps(VALID_PAYLOAD))
    cerebras = FakeLLM(content=json.dumps(VALID_PAYLOAD))
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    result = svc.analyze_structured(make_contract())
    assert isinstance(result, LLMAnalysisResult)
    assert svc.last_provider_used == "groq"
    assert groq.calls == 1
    assert cerebras.calls == 0
    print("  OK")

    # ========== 2. Groq 429 -> Cerebras succeeds ==========
    print("== 2. Groq 429 -> Cerebras succeeds ==")
    groq = FakeLLM(error=FakeRateLimitError())
    cerebras = FakeLLM(content=json.dumps(VALID_PAYLOAD))
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    result = svc.analyze_structured(make_contract("XYZ"))
    assert isinstance(result, LLMAnalysisResult)
    assert svc.last_provider_used == "cerebras"
    assert groq.calls == 1
    assert cerebras.calls == 1
    # Same prompt sent to both
    assert groq.last_prompt == cerebras.last_prompt
    print("  OK")

    # ========== 3. Groq 429 -> Cerebras also fails -> graceful rule-based fallback (still delivers QoQ/YoY) ==========
    print("== 3. Groq 429 -> Cerebras also fails -> fallback to rule-based ==")
    groq = FakeLLM(error=FakeRateLimitError())
    cerebras = FakeLLM(error=FakeRateLimitError("Cerebras 429"))
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    result = svc.analyze_structured(make_contract())
    assert result is None, "both rate-limited should return None for rule-based fallback"
    assert groq.calls == 1
    assert cerebras.calls == 1
    print("  OK -> both rate-limited, returns None for rule-based fallback (no retry)")

    # Verify workflow completes with rule-based score when both providers rate-limited (QoQ/YoY still delivered)
    db = make_db()
    seed(db, full_quarters())
    groq = FakeLLM(error=FakeRateLimitError())
    cerebras = FakeLLM(error=FakeRateLimitError())
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    wf = AnalysisWorkflow(db, ai_service=svc)
    result = wf.run("ABC")
    assert result["status"] == "completed", result
    assert result["llm_analysis_valid"] is False
    assert result["structured_analysis"] is None
    assert isinstance(result["score"], int)
    print("  OK -> workflow completes with rule-based score, will still persist/Qdrant/Telegram")
    row = AnalysisResultRepository(db).get_by_symbol("ABC")
    assert row is not None and row.status == "completed"
    db.close()

    # ========== 4. Groq auth error -> no fallback ==========
    print("== 4. Groq auth error -> no fallback ==")
    groq = FakeLLM(error=FakeAuthError())
    cerebras = FakeLLM(content=json.dumps(VALID_PAYLOAD))
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    try:
        result = svc.analyze_structured(make_contract())
        assert False, "should have raised auth error"
    except Exception as e:
        assert "401" in str(e) or "auth" in str(e).lower()
        assert groq.calls == 1
        assert cerebras.calls == 0
        print("  OK -> auth error not falling back")

    # ========== 5. Cerebras structured output validation ==========
    print("== 5. Cerebras structured output validation ==")
    # Groq 429, Cerebras returns invalid JSON -> graceful fallback to rule-based (returns None)
    groq = FakeLLM(error=FakeRateLimitError())
    cerebras = FakeLLM(content="not json")
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    result = svc.analyze_structured(make_contract())
    assert result is None
    assert cerebras.calls == 1
    print("  OK -> Cerebras invalid JSON returns None for rule-based fallback")

    # Cerebras returns valid JSON -> passes validation
    groq = FakeLLM(error=FakeRateLimitError())
    cerebras = FakeLLM(content=json.dumps(VALID_PAYLOAD))
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    result = svc.analyze_structured(make_contract())
    assert result.company_score == 80
    print("  OK -> Cerebras valid payload passes Pydantic")

    # ========== 6. provider_used recorded correctly ==========
    print("== 6. provider_used recorded correctly ==")
    db = make_db()
    seed(db, full_quarters())
    groq = FakeLLM(content=json.dumps(VALID_PAYLOAD))
    cerebras = FakeLLM(content=json.dumps(VALID_PAYLOAD))
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    wf = AnalysisWorkflow(db, ai_service=svc)
    result = wf.run("ABC")
    row = AnalysisResultRepository(db).get_by_symbol("ABC")
    assert row.provider_used == "groq", row.provider_used
    assert result["provider_used"] == "groq"
    print("  OK -> groq recorded")

    db = make_db()
    seed(db, full_quarters())
    groq = FakeLLM(error=FakeRateLimitError())
    cerebras = FakeLLM(content=json.dumps(VALID_PAYLOAD))
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    wf = AnalysisWorkflow(db, ai_service=svc)
    result = wf.run("ABC")
    row = AnalysisResultRepository(db).get_by_symbol("ABC")
    assert row.provider_used == "cerebras", row.provider_used
    assert result["provider_used"] == "cerebras"
    print("  OK -> cerebras recorded")
    db.close()

    # ========== 7. Do not repeatedly retry exhausted Groq quota ==========
    print("== 7. No repeated Groq retry ==")
    groq = FakeLLM(error=FakeRateLimitError())
    cerebras = FakeLLM(content=json.dumps(VALID_PAYLOAD))
    svc = AIAnalysisService(llm=groq, cerebras_llm=cerebras)
    svc.analyze_structured(make_contract())
    assert groq.calls == 1, "Groq should be called exactly once"
    assert cerebras.calls == 1, "Cerebras should be called exactly once"
    print("  OK -> single fallback, no loop")

    print("\nALL CEREBRAS FALLBACK CHECKS PASSED")

if __name__ == "__main__":
    main()
