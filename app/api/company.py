from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyResponse , CompanyUpdate
from fastapi import APIRouter, Depends, HTTPException

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

@router.get("/", response_model=list[CompanyResponse])
def get_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return companies

@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: int,
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == company_id).first()

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found"
        )

    return company

@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: int,
    company: CompanyUpdate,
    db: Session = Depends(get_db)
):
    # Fetch the company from the database using its ID
    db_company = db.query(Company).filter(Company.id == company_id).first()

    # If the company doesn't exist, return HTTP 404
    if db_company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found"
        )

    # Update each field with the new values received from the client
    db_company.symbol = company.symbol
    db_company.company_name = company.company_name
    db_company.sector = company.sector
    db_company.industry = company.industry
    db_company.isin = company.isin
    db_company.listing_status = company.listing_status

    # Save the changes permanently in the database
    db.commit()

    # Reload the object so it contains the latest values from the database
    db.refresh(db_company)

    # Return the updated company as the API response
    return db_company

@router.delete("/{company_id}")
def delete_company(
    company_id: int,
    db: Session = Depends(get_db)
):
    # Fetch the company from the database
    db_company = db.query(Company).filter(Company.id == company_id).first()

    # If the company doesn't exist, return HTTP 404
    if db_company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found"
        )

    # Mark this object for deletion
    db.delete(db_company)

    # Permanently remove it from the database
    db.commit()

    # Return a success message
    return {
        "message": "Company deleted successfully"
    }