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
        period: str = "Quarterly",
        symbol: str = None,
        from_date: str = None,
        to_date: str = None
    ):
        """
        Fetch financial results from NSE.

        Parameters
        ----------
        index : str
            equities / sme

        period : str
            Quarterly / Half-Yearly / Annual

        symbol : str
            Optional company symbol.

        from_date : str
            Optional start date in DD-MM-YYYY format.

        to_date : str
            Optional end date in DD-MM-YYYY format.

        Returns
        -------
        list
            List of financial result records.
        """

        url = (
            f"{self.BASE_URL}"
            f"/api/corporates-financial-results"
            f"?index={index}"
            f"&period={period}"
        )

        if symbol:
            url += f"&symbol={symbol}"

        if from_date:
            url += f"&from_date={from_date}"

        if to_date:
            url += f"&to_date={to_date}"

        response = self.client.get(url)
        print("REQUEST URL:", url)

        return response.json()

    def get_integrated_financial_results(
        self,
        index: str = "equities",
        page: int = 1,
        size: int = 20
    ):
        """
        Fetch latest integrated financial filings from NSE.
        No company symbol is required.
        """

        url = (
            f"{self.BASE_URL}"
            f"/api/integrated-filing-results"
            f"?index={index}"
            f"&type=Integrated%20Filing-%20Financials"
            f"&page={page}"
            f"&size={size}"
        )

        response = self.client.get(url)

        return response.json()

    def get_one_year_integrated_filings(
        self,
        index: str = "equities",
        pages: int = 20,
        size: int = 100
    ):
        """
        Fetch enough integrated filings to cover approximately
        one year of NSE financial results.
        """

        all_records = []

        for page in range(1, pages + 1):

            data = self.get_integrated_financial_results(
                index=index,
                page=page,
                size=size
            )

            records = data.get("data", [])

            if not records:
                break

            all_records.extend(records)

            print(
                f"FETCHED PAGE {page} | "
                f"RECORDS: {len(records)}"
            )

        return all_records

    def sync_integrated_filings(self, db: Session):
        """
        Automatically fetch latest NSE integrated filings,
        download XBRL, extract financial data, and store results.
        """

        repository = FinancialResultRepository(db)

        data = self.get_integrated_financial_results()
        records = data.get("data", [])

        new_records = []

        xbrl_service = XBRLService()
        parser = XBRLParser()

        for record in records:

            seq_id = record.get("seq_Id")

            record["seq_Id"] = seq_id

            if not seq_id:
                continue

            existing_result = repository.get_by_seq_number(seq_id)

            if existing_result:
                if not existing_result.financial_data and record.get("xbrl"):

                    try:
                        xml = xbrl_service.download_xbrl(
                            record["xbrl"]
                        )

                        root = parser.parse(xml)

                        financial_data = parser.extract_financial_data(
                            root
                        )

                        repository.update_financial_data(
                            seq_id,
                            financial_data
                        )

                        print(
                            f"XBRL UPDATED: "
                            f"{record.get('symbol')} | "
                            f"SEQ: {seq_id}"
                        )

                    except Exception as e:
                        print(
                            f"XBRL UPDATE FAILED: "
                            f"{record.get('symbol')} | "
                            f"SEQ: {seq_id} | "
                            f"{e}"
                        )

                continue

            result = {
                "seqNumber": seq_id,
                "symbol": record.get("symbol"),
                "company_name": record.get("cmName"),
                "filing_date": record.get("creation_Date"),
                "period": record.get("qe_Date"),
                "audited": record.get("audited"),
                "consolidated": record.get("consolidated"),
                "xbrl": record.get("xbrl"),
                "raw_data": record
            }

            # Automatically process XBRL
            if record.get("xbrl"):

                try:
                    xml = xbrl_service.download_xbrl(
                        record["xbrl"]
                    )

                    root = parser.parse(xml)

                    financial_data = parser.extract_financial_data(
                        root
                    )

                    result["financial_data"] = financial_data

                    print(
                        f"XBRL PROCESSED: "
                        f"{record.get('symbol')} | "
                        f"SEQ: {seq_id}"
                    )

                except Exception as e:

                    print(
                        f"XBRL FAILED: "
                        f"{record.get('symbol')} | "
                        f"SEQ: {seq_id} | "
                        f"{e}"
                    )

            repository.create(result)

            new_records.append(record)

            print(
                f"NEW RESULT: "
                f"{record.get('symbol')} | "
                f"{record.get('cmName')} | "
                f"SEQ: {seq_id}"
            )

        return new_records


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

    def backfill_company_history(
        self,
        db: Session,
        symbol: str,
        from_date: str,
        to_date: str
    ):
        """
        Fetch historical financial results for a company
        and store filings that are not already in the database.
        """

        repository = FinancialResultRepository(db)

        results = self.get_financial_results(
            symbol=symbol,
            from_date=from_date,
            to_date=to_date
        )

        new_results = []

        xbrl_service = XBRLService()
        parser = XBRLParser()

        for result in results:

            # Skip filings already stored.
            if repository.exists(result.get("seqNumber")):
                continue

            # Parse XBRL when available.
            if result.get("xbrl"):

                try:
                    xml = xbrl_service.download_xbrl(result["xbrl"])

                    print("XBRL DOWNLOADED:", result.get("symbol"))
                    print("XML LENGTH:", len(xml))

                    root = parser.parse(xml)

                    financial_data = parser.extract_financial_data(root)

                    print("EXTRACTED FINANCIAL DATA:", financial_data)

                    result["financial_data"] = financial_data

                except Exception as e:
                    print(
                        f"Failed to parse XBRL for "
                        f"{result.get('symbol')}: {e}"
                    )

            # Store the historical filing.
            repository.create(result)

            new_results.append(result)

        return new_results

    def sync_financial_results(self, db: Session):
        """
        Fetch the latest NSE financial results and store new filings.

        If a filing already exists but its financial_data is missing,
        automatically download and parse its XBRL data and update
        the existing database record.

        Returns
        -------
        list
            Newly inserted financial results.
        """

        # Create the repository so we can read/write
        # financial results in the database.
        repository = FinancialResultRepository(db)

        # Get the latest financial results from NSE.
        results = self.get_financial_results()

        # Keep track of completely new records that we insert.
        new_results = []

        # Create these services once and reuse them.
        # We don't want to create them again for every company.
        xbrl_service = XBRLService()
        parser = XBRLParser()

        # Process every financial result returned by NSE.
        for result in results:

            # Get the unique NSE sequence number.
            seq_number = result.get("seqNumber")

            # ---------------------------------------------------------
            # CHECK WHETHER THIS FILING ALREADY EXISTS
            # ---------------------------------------------------------

            # Get the existing database record, if one exists.
            existing_result = repository.get_by_seq_number(
                seq_number
            )

            # If the filing already exists...
            if existing_result:

                # Check whether financial data is missing.
                #
                # Example:
                # INFY SEQ 1189815 already existed,
                # but financial_data was None.
                if not existing_result.financial_data:

                    # We can only extract financial data if
                    # NSE provides an XBRL URL.
                    if result.get("xbrl"):

                        try:

                            # Download the XBRL XML file from NSE.
                            xml = xbrl_service.download_xbrl(
                                result["xbrl"]
                            )

                            # Convert XML text into an XML tree.
                            root = parser.parse(xml)

                            # Extract financial metrics from XBRL.
                            financial_data = (
                                parser.extract_financial_data(
                                    root
                                )
                            )

                            # Update the existing database record
                            # instead of creating a duplicate record.
                            repository.update_financial_data(
                                seq_number,
                                financial_data
                            )

                            print(
                                f"Updated financial data for "
                                f"{result.get('symbol')} "
                                f"(SEQ: {seq_number})"
                            )

                        except Exception as e:

                            # If XBRL processing fails, print the error
                            # but allow the synchronization to continue.
                            print(
                                f"Failed to update financial data for "
                                f"{result.get('symbol')}: {e}"
                            )

                # The filing already exists.
                #
                # Therefore, do NOT insert it again.
                continue

            # ---------------------------------------------------------
            # NEW FILING
            # ---------------------------------------------------------

            # This filing does not exist in our database.
            # We therefore process its XBRL data before inserting it.
            if result.get("xbrl"):

                try:

                    # Download the XBRL XML document.
                    xml = xbrl_service.download_xbrl(
                        result["xbrl"]
                    )

                    # Convert XML into an ElementTree root.
                    root = parser.parse(xml)

                    # Extract financial metrics.
                    financial_data = (
                        parser.extract_financial_data(
                            root
                        )
                    )

                    # Attach the extracted financial data
                    # to the NSE result before saving it.
                    result["financial_data"] = financial_data

                except Exception as e:

                    # If XBRL extraction fails, keep the original
                    # NSE record but show the error.
                    print(
                        f"Failed to parse XBRL for "
                        f"{result.get('symbol')}: {e}"
                    )

            # ---------------------------------------------------------
            # INSERT NEW RECORD
            # ---------------------------------------------------------

            # Save the completely new filing in the database.
            repository.create(result)

            # Keep track of newly inserted records.
            new_results.append(result)

        # Return only records that were newly inserted.
        return new_results