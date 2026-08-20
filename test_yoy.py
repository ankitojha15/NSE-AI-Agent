from app.database.database import SessionLocal
from app.repositories.financial_result_repository import (
    FinancialResultRepository
)

db = SessionLocal()

repository = FinancialResultRepository(db)

results = repository.get_company_history("HDFCBANK")

for result in results:
    raw = result.raw_data or {}

    print("\n---")
    print("SEQ:", result.seq_number)
    print("FROM DATE:", raw.get("fromDate"))
    print("TO DATE:", raw.get("toDate"))

db.close()