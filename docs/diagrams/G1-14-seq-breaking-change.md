# Sơ đồ 1: Breaking Change (Lỗi gỡ bỏ tham số URL)

**Mô tả:** Sơ đồ này minh họa luồng kiểm thử một API đã bị thay đổi kiến trúc ở phiên bản mới (gỡ bỏ `{userId}` trên URL), dẫn đến sai lệch ngay từ cấp độ HTTP Status Code (Mức 1).

```mermaid
sequenceDiagram
    autonumber
    
    participant InputGen as Test Dataset & Vector Generator
    participant Dispatcher as Dual Traffic Dispatcher
    participant API1 as Jellyfin v10.8 (API + Core)
    participant API2 as Jellyfin v10.9 (API + Core)
    participant Normalizer as Response Normalizer
    participant Comparator as Differential Comparator
    participant Reporter as Evidence & Defect Logger

    Note over InputGen, Reporter: Luồng 1: Xử lý Contract Breaking Change (Endpoint gỡ bỏ URL path)
    
    InputGen->>Dispatcher: Nạp test vector: GET /Users/{userId}/Items
    
    par Phát Request Song Song
        Dispatcher->>API1: Gửi Request R (cổng 8096)
        Dispatcher->>API2: Gửi Request R (cổng 8097)
    end
    
    API1-->>Normalizer: Raw Response 1 (200 OK + JSON Data)
    API2-->>Normalizer: Raw Response 2 (404 Not Found)
    
    Note right of Normalizer: Bỏ qua bước làm sạch do có sự chênh lệch lớn về HTTP Status
    
    Normalizer->>Comparator: Chuyển dữ liệu (200 OK vs 404 Not Found)
    
    Comparator->>Comparator: So sánh Mức 1: HTTP Status Code
    Note over Comparator: DIVERGENCE POINT: 200 != 404<br/>Lý do: v10.9 chuyển sang dùng X-Emby-Token
    
    Comparator->>Reporter: Ghi nhận sai lệch API (Contract Breaking)
    Reporter-->>InputGen: Lưu api-diff-report.json & sinh cURL tái hiện lỗi
```
