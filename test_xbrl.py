from app.database.database import SessionLocal
from app.repositories.financial_result_repository import FinancialResultRepository
from app.services.xbrl_service import XBRLService
from app.services.xbrl_parser import XBRLParser


db = SessionLocal()

repository = FinancialResultRepository(db)

# Get one stored Valiant Laboratories result
result = repository.get_by_seq_number(184838)

if not result:
    print("Result not found")
    exit()

print("SYMBOL:", result.symbol)
print("SEQ:", result.seq_number)
print("XBRL URL:", result.xbrl_url)

# Download XBRL
xbrl_service = XBRLService()

xml = xbrl_service.download_xbrl(result.xbrl_url)

print("\nXBRL DOWNLOADED")
print("XML LENGTH:", len(xml))

# Parse XML
parser = XBRLParser()

root = parser.parse(xml)

print("XML PARSED SUCCESSFULLY")

# Extract financial data
financial_data = parser.extract_financial_data(root)

print("\nFINANCIAL DATA:")
print(financial_data)

db.close()