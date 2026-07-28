from fastapi import FastAPI
from app.database.database import engine

app = FastAPI(
    title = "NSE AI Earnings Analysis Agent",
    version = "1.0.0",
    description = "AI-powered agent for analysing NSE company financial results."
)

@app.get("/")
def root():
    return {
        "message":"welcome to the NSE AI Earnings Analysis Agent!"
    }