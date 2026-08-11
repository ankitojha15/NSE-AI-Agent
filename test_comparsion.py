from app.database.database import SessionLocal
from app.services.financial_comparsion_service import (
    FinancialComparisonService
)


db = SessionLocal()

service = FinancialComparisonService(db)

result = service.compare("VALIANTLAB")

qoq = service.calculate_qoq(
    result["latest_financial_data"],
    result["previous_financial_data"]
)

print("\nQoQ COMPARISON:")
print(qoq)

print(result)

db.close()