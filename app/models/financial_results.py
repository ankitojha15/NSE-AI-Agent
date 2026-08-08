from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    JSON
)

from datetime import datetime

from app.database.models import Base


class FinancialResult(Base):
    """
    Database model for storing NSE financial result metadata.

    Purpose
    -------
    - Keep track of processed NSE filings.
    - Prevent duplicate processing.
    - Store the complete raw NSE response for future use.
    """

    # Database table name
    __tablename__ = "financial_results"

    # Internal primary key
    id = Column(Integer, primary_key=True, index=True)

    # Unique identifier provided by NSE.
    # We'll use this to detect whether a filing
    # has already been processed.
    seq_number = Column(String(30), unique=True, nullable=False)

    # Company information
    symbol = Column(String(30), index=True)
    company_name = Column(String(255))

    # Filing information
    filing_date = Column(String(50))
    period = Column(String(100))

    # Result type
    audited = Column(String(30))
    consolidated = Column(String(50))

    # Link to the XBRL document
    xbrl_url = Column(String(500))

    # Store the complete original JSON returned by NSE.
    # This makes the application future-proof because
    # we won't lose information if NSE adds new fields.
    raw_data = Column(JSON)

    # Store parsed financial metrics extracted from XBRL.
    # This avoids parsing the same XBRL file repeatedly.
    financial_data = Column(JSON)

    # Timestamp when we stored this record.
    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )