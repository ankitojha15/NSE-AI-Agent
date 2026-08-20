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

        self.session = requests.Session()

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0 Safari/537.36"
            )
        }

    def get(self, url: str):
        """
        Sends an HTTP GET request with retry support.

        Parameters
        ----------
        url : str
            The URL to send the request to.

        Returns
        -------
        requests.Response
            The response received from the server.
        """

        last_exception = None

        for attempt in range(3):

            try:
                response = self.session.get(
                    url,
                    headers=self.headers,
                    timeout=30
                )

                response.raise_for_status()

                return response

            except requests.exceptions.ConnectionError as e:

                last_exception = e

                print(
                    f"CONNECTION FAILED | "
                    f"ATTEMPT: {attempt + 1}/3"
                )

        raise last_exception