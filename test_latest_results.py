from app.services.nse_service import NseService

print("### TEST LATEST NSE RESULTS ###")

service = NseService()

# Ask NSE for financial results for INFY.
# We are NOT providing a year or quarter here.
# The purpose of this test is to see what the current
# NSE endpoint actually returns.
results = service.get_company_results("INFY")

print("\nTOTAL RECORDS:", len(results))

for result in results[:10]:

    print("\n" + "=" * 80)

    print("SYMBOL:", result.get("symbol"))
    print("COMPANY:", result.get("companyName"))
    print("SEQ:", result.get("seqNumber"))

    print("FROM:", result.get("fromDate"))
    print("TO:", result.get("toDate"))

    print("FILING:", result.get("filingDate"))
    print("RELATING TO:", result.get("relatingTo"))

    print("CONSOLIDATED:", result.get("consolidated"))

    print("XBRL:", result.get("xbrl"))

    print("=" * 80)