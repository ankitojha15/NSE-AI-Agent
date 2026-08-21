import csv
from io import StringIO

from sqlalchemy.orm import Session

from app.repositories.company_repository import CompanyRepository
from app.repositories.financial_result_repository import FinancialResultRepository
from app.services.http_client import HTTPClient
from app.services.xbrl_parser import XBRLParser
from app.services.xbrl_service import XBRLService
from app.utils.logger import logger


class NseService:
    """
    Service responsible for communicating with NSE.
    """

    BASE_URL = "https://www.nseindia.com"
    EQUITY_MASTER_URL = (
        "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    )

    def __init__(self):
        """
        Create one reusable HTTP client.
        """
        self.client = HTTPClient()
        self._market_cap_cache = {}

    def get_market_cap(self, symbol: str) -> str | None:
        """
        Fetch market capitalization for a symbol via NSE quote API.

        Returns a formatted string like "₹1,20,500 Cr" or None when
        unavailable. Results are cached per instance to avoid repeated
        NSE calls within a single pipeline run.
        """

        if not symbol:
            return None

        if symbol in self._market_cap_cache:
            return self._market_cap_cache[symbol]

        # NSE quote-equity endpoint; priceInfo may contain market cap
        # fields. We try common keys and fall back to "N/A" gracefully.
        url = f"{self.BASE_URL}/api/quote-equity?symbol={symbol}"

        try:
            response = self.client.get(url)
            data = response.json()

            # NSE quote structure varies; try priceInfo.marketCap etc.
            price_info = data.get("priceInfo") or {}
            market_cap = (
                price_info.get("marketCap")
                or price_info.get("mktCap")
                or data.get("marketCap")
                or data.get("mktCap")
            )

            # Some responses nest under "info" or provide "marketCap" in crores
            if market_cap is None:
                # Try securityWiseDP with market cap?
                market_cap = data.get("securityWiseDP", {}).get("marketCap")

            if market_cap is None:
                self._market_cap_cache[symbol] = None
                return None

            # market_cap from NSE is often in crores already; format
            try:
                value = float(str(market_cap).replace(",", ""))
            except (TypeError, ValueError):
                self._market_cap_cache[symbol] = str(market_cap)
                return str(market_cap)

            # Format as ₹X Cr (Indian grouping)
            # If value is very large (e.g., absolute rupees), convert to crores
            # Heuristic: > 1e10 likely absolute rupees
            if value > 1e10:
                value = value / 1e7

            formatted = f"₹{value:,.2f} Cr"
            self._market_cap_cache[symbol] = formatted
            return formatted

        except Exception:
            self._market_cap_cache[symbol] = None
            return None

    def get_equity_master(self) -> list:
        """
        Fetch the NSE equity master file.

        This is the official list of all companies listed on NSE,
        so no manually maintained company-symbol list is required.

        Returns
        -------
        list
            List of company records (symbol, company_name,
            series, isin).
        """

        response = self.client.get(self.EQUITY_MASTER_URL)

        reader = csv.reader(StringIO(response.text))

        header = None

        for row in reader:

            if not row:
                continue

            # The header row contains the SYMBOL column.
            # Rows before the header (e.g. legacy homepage rows)
            # are skipped.
            if "SYMBOL" not in row:
                continue

            header = [column.strip() for column in row]
            break

        if header is None:
            raise ValueError("NSE equity master header row not found")

        companies = []

        for row in reader:

            if len(row) < len(header):
                continue

            record = dict(zip(header, row))

            companies.append(
                {
                    "symbol": record.get("SYMBOL", "").strip(),
                    "company_name": (
                        record.get("NAME OF COMPANY", "").strip()
                    ),
                    "series": record.get("SERIES", "").strip(),
                    "isin": record.get("ISIN NUMBER", "").strip(),
                }
            )

        return companies

    def sync_listed_companies(self, db: Session):
        """
        Discover NSE-listed companies automatically and store them.

        Companies are matched by their unique symbol so running this
        multiple times never creates duplicates.

        Parameters
        ----------
        db : Session
            Database session.

        Returns
        -------
        dict
            Summary of the sync: fetched, new, updated,
            unchanged, skipped, failed.
        """

        repository = CompanyRepository(db)

        records = self.get_equity_master()

        logger.info(
            "EQUITY MASTER FETCHED | records: %s",
            len(records)
        )

        summary = {
            "fetched": len(records),
            "new": 0,
            "updated": 0,
            "unchanged": 0,
            "skipped": 0,
            "failed": 0,
        }

        for record in records:

            # Only the standard equity series represents
            # regularly listed companies.
            if record.get("series") != "EQ":
                summary["skipped"] += 1
                continue

            if not record.get("symbol"):
                summary["skipped"] += 1
                continue

            try:

                _, state = repository.upsert(record)

                if state == "created":
                    summary["new"] += 1

                elif state == "updated":
                    summary["updated"] += 1

                else:
                    summary["unchanged"] += 1

            except Exception:

                logger.exception(
                    "COMPANY UPSERT FAILED | symbol: %s",
                    record.get("symbol")
                )

                summary["failed"] += 1

        logger.info(
            "COMPANY SYNC COMPLETE | summary: %s",
            summary
        )

        return summary

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

    def get_all_integrated_filings(
        self,
        index: str = "equities",
        size: int = 100,
        max_pages: int = 50
    ):
        """
        Fetch integrated financial filings with automatic pagination.

        Pages are fetched one after another until:
        - a page returns no records, or
        - a page returns fewer records than the requested page size.

        A maximum page limit protects against infinite requests.

        Filings are read only from the NSE response "data" array and
        deduplicated by their sequence number (seq_Id / seqNumber).

        Parameters
        ----------
        index : str
            equities / sme

        size : int
            Number of filings requested per page.

        max_pages : int
            Hard limit on the number of pages fetched.

        Returns
        -------
        list
            Unique integrated filing records.
        """

        unique_records = {}

        page = 1

        while page <= max_pages:

            data = self.get_integrated_financial_results(
                index=index,
                page=page,
                size=size
            )

            records = data.get("data") or []

            logger.info(
                "INTEGRATED FILINGS PAGE %s | records: %s",
                page,
                len(records)
            )

            for record in records:

                seq_id = record.get("seq_Id") or record.get("seqNumber")

                if seq_id:
                    unique_records[seq_id] = record

            # Last page reached when the response is empty
            # or shorter than the requested page size.
            if not records or len(records) < size:
                break

            page += 1

        return list(unique_records.values())

    def discover_new_filings(self, db: Session):
        """
        Discover integrated filings that are not yet stored.

        Reads all integrated filings from NSE (with automatic
        pagination and deduplication) and classifies each filing
        as new or already-stored using the FinancialResultRepository.

        This method never inserts or updates any filing.

        Parameters
        ----------
        db : Session
            Database session.

        Returns
        -------
        dict
            {
                "fetched": int,
                "new": [filings...],
                "existing": [filings...]
            }
        """

        repository = FinancialResultRepository(db)

        records = self.get_all_integrated_filings()

        new_filings = []
        existing_filings = []

        for record in records:

            seq_id = record.get("seq_Id") or record.get("seqNumber")

            if not seq_id:
                logger.warning(
                    "FILING WITHOUT SEQ NUMBER SKIPPED | %s",
                    record.get("symbol")
                )
                continue

            if repository.get_by_seq_number(seq_id):
                existing_filings.append(record)
            else:
                new_filings.append(record)

        logger.info(
            "FILING DISCOVERY COMPLETE | "
            "fetched: %s | new: %s | existing: %s",
            len(records),
            len(new_filings),
            len(existing_filings)
        )

        return {
            "fetched": len(records),
            "new": new_filings,
            "existing": existing_filings,
        }

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