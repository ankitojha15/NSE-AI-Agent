from fastapi import FastAPI
from app.database.database import engine
from app.api.analysis import router as analysis_router
from app.api.company import router as company_router
from app.api.results import router as results_router

app = FastAPI(
    title = "NSE AI Earnings Analysis Agent",
    version = "1.0.0",
    description = "AI-powered agent for analysing NSE company financial results."
)

# Analysis router first so "/companies/search" is not captured by
# the company router's "/companies/{company_id}" route.
app.include_router(analysis_router)
app.include_router(company_router)
app.include_router(results_router)

@app.get("/")
def root():
    return {
        "message":"welcome to the NSE AI Earnings Analysis Agent!"
    }