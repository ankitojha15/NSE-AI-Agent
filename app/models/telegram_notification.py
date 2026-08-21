from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
)

from app.database.models import Base


class TelegramNotification(Base):
    """
    Records the Telegram notifications sent per analysis.

    A notification is identified by (symbol, filing_seq) so the same
    financial result is never sent twice regardless of LLM wording.
    When seq is unavailable the reporting period (fromDate→toDate) is
    used as a fallback identity. A new notification is only sent when
    a genuinely new or revised filing appears.
    """

    __tablename__ = "telegram_notifications"

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "filing_identity",
            name="uq_telegram_symbol_filing",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(30), index=True, nullable=False)
    # Identity: seq_number when available, otherwise "fromDate→toDate"
    filing_identity = Column(String(64), nullable=False)
    # Kept for backwards compat / debugging; not used for dedup.
    content_hash = Column(String(64), nullable=True)

    sent_at = Column(DateTime, default=datetime.utcnow)
