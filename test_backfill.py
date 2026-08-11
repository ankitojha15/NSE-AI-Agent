from app.database.database import SessionLocal
from app.services.nse_service import NseService
from app.repositories.financial_result_repository import FinancialResultRepository


db = SessionLocal()

service = NseService()
repository = FinancialResultRepository(db)

results = service.get_financial_results(
    symbol="TCS",
    from_date="01-01-2024",
    to_date="31-12-2024"
)

print("NSE records:", len(results))

for result in results:

    seq = result.get("seqNumber")

    print(
        "SEQ:",
        seq,
        "| fromDate:",
        result.get("fromDate"),
        "| toDate:",
        result.get("toDate"),
        "| EXISTS:",
        repository.exists(seq)
    )

db.close()