from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.analysis import get_vector_service, get_workflow
from app.database.database import get_db
from app.database.models import Base
from app.main import app
from app.repositories.financial_result_repository import (
    FinancialResultRepository
)


class FakeWorkflow:
    def __init__(self, state):
        self.state = state

    def run(self, symbol):
        return {**self.state, "symbol": symbol}


class FakeVectorService:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, query_text, limit):
        self.queries.append((query_text, limit))
        return self.results[:limit]


def filing(symbol, qe_date, seq, creation_date, financial_data):
    return {
        "seq_Id": str(seq),
        "symbol": symbol,
        "cmName": symbol + " Limited",
        "creation_Date": creation_date,
        "qe_Date": qe_date,
        "audited": "Yes",
        "consolidated": "No",
        "xbrl": "http://example.com/x.xml",
        "financial_data": financial_data,
    }


def full_quarters():
    return [
        filing("ABC", "31-MAR-2026", 101, "10-Aug-2026 12:00:00", {
            "sales": 400, "ebitda": 120, "net_profit": 60,
            "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0,
        }),
        filing("ABC", "31-DEC-2025", 102, "10-May-2026 12:00:00", {
            "sales": 300, "ebitda": 90, "net_profit": 50,
            "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67,
        }),
        filing("ABC", "30-SEP-2025", 103, "10-Feb-2026 12:00:00", {
            "sales": 320, "ebitda": 100, "net_profit": 40,
            "basic_eps": 4.0, "opm": 21.0, "net_profit_margin": 12.5,
        }),
        filing("ABC", "30-JUN-2025", 104, "10-Nov-2025 12:00:00", {
            "sales": 280, "ebitda": 85, "net_profit": 45,
            "basic_eps": 4.5, "opm": 19.0, "net_profit_margin": 16.07,
        }),
        filing("ABC", "31-MAR-2025", 105, "10-Aug-2025 12:00:00", {
            "sales": 350, "ebitda": 100, "net_profit": 55,
            "basic_eps": 5.5, "opm": 21.0, "net_profit_margin": 15.71,
        }),
    ]


def setup_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed(db, filings):
    repo = FinancialResultRepository(db)
    for f in filings:
        repo.create(f)


