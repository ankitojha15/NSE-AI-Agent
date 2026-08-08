from app.services.http_client import HTTPClient
from app.repositories.financial_result_repository import FinancialResultRepository
from sqlalchemy.orm import Session
from app.services.xbrl_service import XBRLService
from app.services.xbrl_parser import XBRLParser


class NseService:
    """
    Service responsible for communicating with NSE.
    """

    BASE_URL = "https://www.nseindia.com"

    def __init__(self):
        """
        Create one reusable HTTP client.
        """
        self.client = HTTPClient()

    def get_financial_results(
        self,
        index: str = "equities",
        period: str = "Quarterly"
    ):
        """
        Fetch financial results from NSE.

        Parameters
        ----------
        index : str
            equities / sme

        period : str
            Quarterly / Half-Yearly / Annual

        Returns
        -------
        list
            List of financial result records.
        """

        url = (
                    f"{self.BASE_URL}"
                    f"/api/corporates-financial-results"
                    f"?index={index}&period={period}"
                )
        
        response = self.client.get(url)
        
        return response.json()

    def get_company_results(
        self,
        symbol: str,
        index: str = "equities",
        period: str = "Quarterly"
    ):
        """
        Return financial results for a specific company.

        Parameters
        ----------
        symbol : str
            Company symbol (e.g. TCS, INFY).

        Returns
        -------
        list
            Matching financial result records.
        """

        # Get all financial results
        results = self.get_financial_results(
            index=index,
            period=period
        )

        # Store matching records
        company_results = []

        # Check every record
        for record in results:

            # Compare symbols (case-insensitive)
            if record.get("symbol", "").upper() == symbol.upper():
                company_results.append(record)

        return company_results

    def sync_financial_results(self, db: Session):
        """
        Fetch the latest NSE financial results and store only new filings.

        Returns
        -------
        list
            Newly inserted financial results.
        """

        repository = FinancialResultRepository(db)

        results = self.get_financial_results()

        new_results = []

        # Create XBRL services once and reuse them.
        xbrl_service = XBRLService()
        parser = XBRLParser()

        for result in results:

            # Skip the record if it is already stored.
            if repository.exists(result.get("seqNumber")):
                continue

            # Parse XBRL when an XBRL URL is available.
            if result.get("xbrl"):

                try:
                    # Download XBRL file.
                    xml = xbrl_service.download_xbrl(
                        result["xbrl"]
                    )

                    # Parse XML.
                    root = parser.parse(xml)

                    # Extract financial metrics.
                    financial_data = parser.extract_financial_data(root)

                    # Attach parsed financial data to the NSE record.
                    result["financial_data"] = financial_data

                except Exception as e:
                    print(
                        f"Failed to parse XBRL for "
                        f"{result.get('symbol')}: {e}"
                    )

            # Store the new record.
            repository.create(result)

            # Keep track of newly inserted records.
            new_results.append(result)

        return new_results