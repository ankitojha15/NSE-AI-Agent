from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.models.financial_results import FinancialResult
from app.repositories.financial_result_repository import FinancialResultRepository


def make_filing(seq, qe_date="30-Jun-2026", financial_data=None):
    return {
        "seq_Id": seq,
        "symbol": "TEST",
        "cmName": "Test Company Limited",
        "creation_Date": "01-Jul-2026",
        "qe_Date": qe_date,
        "audited": "Yes",
        "consolidated": "No",
        "xbrl": "http://example.com/xbrl.xml",
        "financial_data": financial_data,
    }


def main():

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    repo = FinancialResultRepository(db)

    # 1. First insert -> created
    result, state = repo.upsert(
        make_filing("1001", financial_data={"sales": 10.0})
    )
    assert state == "created", state
    assert result.seq_number == "1001"
    assert result.financial_data == {"sales": 10.0}

    # 2. Same seq + same data -> unchanged, no duplicate
    _, state = repo.upsert(
        make_filing("1001", financial_data={"sales": 10.0})
    )
    assert state == "unchanged", state
    count = db.query(FinancialResult).filter(
        FinancialResult.seq_number == "1001"
    ).count()
    assert count == 1, f"duplicate created: {count} rows"

    # 3. Existing filing with missing financial_data -> backfilled, not duplicated
    db.query(FinancialResult).filter(
        FinancialResult.seq_number == "1001"
    ).update({"financial_data": None})
    db.commit()

    result, state = repo.upsert(
        make_filing("1001", financial_data={"sales": 12.0, "net_profit": 1.0})
    )
    assert state == "updated", state
    assert result.financial_data == {"sales": 12.0, "net_profit": 1.0}
    count = db.query(FinancialResult).filter(
        FinancialResult.seq_number == "1001"
    ).count()
    assert count == 1

    # 4. create() on an existing seq returns existing instead of crashing
    result = repo.create(
        make_filing("1001", financial_data={"sales": 12.0, "net_profit": 1.0})
    )
    assert result.seq_number == "1001"
    count = db.query(FinancialResult).filter(
        FinancialResult.seq_number == "1001"
    ).count()
    assert count == 1

    # 5. DB-level uniqueness: same seq_number direct insert must fail
    db.add(FinancialResult(seq_number="1001", symbol="X"))
    try:
        db.commit()
        assert False, "expected IntegrityError for duplicate seq_number"
    except IntegrityError:
        db.rollback()
        print("DB unique constraint on seq_number enforced: OK")

    # 6. A genuinely new filing still inserts
    result, state = repo.upsert(
        make_filing("2002", qe_date="31-Mar-2026", financial_data={"sales": 5.0})
    )
    assert state == "created", state
    assert db.query(FinancialResult).count() == 2

    print("FINANCIAL RESULT REPOSITORY IDEMPOTENCY + UNIQUENESS: ALL PASSED")

    db.close()


if __name__ == "__main__":
    main()