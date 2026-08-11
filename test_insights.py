from app.database.database import SessionLocal
from app.services.financial_analysis_service import FinancialAnalysisService
from app.services.financial_insight_service import FinancialInsightService


db = SessionLocal()

analysis_service = FinancialAnalysisService(db)
insight_service = FinancialInsightService()

analysis = analysis_service.compare_latest_results("TCS")

insights = insight_service.analyze(analysis)


print("\n==============================")
print("TCS FINANCIAL INSIGHTS")
print("==============================")

print("\nPOSITIVE:")
for item in insights["positive"]:
    print("-", item)

print("\nNEGATIVE:")
for item in insights["negative"]:
    print("-", item)

print("\nGROWTH ANALYSIS:")
for item in insights["growth_analysis"]:
    print("-", item)

print("\nMARGIN ANALYSIS:")
for item in insights["margin_analysis"]:
    print("-", item)

print("\nRISK FLAGS:")
for item in insights["risk_flags"]:
    print("-", item)


db.close()