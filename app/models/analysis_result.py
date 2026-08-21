from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
)

from app.database.models import Base


class AnalysisResult(Base):
    """
    Database model for storing the final workflow analysis result.

    One row per company (symbol is unique). Re-running the workflow
    for the same company updates the existing row.
    """

    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(30), unique=True, index=True, nullable=False)

    status = Column(String(30), nullable=False, default="completed")

    score = Column(Integer, nullable=True)
    score_explanation = Column(Text, nullable=True)

    contract_data = Column(JSON, nullable=True)
    llm_analysis = Column(Text, nullable=True)
    provider_used = Column(String(20), nullable=True)

    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )