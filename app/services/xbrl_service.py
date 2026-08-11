from app.services.http_client import HTTPClient


class XBRLService:
    """
    Service responsible for downloading XBRL files from NSE.
    """

    def __init__(self):
        # Reuse our HTTP client
        self.client = HTTPClient()

    def download_xbrl(self, xbrl_url: str) -> str:
        response = self.client.get(xbrl_url)
        return response.text
        """
        Download an XBRL document.

        Parameters
        ----------
        xbrl_url : str
            URL of the XBRL document.

        Returns
        -------
        str
            XML content as a string.
        """  

        response = self.client.get(xbrl_url)

        return response.text