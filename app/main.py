from fastapi import FastAPI
from app.database.database import engine
from app.api.company import router as company_router

app = FastAPI(
    title = "NSE AI Earnings Analysis Agent",
    version = "1.0.0",
    description = "AI-powered agent for analysing NSE company financial results."
)

app.include_router(company_router)

@app.get("/")
def root():
    return {
        "message":"welcome to the NSE AI Earnings Analysis Agent!"
    }