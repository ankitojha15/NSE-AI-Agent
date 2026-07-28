from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyResponse

router = APIRouter(
    prefix="/companies",
    tags=["Companies"]
)


@router.post("/", response_model=CompanyResponse)
def create_company(
    company: CompanyCreate,
    db: Session = Depends(get_db)
):
    db_company = Company(
        symbol=company.symbol,
        company_name=company.company_name,
        sector=company.sector,
        industry=company.industry,
        isin=company.isin,
        listing_status=company.listing_status
    )

    db.add(db_company)
    db.commit()
    db.refresh(db_company)

    return db_company