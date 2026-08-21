"""
Correction phase tests — covers all 10 goals (A-K).
No real Telegram, LLM, NSE, or Qdrant calls (all mocked).
"""
import hashlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.models.financial_results import FinancialResult
from app.models.telegram_notification import TelegramNotification
from app.repositories.financial_result_repository import FinancialResultRepository
from app.schemas.ai_analysis import LLMAnalysisResult
from app.schemas.financial_analysis import FinancialAnalysisContract
from app.services.financial_analysis_service import FinancialAnalysisService
from app.services.telegram_service import TelegramService
from app.utils.quarter_utils import quarter_label


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

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


def sample_analysis(periods=None, yoy_exhausted=False):
    base = {
        "qoq": {
            "sales": {"latest": 400, "previous": 300, "growth_percent": 33.33},
            "ebitda": {"latest": 120, "previous": 90, "growth_percent": 33.33},
        },
        "yoy": {
            "sales": {"latest": 400, "previous": 350, "growth_percent": 14.29},
        },
        "latest": {"sales": 400, "ebitda": 120, "net_profit": 60, "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0},
        "periods": periods or {
            "latest": {"from": "01-Apr-2026", "to": "30-Jun-2026"},
            "previous": {"from": "01-Jan-2026", "to": "31-Mar-2026"},
            "yoy": {"from": "01-Apr-2025", "to": "30-Jun-2025"},
        },
        "latest_seq": "999001",
        "previous_seq": "999002",
        "yoy_seq": "999003",
        "yoy_search_exhausted": yoy_exhausted,
        "yoy_search_reason": "no filing for Q1 FY2025-26 after historical search" if yoy_exhausted else None,
    }
    return base


def sample_structured(score=None):
    d = {
        "summary": "Strong quarter.",
        "positive_factors": ["Revenue grew strongly"],
        "negative_factors": ["Margins declined"],
        "risk_factors": ["Concentration risk"],
    }
    if score is not None:
        d["company_score"] = score
        d["score_explanation"] = f"Score {score}"
    return d


class FakePost:
    def __init__(self, error=None):
        self.calls = []
        self.error = error
    def __call__(self, url, json, timeout=10):
        self.calls.append({"url": url, "json": json})
        if self.error:
            raise self.error
        class R:
            def json(self): return {"ok": True, "result": {"message_id": 1}}
        return R()


# ==================================================================
# C. Quarter labels
# ==================================================================
def test_quarter_labels():
    print("== C. QUARTER LABELS ==")

    cases = [
        ("01-Apr-2026", "30-Jun-2026", "Q1", "FY2026-27"),
        ("01-Jul-2026", "30-Sep-2026", "Q2", "FY2026-27"),
        ("01-Oct-2025", "31-Dec-2025", "Q3", "FY2025-26"),
        ("01-Jan-2026", "31-Mar-2026", "Q4", "FY2025-26"),
        ("01-Jan-2025", "31-Mar-2025", "Q4", "FY2024-25"),
        ("01-Apr-2025", "30-Jun-2025", "Q1", "FY2025-26"),
    ]

    for from_d, to_d, exp_q, exp_fy in cases:
        ql = quarter_label(from_d, to_d)
        assert ql["quarter"] == exp_q, f"{from_d}→{to_d}: {ql}"
        assert ql["fy"] == exp_fy, f"{from_d}→{to_d}: {ql}"
        assert ql["range"] == f"{from_d} → {to_d}"
        assert ql["label"] == f"{exp_q} {exp_fy}"

    print("  OK -> Q1-Q4 + FY labels correct for all quarters")
    print("  OK -> date ranges included")


# ==================================================================
# D. QoQ exact period matching
# ==================================================================
def test_qoq_exact_period_matching():
    print("== D. QoQ EXACT PERIOD MATCHING ==")
    db = make_db()
    # Q1 and Q4 consecutive -> valid QoQ
    seed(db, [
        filing("AAA", "30-Jun-2026", 1, {"sales": 400, "ebitda": 100, "net_profit": 50, "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 12.5}),
        filing("AAA", "31-Mar-2026", 2, {"sales": 300, "ebitda": 80, "net_profit": 40, "basic_eps": 4.0, "opm": 19.0, "net_profit_margin": 13.0}),
        filing("AAA", "31-Mar-2025", 3, {"sales": 350, "ebitda": 90, "net_profit": 45, "basic_eps": 4.5, "opm": 21.0, "net_profit_margin": 12.8}),
    ])
    a = FinancialAnalysisService(db).compare_latest_results("AAA")
    # Q1 2026-27 previous should be Q4 2025-26 (consecutive) -> QoQ valid
    # But Q1's previous is Jan-Mar, not Apr-Jun-2025 gap? 01-Apr-2026's expected previous is Jan-Mar 2026 -> exists (seq 2) -> valid
    assert a["qoq"] != {}, "consecutive quarter must produce QoQ"
    assert a["periods"]["latest"]["from"] == "01-Apr-2026"
    assert a["periods"]["previous"]["from"] == "01-Jan-2026"

    # Gap: remove the adjacent quarter -> QoQ must be empty
    db2 = make_db()
    seed(db2, [
        filing("BBB", "30-Jun-2026", 10, {"sales": 400, "ebitda": 100, "net_profit": 50, "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 12.5}),
        # Skip Q4 2025-26 -> next is Q3 2025-26 (not adjacent)
        filing("BBB", "31-Dec-2025", 11, {"sales": 300, "ebitda": 80, "net_profit": 40, "basic_eps": 4.0, "opm": 19.0, "net_profit_margin": 13.0}),
        filing("BBB", "30-Jun-2025", 12, {"sales": 280, "ebitda": 85, "net_profit": 42, "basic_eps": 4.2, "opm": 18.0, "net_profit_margin": 15.0}),
    ])
    b = FinancialAnalysisService(db2).compare_latest_results("BBB")
    assert b["qoq"] == {}, f"gap must prevent QoQ: {b['qoq']}"

    print("  OK -> QoQ only for immediately preceding quarter; gaps rejected")


# ==================================================================
# A. YoY historical lookup (mocked NSE)
# ==================================================================
def test_yoy_historical_lookup():
    print("== A. YoY HISTORICAL LOOKUP ==")
    db = make_db()
    # Latest Q1 2026-27 + previous Q4, but no Q1 2025-26 in DB yet
    seed(db, [
        filing("YYY", "30-Jun-2026", 100, {"sales": 400, "ebitda": 120, "net_profit": 60, "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0}),
        filing("YYY", "31-Mar-2026", 101, {"sales": 300, "ebitda": 90, "net_profit": 50, "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67}),
    ])

    # Monkeypatch NseService.get_financial_results to return the YoY quarter
    from unittest.mock import patch
    yoy_filing = {
        "seqNumber": "999YOY",
        "seq_Id": "999YOY",
        "symbol": "YYY",
        "cmName": "YYY Limited",
        "creation_Date": "10-Aug-2025 12:00:00",
        "qe_Date": "30-Jun-2025",
        "fromDate": "01-Apr-2025",
        "toDate": "30-Jun-2025",
        "audited": "Yes",
        "consolidated": "No",
        "financial_data": {"sales": 350, "ebitda": 100, "net_profit": 55, "basic_eps": 5.5, "opm": 21.0, "net_profit_margin": 15.71},
    }

    with patch("app.services.nse_service.NseService.get_financial_results", return_value={"data": [yoy_filing]}):
        # Also mock XBRL download to avoid network
        with patch("app.services.xbrl_service.XBRLService.download_xbrl", side_effect=Exception("no xbrl")):
            analysis = FinancialAnalysisService(db).compare_latest_results("YYY")

    assert analysis["yoy"] != {}, f"YoY must be found via historical lookup: {analysis}"
    assert analysis["yoy"]["sales"]["growth_percent"] == 14.29, analysis["yoy"]["sales"]
    assert analysis["yoy_seq"] == "999YOY"
    assert analysis["periods"]["yoy"]["from"] == "01-Apr-2025"
    assert analysis["periods"]["yoy"]["to"] == "30-Jun-2025"

    print("  OK -> YoY Q1 2026-27 correctly matched Q1 2025-26 via NSE historical search")


# ==================================================================
# B. Missing YoY — search exhausted
# ==================================================================
def test_missing_yoy_logged():
    print("== B. MISSING YoY (search exhausted) ==")
    db = make_db()
    seed(db, [
        filing("ZZZ", "30-Jun-2026", 200, {"sales": 400, "ebitda": 120, "net_profit": 60, "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0}),
        filing("ZZZ", "31-Mar-2026", 201, {"sales": 300, "ebitda": 90, "net_profit": 50, "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67}),
    ])

    from unittest.mock import patch
    with patch("app.services.nse_service.NseService.get_financial_results", return_value={"data": []}):
        analysis = FinancialAnalysisService(db).compare_latest_results("ZZZ")

    assert analysis["yoy"] == {}
    assert analysis["yoy_search_exhausted"] is True
    assert "Q1" in analysis["yoy_search_reason"] or "01-Apr-2025" in analysis["yoy_search_reason"]

    print("  OK -> exhausted search logged with exact target period")


# ==================================================================
# E. Unit normalization + F. No double conversion
# ==================================================================
def test_unit_normalization():
    print("== E. UNIT NORMALIZATION ==")
    db = make_db()
    # Store raw INR value for latest (5,776,500,000) and normalized previous
    seed(db, [
        filing("UNIT", "30-Jun-2026", 300, {"sales": 5776500000, "ebitda": 120, "net_profit": 60, "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0}),
        filing("UNIT", "31-Mar-2026", 301, {"sales": 300, "ebitda": 90, "net_profit": 50, "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67}),
        filing("UNIT", "30-Jun-2025", 302, {"sales": 350, "ebitda": 100, "net_profit": 55, "basic_eps": 5.5, "opm": 21.0, "net_profit_margin": 15.71}),
    ])
    a = FinancialAnalysisService(db).compare_latest_results("UNIT")
    # 5,776,500,000 / 10M = 577.65 crore
    assert a["latest"]["sales"] == 577.65, f"raw INR must become crore: {a['latest']['sales']}"
    # QoQ should use normalized value
    assert a["qoq"]["sales"]["latest"] == 577.65

    print("  OK -> 5,776,500,000 INR -> 577.65 crore")

    print("== F. NO DOUBLE CONVERSION ==")
    db2 = make_db()
    seed(db2, [
        filing("NODBL", "30-Jun-2026", 310, {"sales": 577.65, "ebitda": 120, "net_profit": 60, "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0}),
        filing("NODBL", "31-Mar-2026", 311, {"sales": 300, "ebitda": 90, "net_profit": 50, "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67}),
        filing("NODBL", "30-Jun-2025", 312, {"sales": 350, "ebitda": 100, "net_profit": 55, "basic_eps": 5.5, "opm": 21.0, "net_profit_margin": 15.71}),
    ])
    b = FinancialAnalysisService(db2).compare_latest_results("NODBL")
    assert b["latest"]["sales"] == 577.65, f"already crore must stay: {b['latest']['sales']}"

    # Negative large value: -936,700,000 -> -93.67 crore
    db3 = make_db()
    seed(db3, [
        filing("NEG", "30-Jun-2026", 320, {"sales": -936700000, "ebitda": 120, "net_profit": 60, "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0}),
        filing("NEG", "31-Mar-2026", 321, {"sales": 300, "ebitda": 90, "net_profit": 50, "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67}),
        filing("NEG", "30-Jun-2025", 322, {"sales": 350, "ebitda": 100, "net_profit": 55, "basic_eps": 5.5, "opm": 21.0, "net_profit_margin": 15.71}),
    ])
    c = FinancialAnalysisService(db3).compare_latest_results("NEG")
    assert c["latest"]["sales"] == -93.67, f"negative raw must normalize: {c['latest']['sales']}"

    # EPS must never be converted
    db4 = make_db()
    seed(db4, [
        filing("EPS", "30-Jun-2026", 330, {"sales": 400, "ebitda": 120, "net_profit": 60, "basic_eps": 5776500000, "opm": 22.0, "net_profit_margin": 15.0}),
        filing("EPS", "31-Mar-2026", 331, {"sales": 300, "ebitda": 90, "net_profit": 50, "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67}),
        filing("EPS", "30-Jun-2025", 332, {"sales": 350, "ebitda": 100, "net_profit": 55, "basic_eps": 5.5, "opm": 21.0, "net_profit_margin": 15.71}),
    ])
    d = FinancialAnalysisService(db4).compare_latest_results("EPS")
    # EPS 5,776,500,000 is absurdly large for EPS but per spec EPS is per-share and must NOT be converted
    assert d["latest"]["basic_eps"] == 5776500000.0, f"EPS must not be crore-converted: {d['latest']['basic_eps']}"

    print("  OK -> already normalized stays; negative handled; EPS exempt")


# ==================================================================
# G/H. Duplicate Telegram (filing identity) + new filing
# ==================================================================
def test_telegram_dedup_filing_identity():
    print("== G/H. TELEGRAM DEDUP (filing identity) ==")
    db = make_db()
    post = FakePost()
    svc = TelegramService(bot_token="T", chat_id="C", db=db, post=post)

    periods = {
        "latest": {"from": "01-Apr-2026", "to": "30-Jun-2026"},
        "previous": {"from": "01-Jan-2026", "to": "31-Mar-2026"},
        "yoy": {"from": "01-Apr-2025", "to": "30-Jun-2025"},
    }

    a1 = sample_analysis(periods=periods)
    a1["latest_seq"] = "SEQ001"
    s1 = sample_structured()

    r1 = svc.send_analysis_notification("AAA", analysis=a1, structured_analysis=s1)
    assert r1["status"] == "sent"
    assert len(post.calls) == 1

    # Same filing, different LLM wording -> still duplicate
    s2 = dict(s1)
    s2["positive_factors"] = ["Totally different wording from new LLM run"]
    r2 = svc.send_analysis_notification("AAA", analysis=a1, structured_analysis=s2)
    assert r2["status"] == "duplicate"
    assert len(post.calls) == 1

    # New filing (new seq) -> sent
    a2 = dict(a1)
    a2["latest_seq"] = "SEQ002"
    r3 = svc.send_analysis_notification("AAA", analysis=a2, structured_analysis=s1)
    assert r3["status"] == "sent"
    assert len(post.calls) == 2

    # Fallback identity: same symbol + same period -> duplicate even without seq
    db2 = make_db()
    post2 = FakePost()
    svc2 = TelegramService(bot_token="T", chat_id="C", db=db2, post=post2)
    a_no_seq = sample_analysis(periods=periods)
    a_no_seq["latest_seq"] = None
    svc2.send_analysis_notification("BBB", analysis=a_no_seq, structured_analysis=s1)
    r_dup = svc2.send_analysis_notification("BBB", analysis=a_no_seq, structured_analysis=s2)
    assert r_dup["status"] == "duplicate"

    print("  OK -> same filing deduped; new seq re-notifies; period fallback works")


# ==================================================================
# I. LLM contradiction protection
# ==================================================================
def test_llm_contradiction_protection():
    print("== I. LLM CONTRADICTION PROTECTION ==")
    from app.workflows.analysis_workflow import AnalysisWorkflow
    from unittest.mock import MagicMock

    # Contract has sales=400
    db = make_db()
    seed(db, [
        filing("CONTRA", "30-Jun-2026", 400, {"sales": 400, "ebitda": 120, "net_profit": 60, "basic_eps": 6.0, "opm": 22.0, "net_profit_margin": 15.0}),
        filing("CONTRA", "31-Mar-2026", 401, {"sales": 300, "ebitda": 90, "net_profit": 50, "basic_eps": 5.0, "opm": 20.0, "net_profit_margin": 16.67}),
        filing("CONTRA", "30-Jun-2025", 402, {"sales": 350, "ebitda": 100, "net_profit": 55, "basic_eps": 5.5, "opm": 21.0, "net_profit_margin": 15.71}),
    ])

    # Fake LLM that says "revenue missing" even though contract has revenue
    bad_llm_result = {
        "summary": "Revenue missing for this quarter.",
        "positive_factors": ["Revenue missing so no positives"],
        "negative_factors": ["Revenue missing"],
        "growth_analysis": ["Revenue missing, cannot compare"],
        "margin_analysis": ["OPM steady"],
        "risk_factors": ["Revenue missing is a risk"],
    }

    class FakeAI:
        def analyze_structured(self, contract):
            return bad_llm_result

    wf = AnalysisWorkflow(db, ai_service=FakeAI())
    state = wf.run("CONTRA")
    structured = state.get("structured_analysis") or {}

    # After sanitization, "revenue missing" claims must be stripped
    for field in ("summary", "growth_analysis", "margin_analysis"):
        val = structured.get(field)
        if isinstance(val, str):
            assert "revenue missing" not in val.lower(), f"contradiction not removed from {field}: {val}"
        elif isinstance(val, list):
            for item in val:
                assert "revenue missing" not in str(item).lower(), f"contradiction in {field}: {item}"

    # Also verify via Telegram message: no "revenue missing"
    post = FakePost()
    svc = TelegramService(bot_token="T", chat_id="C", post=post)
    analysis = FinancialAnalysisService(db).compare_latest_results("CONTRA")
    svc.send_analysis_notification("CONTRA", analysis=analysis, structured_analysis=structured)
    text = post.calls[0]["json"]["text"]
    assert "revenue missing" not in text.lower(), f"Telegram must not say revenue missing: {text}"

    print("  OK -> LLM 'revenue missing' stripped when contract has revenue")


# ==================================================================
# J. AI score absent from Telegram
# ==================================================================
def test_ai_score_absent():
    print("== J. AI SCORE ABSENT ==")
    post = FakePost()
    svc = TelegramService(bot_token="T", chat_id="C", post=post)
    svc.send_analysis_notification("AAA", analysis=sample_analysis(), structured_analysis=sample_structured(score=95), score=95)
    text = post.calls[0]["json"]["text"]
    assert "AI Score" not in text
    assert "company_score" not in text.lower()
    assert "95/100" not in text
    assert "Score 95" not in text

    print("  OK -> no AI score in Telegram")


# ==================================================================
# K. Telegram message contains exact reporting period
# ==================================================================
def test_telegram_period_display():
    print("== K. TELEGRAM PERIOD DISPLAY ==")
    post = FakePost()
    svc = TelegramService(bot_token="T", chat_id="C", post=post)
    svc.send_analysis_notification("TCS", analysis=sample_analysis(), structured_analysis=sample_structured())

    text = post.calls[0]["json"]["text"]
    assert "Reporting Period" in text
    assert "Q1 FY2026-27" in text
    assert "01-Apr-2026 → 30-Jun-2026" in text
    assert "Latest Quarter" not in text
    assert "Last Quarter" not in text
    # QoQ period labels
    assert "Current:" in text and "Previous:" in text
    # YoY period labels
    assert "Previous Year:" in text
    # Financials header is period-specific
    assert "Financials — Q1 FY2026-27" in text

    print("  OK -> exact periods, Q/FY labels, no ambiguous 'Latest Quarter'")


def main():
    test_quarter_labels()
    test_qoq_exact_period_matching()
    test_yoy_historical_lookup()
    test_missing_yoy_logged()
    test_unit_normalization()
    test_telegram_dedup_filing_identity()
    test_llm_contradiction_protection()
    test_ai_score_absent()
    test_telegram_period_display()
    print("\nALL CORRECTION CHECKS PASSED")


if __name__ == "__main__":
    main()
