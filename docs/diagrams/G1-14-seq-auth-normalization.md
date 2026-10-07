# Sơ đồ 2: Authentication & Token Normalization

**Mô tả:** Sơ đồ này làm rõ vai trò tối quan trọng của thành phần Normalizer. Nhờ áp dụng In-memory Masking Rules, các tham số biến động như AccessToken và ServerId được che đi trước khi thực hiện đối chiếu sâu (Mức 3).

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

    Note over InputGen, Reporter: Luồng 2: Authentication & Token Normalization (Stateful Data)
    
    InputGen->>Dispatcher: Nạp kịch bản đăng nhập: POST /Users/AuthenticateByName
    
    par Phát Request Song Song
        Dispatcher->>API1: Gửi Request R (Username/Password)
        Dispatcher->>API2: Gửi Request R (Username/Password)
    end
    
    API1-->>Normalizer: Raw Response 1 (200 OK, AccessToken_A, ServerId_A)
    API2-->>Normalizer: Raw Response 2 (200 OK, AccessToken_B, ServerId_B)
    
    Note over Normalizer: Áp dụng In-memory Masking Rules (Regex/Hardcode logic)<br/>thay vì đọc từ config/ignore-rules.json (do file này chưa tồn tại)
    
    Normalizer->>Normalizer: Replace Token_A, Token_B -> <MASKED_TOKEN>
    Normalizer->>Normalizer: Replace ServerId_A, ServerId_B -> <MASKED_SERVER_ID>
    
    Normalizer->>Comparator: Chuyển 2 JSON payload đã làm sạch (Normalized Data)
    
    Comparator->>Comparator: So sánh Mức 3: Deep Semantic JSON Body Diff
    Note over Comparator: KHỚP NHAU (MATCH): Cấu trúc & giá trị tĩnh đều trùng khớp
    
    Comparator->>Reporter: Ghi nhận Pass (Không có Defect)
```
