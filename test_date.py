from app.database.database import SessionLocal
from app.models.financial_results import FinancialResult
import json

db = SessionLocal()

result = (
    db.query(FinancialResult)
    .filter(FinancialResult.seq_number == "184838")
    .first()
)

print(json.dumps(result.raw_data, indent=2))

db.close()