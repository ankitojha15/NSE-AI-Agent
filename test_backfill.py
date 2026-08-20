from app.database.database import SessionLocal
from app.services.nse_service import NseService
from app.services.quarter_backfill_service import (
    QuarterBackfillService
)


db = SessionLocal()

try:
    nse_service = NseService()

    service = QuarterBackfillService(
        db,
        nse_service
    )

    results = service.backfill_company(
        "HDFCBANK"
    )

    print(
        "\nTOTAL UNIQUE QUARTERS:",
        len(results)
    )

    for result in results:

        raw = result.raw_data or {}

        print(
            result.seq_number,
            "|",
            raw.get("fromDate"),
            "|",
            raw.get("toDate")
        )

finally:
    db.close()