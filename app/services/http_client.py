import requests

class HTTPClient:
    """
    A reusable HTTP client for making API requests.

    Why do we need this?
    --------------------
    Instead of creating a new requests.Session() in every service,
    we create it once here and reuse it everywhere.

    Benefits:
    - Reuses the same HTTP connection
    - Maintains cookies automatically
    - Keeps networking code in one place
    """

    def __init__(self):
        """
        Constructor.
        Runs automatically when an object is created.
        """

        # Create a persistent HTTP session.
        self.session = requests.Session()

        # Default headers sent with every request.
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0 Safari/537.36"
            )
        }

    def get(self, url: str):
        """
        Sends an HTTP GET request.

        Parameters
        ----------
        url : str
            The URL to send the request to.

        Returns
        -------
        requests.Response
            The response received from the server.
        """

        # Send a GET request using the same session.
        response = self.session.get(
            url,
            headers=self.headers,
            timeout=30
        )

        # Raise an exception for HTTP errors (404, 500, etc.)
        response.raise_for_status()

        return response