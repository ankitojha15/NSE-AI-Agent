from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.models.company import Company
from app.repositories.company_repository import CompanyRepository


def main():

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    repo = CompanyRepository(db)

    # 1. First insert creates
    company, state = repo.upsert({
        "symbol": "TCS",
        "company_name": "Tata Consultancy Services Limited",
        "series": "EQ",
        "isin": "INE467B01029",
    })
    assert state == "created", state
    assert company.id is not None

    # 2. Same symbol again -> unchanged, no duplicate
    _, state = repo.upsert({
        "symbol": "TCS",
        "company_name": "Tata Consultancy Services Limited",
        "series": "EQ",
        "isin": "INE467B01029",
    })
    assert state == "unchanged", state
    count = db.query(Company).filter(Company.symbol == "TCS").count()
    assert count == 1, f"duplicate created: {count} rows"

    # 3. Name change -> updated, still one row
    company, state = repo.upsert({
        "symbol": "TCS",
        "company_name": "TATA Consultancy Services Limited",
        "series": "EQ",
        "isin": "INE467B01029",
    })
    assert state == "updated", state
    assert company.company_name == "TATA Consultancy Services Limited"
    count = db.query(Company).filter(Company.symbol == "TCS").count()
    assert count == 1

    # 4. DB-level uniqueness: same symbol direct insert must fail
    db.add(Company(symbol="TCS", company_name="Duplicate", isin="INE000000000"))
    try:
        db.commit()
        assert False, "expected IntegrityError for duplicate symbol"
    except IntegrityError:
        db.rollback()
        print("DB unique constraint on symbol enforced: OK")

    # 5. DB-level uniqueness: same ISIN different symbol must fail
    db.add(Company(symbol="OTHER", company_name="Dup", isin="INE467B01029"))
    try:
        db.commit()
        assert False, "expected IntegrityError for duplicate ISIN"
    except IntegrityError:
        db.rollback()
        print("DB unique constraint on ISIN enforced: OK")

    print("COMPANY REPOSITORY IDEMPOTENCY + UNIQUENESS: ALL PASSED")

    db.close()


if __name__ == "__main__":
    main()