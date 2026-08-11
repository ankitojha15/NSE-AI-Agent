from app.database.database import SessionLocal
from app.repositories.financial_result_repository import FinancialResultRepository


db = SessionLocal()

repository = FinancialResultRepository(db)

result = repository.get_by_seq_number("184838")

print("SEQ:", result.seq_number)
print("SYMBOL:", result.symbol)
print("FINANCIAL DATA:")
print(result.financial_data)

db.close()