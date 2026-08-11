print("### TEST_ANALYSIS NEW FILE ###")

from app.database.database import SessionLocal
from app.services.financial_analysis_service import FinancialAnalysisService


db = SessionLocal()

service = FinancialAnalysisService(db)

result = service.compare_latest_results("TCS")


print("\n==============================")
print("TCS FINANCIAL ANALYSIS")
print("==============================")

print("\nSymbol:")
print(result["symbol"])

print("\n==============================")
print("LATEST")
print("==============================")
print(result["latest"])

print("\n==============================")
print("PREVIOUS QUARTER")
print("==============================")
print(result["previous"])

print("\n==============================")
print("QoQ COMPARISON")
print("==============================")
print(result["qoq"])

print("\n==============================")
print("YoY COMPARISON")
print("==============================")
print(result["yoy"])

print("\n==============================")
print("SAME QUARTER LAST YEAR")
print("==============================")
print(result["same_quarter_last_year"])


db.close()