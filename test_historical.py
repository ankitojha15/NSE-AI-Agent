from app.services.nse_service import NseService


service = NseService()

results = service.get_financial_results(
    symbol="TCS",
    from_date="01-01-2024",
    to_date="31-12-2024"
)

print("Total results:", len(results))

for record in results:

    print(
        "SEQ:",
        record.get("seqNumber"),
        "| filingDate:",
        record.get("filingDate"),
        "| period:",
        record.get("period"),
        "| fromDate:",
        record.get("fromDate"),
        "| toDate:",
        record.get("toDate"),
        "| relatingTo:",
        record.get("relatingTo"),
        "| XBRL:",
        bool(record.get("xbrl"))
    )