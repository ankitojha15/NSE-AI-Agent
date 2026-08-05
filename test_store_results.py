from app.database.database import SessionLocal
from app.services.nse_service import NseService

db = SessionLocal()

service = NseService()

new_results = service.sync_financial_results(db)

print(f"New Results: {len(new_results)}")

db.close()