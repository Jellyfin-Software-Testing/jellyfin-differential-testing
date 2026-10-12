from utils.jellyfin_api_client import JellyfinAPIClient

def test_jellyfin_client_trace_logging():
    client = JellyfinAPIClient(base_url="http://localhost:8096", version="10.8.13", test_id="G2-05-TEST")
    response = client.get("/System/Info/Public")
    assert response.status_code == 200