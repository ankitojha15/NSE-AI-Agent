from app.database.database import SessionLocal
from app.services.nse_service import NseService

# Create database session
db = SessionLocal()

# Create NSE service
service = NseService()

# Run synchronization
new_results = service.sync_financial_results(db)

print(f"Inserted {len(new_results)} new records.")

# Close database session
db.close()