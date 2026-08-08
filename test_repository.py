from app.database.database import SessionLocal
from app.repositories.financial_result_repository import FinancialResultRepository

# Create database session
db = SessionLocal()

# Create repository
repo = FinancialResultRepository(db)

# Fetch latest and previous financial results
latest = repo.get_latest_result("TCS")
previous = repo.get_previous_result("TCS")

print("Latest:")
print(latest.filing_date)
print(latest.period)

print()

print("Previous:")
print(previous.filing_date)
print(previous.period)

# Close database session
db.close()