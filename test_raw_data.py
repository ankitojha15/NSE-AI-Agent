from app.database.database import SessionLocal
from app.repositories.financial_result_repository import FinancialResultRepository


db = SessionLocal()

repository = FinancialResultRepository(db)

result = repository.get_latest_result("INFY")

print("\n==============================")
print("LATEST INFY RAW DATA")
print("==============================")

if result:
    raw_data = result.raw_data or {}

    print("\nRAW DATA KEYS:")
    for key in raw_data.keys():
        print("-", key)

    print("\nRAW DATA:")
    print(raw_data)

else:
    print("No result found.")

db.close()