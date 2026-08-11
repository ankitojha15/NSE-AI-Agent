from app.database.database import SessionLocal
from app.services.financial_analysis_service import FinancialAnalysisService
from app.services.financial_insight_service import FinancialInsightService
from app.services.ai_analysis_service import AIAnalysisService


print("### TEST AI ANALYSIS ###")

db = SessionLocal()

# 1. Financial analysis
analysis_service = FinancialAnalysisService(db)
analysis = analysis_service.compare_latest_results("HDFCBANK")

print("\n==============================")
print("FINANCIAL ANALYSIS OBJECT")
print("==============================")

print(analysis)

# 2. Financial insights
insight_service = FinancialInsightService()
insights = insight_service.analyze(analysis)

# 3. Prepare filing information
ai_service = AIAnalysisService()

filing_data = ai_service.prepare_filing_data(
    analysis["latest_raw_data"]
)

# 4. Send financial data + filing information to AI
report = ai_service.analyze({
    "financial_analysis": analysis,
    "financial_insights": insights,
    "filing_data": filing_data
})

print("\n==============================")
print("HDFC Bank AI FINANCIAL ANALYSIS")
print("==============================")

print(report)

db.close()