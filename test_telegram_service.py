import hashlib
import requests

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.database.models import Base
from app.models.telegram_notification import TelegramNotification
from app.services.telegram_service import (
    MAX_MESSAGE_LENGTH,
    TelegramService,
)


class FakeResponse:
    def __init__(self, ok=True, message_id=111):
        self.ok = ok
        self.status_code = 200 if ok else 500
        self._message_id = message_id

    def json(self):
        return {
            "ok": self.ok,
            "result": {"message_id": self._message_id},
        }


class FakePost:
    """Mocked Telegram Bot API transport."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, url, json, timeout=10):
        self.calls.append({"url": url, "json": json, "timeout": timeout})

        if self.error:
            raise self.error

        return FakeResponse()


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def sample_analysis():
    return {
        "qoq": {
            "sales": {"latest": 400, "previous": 300, "growth_percent": 33.33},
            "ebitda": {"latest": 120, "previous": 90, "growth_percent": 33.33},
            "net_profit": {"latest": 60, "previous": 50, "growth_percent": 20.0},
            "basic_eps": {"latest": 6.0, "previous": 5.0, "growth_percent": 20.0},
            "opm": {"latest": 22.0, "previous": 20.0, "change": 2.0},
            "net_profit_margin": {"latest": 15.0, "previous": 16.67, "change": -1.67},
        },
        "yoy": {
            "sales": {"latest": 400, "previous": 350, "growth_percent": 14.29},
            "net_profit": {"latest": 60, "previous": 48, "growth_percent": 25.0},
        },
        "latest": {
            "sales": 400,
            "ebitda": 120,
            "net_profit": 60,
            "basic_eps": 6.0,
            "opm": 22.0,
            "net_profit_margin": 15.0,
        },
        "periods": {
            "latest": {"from": "01-Apr-2026", "to": "30-Jun-2026"},
            "previous": {"from": "01-Jan-2026", "to": "31-Mar-2026"},
            "yoy": {"from": "01-Apr-2025", "to": "30-Jun-2025"},
        },
        "latest_seq": "999001",
        "previous_seq": "999002",
        "yoy_seq": "999003",
    }


def sample_structured():
    return {
        "summary": "Strong quarter with higher revenue and profit.",
        "positive_factors": ["Revenue grew strongly"],
        "negative_factors": ["Margins declined slightly"],
        "growth_analysis": ["Sales up quarter on quarter"],
        "margin_analysis": ["OPM steady"],
        "risk_factors": ["Concentration risk on key client"],
        "company_score": 78,
        "score_explanation": "Strong revenue and profit growth.",
    }


def long_analysis():
    structured = sample_structured()
    structured["positive_factors"] = [
        f"Positive factor number {i} with a very long explanatory "
        f"sentence designed to inflate the message length well beyond "
        f"the Telegram {MAX_MESSAGE_LENGTH} character limit for "
        f"testing the split behaviour."
        for i in range(60)
    ]
    return sample_analysis(), structured


def main():

    # ========== 1. SUCCESSFUL NOTIFICATION ==========
    print("== 1. SUCCESSFUL NOTIFICATION ==")
    post = FakePost()
    service = TelegramService(
        bot_token="TEST_TOKEN",
        chat_id="-100123456",
        post=post,
    )

    result = service.send_analysis_notification(
        "ABC",
        analysis=sample_analysis(),
        structured_analysis=sample_structured(),
        score=78,
    )

    assert result["status"] == "sent", result
    assert len(post.calls) == 1, post.calls
    payload = post.calls[0]["json"]
    assert payload["chat_id"] == "-100123456"
    assert "TEST_TOKEN" not in payload["text"], "token must not leak"

    print("  OK -> single message sent to the configured chat")
    post = None

    # ========== 2. MESSAGE CONTENT ==========
    print("== 2. MESSAGE CONTENT ==")
    post = FakePost()
    service = TelegramService(
        bot_token="TEST_TOKEN", chat_id="-100123456", post=post
    )
    service.send_analysis_notification(
        "ABC",
        analysis=sample_analysis(),
        structured_analysis=sample_structured(),
        score=78,
    )
    text = post.calls[0]["json"]["text"]

    assert "ABC" in text
    assert "QoQ" in text and "YoY" in text
    assert "Revenue/Sales" in text
    assert "EBITDA" in text
    assert "Net Profit" in text
    assert "EPS" in text
    assert "OPM" in text
    assert "Net Profit Margin" in text
    assert "AI Score" not in text
    assert "company_score" not in text.lower()
    assert "Revenue grew strongly" in text
    assert "Margins declined slightly" in text
    assert "Concentration risk" in text
    assert "+33.33%" in text
    assert "+2.00 pts" in text
    # Period labels must be present
    assert "Reporting Period" in text
    assert "QoQ" in text and "YoY" in text

    print("  OK -> symbol, QoQ, YoY, financials and factors present (no AI score)")
    post = None

    # ========== 3. TELEGRAM API FAILURE ==========
    print("== 3. TELEGRAM API FAILURE ==")
    post = FakePost(error=requests.exceptions.HTTPError("500 Server Error"))
    service = TelegramService(
        bot_token="TEST_TOKEN", chat_id="-100123456", post=post
    )
    result = service.send_analysis_notification(
        "ABC",
        analysis=sample_analysis(),
        structured_analysis=sample_structured(),
        score=78,
    )
    assert result["status"] == "failed", result

    post = FakePost(error=requests.exceptions.Timeout("timed out"))
    service = TelegramService(
        bot_token="TEST_TOKEN", chat_id="-100123456", post=post
    )
    result = service.send_analysis_notification(
        "ABC",
        analysis=sample_analysis(),
        structured_analysis=sample_structured(),
        score=78,
    )
    assert result["status"] == "failed", result

    print("  OK -> API errors and timeouts handled without raising")
    post = None

    # ========== 4. MISSING CONFIGURATION ==========
    print("== 4. MISSING CONFIGURATION ==")
    post = FakePost()

    old_token = settings.TELEGRAM_BOT_TOKEN
    old_chat = settings.TELEGRAM_CHAT_ID

    try:
        settings.TELEGRAM_BOT_TOKEN = None
        settings.TELEGRAM_CHAT_ID = None

        service = TelegramService(post=post)
        result = service.send_analysis_notification(
            "ABC",
            analysis=sample_analysis(),
            structured_analysis=sample_structured(),
            score=78,
        )
        assert result["status"] == "skipped", result
        assert post.calls == [], post.calls
    finally:
        settings.TELEGRAM_BOT_TOKEN = old_token
        settings.TELEGRAM_CHAT_ID = old_chat

    print("  OK -> disabled cleanly when configuration is missing")
    post = None

    # ========== 5. DUPLICATE PREVENTION ==========
    print("== 5. DUPLICATE PREVENTION ==")
    db = make_db()
    post = FakePost()
    service = TelegramService(
        bot_token="TEST_TOKEN", chat_id="-100123456", db=db, post=post
    )

    first = service.send_analysis_notification(
        "ABC",
        analysis=sample_analysis(),
        structured_analysis=sample_structured(),
        score=78,
    )
    second = service.send_analysis_notification(
        "ABC",
        analysis=sample_analysis(),
        structured_analysis=sample_structured(),
        score=78,
    )

    assert first["status"] == "sent", first
    assert second["status"] == "duplicate", second
    assert len(post.calls) == 1, f"expected 1 send, got {len(post.calls)}"
    assert db.query(TelegramNotification).count() == 1
    assert db.query(TelegramNotification).first().symbol == "ABC"

    # Same filing with different LLM wording is still a duplicate.
    changed = sample_structured()
    changed["positive_factors"] = ["Totally new positive factor"]
    third = service.send_analysis_notification(
        "ABC",
        analysis=sample_analysis(),
        structured_analysis=changed,
        score=90,
    )
    assert third["status"] == "duplicate", third
    assert len(post.calls) == 1, f"same filing must not re-notify, got {len(post.calls)}"

    # New filing (different seq) IS sent even for same symbol.
    new_analysis = sample_analysis()
    new_analysis["latest_seq"] = "999999"
    fourth = service.send_analysis_notification(
        "ABC",
        analysis=new_analysis,
        structured_analysis=sample_structured(),
        score=78,
    )
    assert fourth["status"] == "sent", fourth
    assert len(post.calls) == 2
    assert db.query(TelegramNotification).count() == 2
    assert {r.filing_identity for r in db.query(TelegramNotification).all()} == {"999001", "999999"}

    print("  OK -> same filing deduped by seq; new filing re-notifies")
    db.close()
    post = None

    # ========== 6. LONG MESSAGE HANDLING ==========
    print("== 6. LONG MESSAGE HANDLING ==")
    post = FakePost()
    service = TelegramService(
        bot_token="TEST_TOKEN", chat_id="-100123456", post=post
    )
    analysis, structured = long_analysis()

    result = service.send_analysis_notification(
        "ABC",
        analysis=analysis,
        structured_analysis=structured,
        score=78,
    )

    assert result["status"] == "sent", result
    assert result["parts"] > 1, result
    assert len(post.calls) == result["parts"]
    for call in post.calls:
        assert len(call["json"]["text"]) <= MAX_MESSAGE_LENGTH, call

    print("  OK -> long message split into multiple bounded parts")
    post = None

    print("\nALL TELEGRAM CHECKS PASSED")


if __name__ == "__main__":
    main()