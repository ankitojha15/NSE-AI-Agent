from app.database.database import SessionLocal
from app.services.nse_service import NseService

print("### TEST NSE RAW INFY RECORDS ###")

db = SessionLocal()

service = NseService()

results = service.get_company_results("INFY")

print(f"\nTotal INFY records received: {len(results)}")

for result in results:

    print("\n" + "=" * 80)

    print("SEQ:", result.get("seqNumber"))
    print("FROM:", result.get("fromDate"))
    print("TO:", result.get("toDate"))
    print("FILING:", result.get("filingDate"))
    print("RELATING TO:", result.get("relatingTo"))
    print("BROADCAST:", result.get("broadCastDate"))
    print("EXCHANGE TIME:", result.get("exchdisstime"))
    print("AUDITED:", result.get("audited"))
    print("CONSOLIDATED:", result.get("consolidated"))
    print("OLD/NEW FLAG:", result.get("oldNewFlag"))
    print("RE-IND:", result.get("reInd"))
    print("FORMAT:", result.get("format"))
    print("PARAMS:", result.get("params"))
    print("XBRL:", result.get("xbrl"))

    print("=" * 80)

db.close()