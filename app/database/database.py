from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base
from app.models.company import Company
from app.models.financial_results import FinancialResult

DATABASE_URL = "mysql+pymysql://root:12%40root12@localhost:3306/nse_ai"
engine = create_engine(
    DATABASE_URL
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