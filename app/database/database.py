from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.database.models import Base
from app.models.company import Company
from app.models.financial_results import FinancialResult

engine = create_engine(
    settings.DATABASE_URL
)

SessionLocal = sessionmaker(
    autocommit = False,
    autoflush = False,
    bind=engine
)


Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()