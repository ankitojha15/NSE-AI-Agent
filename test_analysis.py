from app.database.database import SessionLocal
from app.services.financial_analysis_service import FinancialAnalysisService

db = SessionLocal()

service = FinancialAnalysisService(db)

result = service.compare_latest_results("TCS")

print(result)

db.close()