from app.database.database import SessionLocal
from app.services.nse_service import NseService


# Create database session
db = SessionLocal()

# Create NSE service
service = NseService()


# Fetch INFY historical financial results.
#
# We are asking NSE for results from 2023 to 2024
# so that the YoY comparison can find:
#
# 01-Oct-2023 → 31-Dec-2023
#
service.backfill_company_history(
    db=db,
    symbol="INFY",
    from_date="01-01-2023",
    to_date="31-12-2024"
)


# Close database connection
db.close()

print("INFY historical backfill completed.")