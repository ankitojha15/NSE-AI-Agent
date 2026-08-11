from app.services.http_client import HTTPClient

client = HTTPClient()

url = (
    "https://www.nseindia.com"
    "/api/corporates-financial-results"
    "?index=equities"
    "&period=Quarterly"
    "&symbol=INFY"
    "&from_date=01-01-2026"
    "&to_date=10-08-2026"
)

print("REQUEST URL:")
print(url)

response = client.get(url)

data = response.json()

print("\nTOTAL RECORDS:", len(data))

for record in data[:20]:

    print(
        record.get("symbol"),
        "| FROM:", record.get("fromDate"),
        "| TO:", record.get("toDate"),
        "| FILING:", record.get("filingDate"),
        "| SEQ:", record.get("seqNumber")
    )