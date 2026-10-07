# Sơ đồ 3: Dynamic Logic & Semantic Diff

**Mô tả:** Luồng phức tạp nhất nơi các thành phần nội tại gọi nhau để tính toán Streaming URL. Bộ Normalizer phải dùng Regex phức tạp để xóa các query params biến động, và Comparator phải phân tích sâu để tìm Schema Drift.

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

    Note over InputGen, Reporter: Luồng 3: Streaming URL & Deep Semantic Diff
    
    InputGen->>Dispatcher: Nạp kịch bản: GET /Items/{itemId}/PlaybackInfo
    
    par Phát Request Song Song
        Dispatcher->>API1: Gửi Request (cổng 8096)
        Dispatcher->>API2: Gửi Request (cổng 8097)
    end
    
    Note over API1, API2: Gọi nội bộ xuống PlaybackManager để tính toán luồng stream
    
    API1-->>Normalizer: Raw Response 1 (MediaSources, Streaming URL ngẫu nhiên, Timestamps)
    API2-->>Normalizer: Raw Response 2 (MediaSources, Streaming URL ngẫu nhiên, Timestamps)
    
    Normalizer->>Normalizer: Chạy Regex lọc bỏ Query Param động trong URL (Sessions, Timestamps)
    
    Normalizer->>Comparator: Chuyển 2 JSON payload đã làm sạch
    
    Comparator->>Comparator: So sánh Mức 3: Deep Semantic JSON Body Diff
    Note over Comparator: DIVERGENCE POINT (Mô phỏng): Cấu trúc trường MediaSources<br/>ở bản v10.9 bị đổi kiểu dữ liệu so với v10.8
    
    Comparator->>Reporter: Ghi nhận Schema Drift / JSON Mismatch
    Reporter-->>InputGen: Lưu cảnh báo vào api-diff-report.json
```