def with_db(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db


def clear_overrides():
    app.dependency_overrides.clear()


def main():

    # ========== 1. COMPANY INFORMATION (existing architecture) ==========
    print("== 1. COMPANY INFORMATION ==")
    db = setup_db()
    with_db(db)
    client = TestClient(app)
    try:
        resp = client.get("/companies")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

        resp = client.post("/companies", json={
            "symbol": "ABC",
            "company_name": "ABC Limited",
        })
        assert resp.status_code == 200, resp.text
        company_id = resp.json()["id"]
        assert resp.json()["symbol"] == "ABC"

        resp = client.get(f"/companies/{company_id}")
        assert resp.status_code == 200
        assert resp.json()["company_name"] == "ABC Limited"

        resp = client.get("/companies/999999")
        assert resp.status_code == 404
    finally:
        clear_overrides()
        db.close()
    print("  OK -> company info endpoints work on isolated data")

    # ========== 2. FINANCIAL RESULTS HISTORY ==========
    print("== 2. FINANCIAL RESULTS HISTORY ==")
    db = setup_db()
    seed(db, full_quarters())
    with_db(db)
    client = TestClient(app)
    try:
        resp = client.get("/companies/ABC/results")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 5
        seqs = {item["seq_number"] for item in data}
        assert seqs == {"101", "102", "103", "104", "105"}
        assert any(
            item["seq_number"] == "101"
            and item["financial_data"]["sales"] == 400
            for item in data
        )

        resp = client.get("/companies/XYZ/results")
        assert resp.status_code == 404, resp.text
    finally:
        clear_overrides()
        db.close()
    print("  OK -> results history lists filings, 404 when none")

    # ========== 3. QOQ / YOY COMPARISON ==========
    print("== 3. QOQ / YOY COMPARISON ==")
    db = setup_db()
    seed(db, full_quarters())
    with_db(db)
    client = TestClient(app)
    try:
        resp = client.get("/companies/ABC/comparison")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["symbol"] == "ABC"
        assert data["latest_seq"] == "101"
        assert data["qoq"]["sales"]["growth_percent"] == 33.33
        assert data["yoy"]["sales"]["growth_percent"] == 14.29
        assert data["qoq"]["opm"]["change"] == 2.0
        assert data["periods"]["latest"]["from_date"] == "01-Jan-2026"
        assert data["periods"]["previous"]["from_date"] == "01-Oct-2025"
        assert data["periods"]["yoy"]["from_date"] == "01-Jan-2025"

        resp = client.get("/companies/NODATA/comparison")
        assert resp.status_code == 404, resp.text

        resp = client.get("/companies//comparison")
        assert resp.status_code in (404, 400)  # invalid symbol
    finally:
        clear_overrides()
        db.close()
    print("  OK -> comparison returns QoQ/YoQ, 404 when insufficient")

    # ========== 4. FINANCIAL INSIGHTS ==========
    print("== 4. FINANCIAL INSIGHTS ==")
    db = setup_db()
    seed(db, full_quarters())
    with_db(db)
    client = TestClient(app)
    try:
        resp = client.get("/companies/ABC/insights")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["positive"]
        assert data["growth_analysis"]
        assert "risk_flags" in data

        resp = client.get("/companies/NODATA/insights")
        assert resp.status_code == 404
    finally:
        clear_overrides()
        db.close()
    print("  OK -> insights return structured groups, 404 when insufficient")

    # ========== 5. AI ANALYSIS + COMPANY SCORE (mocked workflow) ==========
    print("== 5. AI ANALYSIS + COMPANY SCORE ==")
    db = setup_db()
    with_db(db)
    app.dependency_overrides[get_workflow] = lambda: FakeWorkflow({
        "status": "completed",
        "llm_analysis_valid": True,
        "structured_analysis": {
            "summary": "Strong quarter",
            "company_score": 78,
        },
        "score": 78,
        "score_explanation": "Strong growth",
        "error": None,
        "persisted_id": 7,
    })
    client = TestClient(app)
    try:
        resp = client.get("/companies/ABC/analysis")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["symbol"] == "ABC"
        assert data["status"] == "completed"
        assert data["score"] == 78
        assert data["llm_analysis_valid"] is True
        assert data["persisted_id"] == 7

        # Insufficient-data workflow -> 404
        app.dependency_overrides[get_workflow] = lambda: FakeWorkflow({
            "status": "insufficient_data",
            "error": "Not enough data",
            "persisted_id": None,
        })
        resp = client.get("/companies/ABC/analysis")
        assert resp.status_code == 404, resp.text
    finally:
        clear_overrides()
        db.close()
    print("  OK -> analysis endpoint (mocked LLM) returns score, 404 on no data")

    # ========== 6. SEMANTIC SEARCH (mocked vector service) ==========
    print("== 6. SEMANTIC SEARCH ==")
    db = setup_db()
    with_db(db)
    fake_vector = FakeVectorService([
        {"point_id": "ABC", "score": 0.91,
         "payload": {"symbol": "ABC", "company_score": 78}},
        {"point_id": "DEF", "score": 0.62,
         "payload": {"symbol": "DEF", "company_score": 30}},
    ])
    app.dependency_overrides[get_vector_service] = lambda: fake_vector
    client = TestClient(app)
    try:
        resp = client.get("/companies/search", params={"q": "revenue growth", "limit": 2})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["query"] == "revenue growth"
        assert data["limit"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["point_id"] == "ABC"
        assert data["results"][0]["payload"]["company_score"] == 78
        assert fake_vector.queries == [("revenue growth", 2)]

        # Missing q -> 422
        resp = client.get("/companies/search")
        assert resp.status_code == 422

        # limit bounds -> 422
        resp = client.get("/companies/search", params={"q": "x", "limit": 0})
        assert resp.status_code == 422
        resp = client.get("/companies/search", params={"q": "x", "limit": 51})
        assert resp.status_code == 422
    finally:
        clear_overrides()
        db.close()
    print("  OK -> search (mocked Qdrant) returns ranked hits + validation")

    print("\nALL STEP 12 CHECKS PASSED")


if __name__ == "__main__":
    main()