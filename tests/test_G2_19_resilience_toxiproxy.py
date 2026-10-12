import pytest
from toxiproxy import Toxiproxy
from utils.jellyfin_api_client import JellyfinAPIClient

@pytest.fixture(scope="module")
def setup_toxiproxy():
    toxiproxy = Toxiproxy()

    # 1. Lấy danh sách proxy hiện tại
    current_proxies = toxiproxy.proxies()

    # 2. Cleanup proxy cũ nếu tồn tại
    if "jellyfin_v108" in current_proxies:
        current_proxies["jellyfin_v108"].destroy()
    if "jellyfin_v109" in current_proxies:
        current_proxies["jellyfin_v109"].destroy()

    # 3. Tạo proxy mới (Lưu ý: Upstream nội bộ Docker của cả 2 container đều dùng port 8096)
    proxy_v108 = toxiproxy.create(
        name="jellyfin_v108",
        listen="0.0.0.0:8601",
        upstream="jellyfin-v10.8.13-test:8096"
    )

    proxy_v109 = toxiproxy.create(
        name="jellyfin_v109",
        listen="0.0.0.0:8602",
        upstream="jellyfin-v10.9.0-test:8096"  # Đổi 8097 thành 8096
    )

    yield proxy_v108, proxy_v109

    # 4. Cleanup sau khi test
    try:
        proxy_v108.destroy()
    except Exception:
        pass

    try:
        proxy_v109.destroy()
    except Exception:
        pass


def test_resilience_under_network_stress(setup_toxiproxy):
    proxy_v108, proxy_v109 = setup_toxiproxy

    # 1. Inject Latency (Lag 500ms ± 100ms jitter)
    proxy_v108.add_toxic(type="latency", attributes={"latency": 500, "jitter": 100})
    proxy_v109.add_toxic(type="latency", attributes={"latency": 500, "jitter": 100})

    # 2. Khởi tạo client kết nối qua cổng Toxiproxy (8601 & 8602)
    client_v108 = JellyfinAPIClient(base_url="http://localhost:8601", version="10.8.13", test_id="G2-19")
    client_v109 = JellyfinAPIClient(base_url="http://localhost:8602", version="10.9.0", test_id="G2-19")

    # 3. Thực hiện kiểm thử vi sai đường truyền giật lag
    resp_108 = client_v108.get("/System/Info/Public", timeout=10.0)
    resp_109 = client_v109.get("/System/Info/Public", timeout=10.0)

    assert resp_108.status_code == 200, "v10.8 failed under network stress"
    assert resp_109.status_code == 200, "v10.9 failed under network stress"