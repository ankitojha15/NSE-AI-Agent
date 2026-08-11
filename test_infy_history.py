from app.database.database import SessionLocal
from app.models.financial_results import FinancialResult


# Create database session
db = SessionLocal()


# Get all INFY financial records
results = (
    db.query(FinancialResult)
    .filter(
        FinancialResult.symbol == "INFY"
    )
    .order_by(
        FinancialResult.filing_date.desc()
    )
    .all()
)


# Print every INFY record
for result in results:

    print(
        "SEQ:",
        result.seq_number
    )

    print(
        "FROM:",
        result.raw_data.get("fromDate")
        if result.raw_data
        else None
    )

    print(
        "TO:",
        result.raw_data.get("toDate")
        if result.raw_data
        else None
    )

    print(
        "FINANCIAL DATA:",
        result.financial_data
    )

    print("-" * 60)


# Close database connection
db.close()