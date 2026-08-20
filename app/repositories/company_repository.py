from sqlalchemy.orm import Session

from app.models.company import Company


class CompanyRepository:
    """
    Handles all database operations related to companies.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_by_symbol(self, symbol: str):
        """
        Return a company using its unique NSE symbol.
        """
        return (
            self.db.query(Company)
            .filter(Company.symbol == symbol)
            .first()
        )

    def exists(self, symbol: str) -> bool:
        """
        Check whether a company already exists.
        """
        return self.get_by_symbol(symbol) is not None

    def upsert(self, company_data: dict):
        """
        Insert a new company or update an existing one.

        Companies are matched by their unique NSE symbol so the
        same company is never stored twice.

        Returns
        -------
        (Company, str)
            The company record and its state:
            "created", "updated", or "unchanged".
        """

        symbol = company_data.get("symbol")

        existing = self.get_by_symbol(symbol)

        if existing is None:

            company = Company(
                symbol=symbol,
                company_name=company_data.get("company_name"),
                sector=company_data.get("sector"),
                industry=company_data.get("industry"),
                isin=company_data.get("isin"),
                listing_status=company_data.get("listing_status", True)
            )

            self.db.add(company)
            self.db.commit()
            self.db.refresh(company)

            return company, "created"

        changed = False

        if (
            company_data.get("company_name")
            and existing.company_name != company_data["company_name"]
        ):
            existing.company_name = company_data["company_name"]
            changed = True

        if (
            company_data.get("isin")
            and existing.isin != company_data["isin"]
        ):
            existing.isin = company_data["isin"]
            changed = True

        listing_status = company_data.get("listing_status")

        if (
            listing_status is not None
            and existing.listing_status != listing_status
        ):
            existing.listing_status = listing_status
            changed = True

        if changed:
            self.db.commit()
            self.db.refresh(existing)
            return existing, "updated"

        return existing, "unchanged"