from app.database.database import SessionLocal
from app.services.financial_comparsion_service import (
    FinancialComparisonService
)


db = SessionLocal()

service = FinancialComparisonService(db)

result = service.compare("VALIANTLAB")

print(result)

db.close()