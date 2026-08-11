from app.database.database import SessionLocal
from app.services.financial_analysis_service import FinancialAnalysisService


# ---------------------------------------------------------
# Create database session
# ---------------------------------------------------------
db = SessionLocal()

# ---------------------------------------------------------
# Create financial analysis service
# ---------------------------------------------------------
service = FinancialAnalysisService(db)

# ---------------------------------------------------------
# Analyze TCS
# ---------------------------------------------------------
analysis = service.analyze_company("TCS")

# ---------------------------------------------------------
# Print the complete analysis result
# ---------------------------------------------------------
print("\n==============================")
print("TCS FINANCIAL ANALYSIS")
print("==============================")

print(analysis)

# ---------------------------------------------------------
# Close database connection
# ---------------------------------------------------------
db.close()