from app.services.nse_service import NseService
from app.database.database import SessionLocal

db = SessionLocal()

service = NseService()

new_records = service.sync_integrated_filings(db)

print("\nNEW RECORDS:", len(new_records))

for record in new_records:
    print(
        record.get("symbol"),
        "|",
        record.get("cmName"),
        "|",
        record.get("seq_Id")
    )

db.close()