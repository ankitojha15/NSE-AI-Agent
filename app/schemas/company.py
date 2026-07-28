from pydantic import BaseModel


class CompanyCreate(BaseModel):
    symbol: str
    company_name: str
    sector: str | None = None
    industry: str | None = None
    isin: str | None = None
    listing_status: bool = True


class CompanyResponse(CompanyCreate):
    id: int

    class Config:
        from_attributes = True

class CompanyUpdate(BaseModel):
    symbol: str
    company_name: str
    sector: str | None = None
    industry: str | None = None
    isin: str | None = None
    listing_status: bool = True