import json
from types import SimpleNamespace

from app.schemas.ai_analysis import LLMAnalysisResult
from app.schemas.financial_analysis import (
    Completeness,
    FinancialAnalysisContract,
    MetricComparison,
    MetricSnapshot,
)


class FakeLLM:
    """Mocked Groq LLM: returns a canned raw string response."""

    def __init__(self, content):
        self.content = content
        self.prompt = None

    def invoke(self, prompt):
        self.prompt = prompt
        return SimpleNamespace(content=self.content)


def make_contract():
    return FinancialAnalysisContract(
        symbol="ABC",
        latest=MetricSnapshot(
            sales=400.0,
            ebitda=120.0,
            net_profit=60.0,
            basic_eps=6.0,
            opm=22.0,
            net_profit_margin=15.0,
        ),
        qoq={
            "sales": MetricComparison(
                metric="sales", latest=400.0, previous=300.0,
                growth_percent=33.33,
            ),
            "opm": MetricComparison(
                metric="opm", latest=22.0, previous=20.0, change=2.0,
            ),
        },
        completeness=Completeness(has_latest=True, missing_metrics=[]),
    )


VALID_PAYLOAD = {
    "summary": "Strong quarter driven by revenue growth.",
    "positive_factors": ["Revenue grew 33% QoQ"],
    "negative_factors": [],
    "growth_analysis": ["Sales up 33.33% QoQ"],
    "margin_analysis": ["Operating margin improved 2 pp"],
    "risk_factors": ["Dependence on one segment"],
    "company_score": 78,
    "score_explanation": "Strong growth offset by concentration risk.",
}


def service_with(content):
    fake = FakeLLM(content)
    service = __import__(
        "app.services.ai_analysis_service",
        fromlist=["AIAnalysisService"],
    ).AIAnalysisService(llm=fake)
    return service, fake


def main():

    # ========== 1. VALID JSON -> PARSED + VALIDATED ==========
    print("== 1. VALID JSON ==")
    service, fake = service_with(json.dumps(VALID_PAYLOAD))

    result = service.analyze_structured(make_contract())

    assert isinstance(result, LLMAnalysisResult)
    assert result.summary == "Strong quarter driven by revenue growth."
    assert result.positive_factors == ["Revenue grew 33% QoQ"]
    assert result.company_score == 78
    assert result.score_explanation.startswith("Strong growth")
    assert len(result.risk_factors) == 1

    # The contract JSON must be embedded in the prompt
    assert '"symbol":"ABC"' in fake.prompt
    assert "growth_percent" in fake.prompt
    # The prompt forbids inventing facts
    assert "NEVER invent" in fake.prompt
    assert "ONLY on the data provided" in fake.prompt

    print("  OK -> valid response parsed and Pydantic-validated")
    service = None

    # ========== 2. JSON INSIDE MARKDOWN FENCES -> EXTRACTED ==========
    print("== 2. JSON WITH CODE FENCES ==")
    fenced = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
    service, _ = service_with(fenced)

    result = service.analyze_structured(make_contract())

    assert isinstance(result, LLMAnalysisResult)
    assert result.company_score == 78
    print("  OK -> markdown fences tolerated")

    # ========== 3. INVALID JSON -> SAFE None ==========
    print("== 3. INVALID JSON ==")
    service, _ = service_with("this is not json")

    assert service.analyze_structured(make_contract()) is None
    print("  OK -> malformed JSON returns None safely")

    # ========== 4. OUT-OF-RANGE SCORE -> SAFE None ==========
    print("== 4. OUT-OF-RANGE SCORE ==")
    payload = dict(VALID_PAYLOAD, company_score=150)
    service, _ = service_with(json.dumps(payload))

    assert service.analyze_structured(make_contract()) is None
    print("  OK -> out-of-range score rejected by Pydantic")

    # ========== 5. MISSING REQUIRED FIELD -> SAFE None ==========
    print("== 5. MISSING REQUIRED FIELD ==")
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "summary"}
    service, _ = service_with(json.dumps(payload))

    assert service.analyze_structured(make_contract()) is None
    print("  OK -> missing field rejected by Pydantic")

    # ========== 6. NON-DICT JSON -> SAFE None ==========
    print("== 6. NON-DICT JSON ==")
    service, _ = service_with("[1, 2, 3]")

    assert service.analyze_structured(make_contract()) is None
    print("  OK -> non-object JSON rejected by Pydantic")

    # ========== 7. EMPTY / NONE CONTENT -> SAFE None ==========
    print("== 7. EMPTY CONTENT ==")
    service, _ = service_with(None)
    assert service.analyze_structured(make_contract()) is None
    print("  OK -> empty content returns None safely")

    print("\nALL STEP 10 CHECKS PASSED")


if __name__ == "__main__":
    main()