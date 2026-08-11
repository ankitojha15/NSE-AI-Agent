from app.database.database import SessionLocal
from app.models.financial_results import FinancialResult
from app.services.xbrl_service import XBRLService
from app.services.xbrl_parser import XBRLParser


db = SessionLocal()

result = (
    db.query(FinancialResult)
    .filter(FinancialResult.seq_number == "1189815")
    .first()
)

print("SEQ:", result.seq_number)
print("SYMBOL:", result.symbol)
print("XBRL URL:", result.raw_data.get("xbrl"))


xbrl_service = XBRLService()
parser = XBRLParser()

xml = xbrl_service.download_xbrl(
    result.raw_data["xbrl"]
)

print("XBRL DOWNLOADED")
print("XML LENGTH:", len(xml))


root = parser.parse(xml)

financial_data = parser.extract_financial_data(root)

print("EXTRACTED FINANCIAL DATA:")
print(financial_data)


db.close()