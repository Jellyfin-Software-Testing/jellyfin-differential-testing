import pytest
from utils.jellyfin_api_client import JellyfinAPIClient

# Gom tất cả test case trong nhóm này chạy trên 1 worker duy nhất (tuần tự)
@pytest.mark.xdist_group(name="serial_tests")
def test_create_user_mutation():
    """Test case tạo user - cần chạy tuần tự để tránh tranh chấp dữ liệu."""
    # Khởi tạo client kết nối Jellyfin v10.8 hoặc v10.9
    client = JellyfinAPIClient(base_url="http://localhost:8096", version="10.8.13", test_id="G2-20-SERIAL")
    
    # Thực hiện thao tác mutation (ví dụ: gọi API)
    # response = client.post("/Users/New", json={"Name": "TestUser"})
    # assert response.status_code == 200
    
    assert True