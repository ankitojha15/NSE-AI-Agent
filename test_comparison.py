from app.database.database import SessionLocal
from app.repositories.financial_result_repository import FinancialResultRepository


db = SessionLocal()

try:
    repository = FinancialResultRepository(db)

    results = repository.get_company_quarters("HARSHA")

    print("TOTAL UNIQUE QUARTERS:", len(results))

    for result in results:
        raw = result.raw_data or {}

        print(
            result.seq_number,
            "|",
            raw.get("fromDate"),
            "|",
            raw.get("toDate")
        )

finally:
    db.close()