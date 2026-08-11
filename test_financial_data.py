from app.database.database import SessionLocal
from app.repositories.financial_result_repository import FinancialResultRepository


db = SessionLocal()

repository = FinancialResultRepository(db)

result = repository.get_latest_result("INFY")

print("\n==============================")
print("INFY FINANCIAL DATA")
print("==============================")

print("\nSEQ:", result.seq_number)

print("\nFINANCIAL DATA:")
print(result.financial_data)

db.close()