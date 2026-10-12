import time
import uuid
import logging
import hashlib
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("JellyfinAPIClient")

class JellyfinAPIClient:
    def __init__(self, base_url: str, version: str, test_id: str = "G2-05"):
        self.base_url = base_url.rstrip("/")
        self.version = version
        self.test_id = test_id
        self.env_hash = hashlib.md5(f"{self.base_url}_{self.version}".encode()).hexdigest()[:8]
        self.session = requests.Session()

    def request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        request_id = str(uuid.uuid4())[:8]
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        # Tính thời gian thực thi (Execution Duration)
        start_time = time.perf_counter()
        response = self.session.request(method, url, **kwargs)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Trace Logging theo đúng yêu cầu
        logger.info(
            f"[TRACE] TestID={self.test_id} | RequestID={request_id} | "
            f"Version={self.version} | EnvHash={self.env_hash} | "
            f"Method={method} | Endpoint={endpoint} | Status={response.status_code} | "
            f"Duration={duration_ms}ms"
        )
        return response

    def get(self, endpoint: str, **kwargs):
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs):
        return self.request("POST", endpoint, **kwargs)