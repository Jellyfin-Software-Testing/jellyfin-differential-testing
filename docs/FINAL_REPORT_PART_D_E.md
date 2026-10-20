# BÁO CÁO CUỐI KỲ - PHẦN D & E
## CHIẾN LƯỢC KIỂM THỬ VÀ MÔ HÌNH HÓA (TEST STRATEGY & TEST MODEL)
**Mã Task Jira**: ST-55 (G3-01)  
**Dự án**: Differential Testing Framework for Jellyfin Media Server (v10.8 vs v10.9)  

---

## PHẦN D: CHIẾN LƯỢC KIỂM THỬ (TEST STRATEGY)

### D.1. Lý Thuyết K14 Differential Testing (Định Hướng Kiểm Thử Sai Biệt)
Kiểm thử sai biệt (Differential Testing - K14) là phương pháp phát hiện lỗi nâng cao dựa trên nguyên lý so sánh hành vi đầu ra (Responses) của hai hay nhiều hệ thống tương đương khi nhận cùng một tập dữ liệu đầu vào ($I$).

1. **Khái niệm Pseudo-Oracle**:
   Trong các hệ thống phức tạp như Jellyfin, việc xây dựng một Oracle thủ công để dự đoán chính xác phản hồi JSON cho hàng ngàn endpoint là không khả thi. Dự án sử dụng phiên bản **Jellyfin v10.8.13** làm *Pseudo-Oracle* (Oracle giả định) để đối chứng hành vi trực tiếp với phiên bản mục tiêu **Jellyfin v10.9.0**.

2. **Nguyên Lý Tổng Thể**:
   Mọi sai lệch $D$ giữa 2 hệ thống được định nghĩa qua công thức toán học:
   $$D(I) = Normalizer(Response_{v10.8}(I)) \oplus Normalizer(Response_{v10.9}(I))$$
   * Nếu $D(I) = \emptyset$: Hai phiên bản đạt sự tương đồng hành vi tuyệt đối (Behavioral Equivalence).
   * Nếu $D(I) \neq \emptyset$: Xuất hiện sai lệch hành vi. Sai lệch này sẽ tiếp tục được đưa qua *Discrepancy Classifier* để phân loại thành lỗi thực sự (Defect) hoặc sự thay đổi có mục đích (Intended Version Change).

---

### D.2. Phạm Vi Kiểm Thử Và Các API Endpoints Mục Tiêu (Target Endpoints)
Dự án tập trung vào 3 nhóm API trọng tâm (High-Risk API Groups) của Jellyfin đại diện cho các tính năng hệ thống, quản lý dữ liệu người dùng và truy vấn nội dung media:

| Nhóm API | API Endpoint | Phương Thức | Mục Tiêu Kiểm Thử Sai Biệt |
| :--- | :--- | :--- | :--- |
| **Catalog & Items** | `/Items` | `GET` | Kiểm thử truy vấn danh sách, sắp xếp (`SortBy`), lọc theo thuộc tính (`Filters`), và phân trang (`StartIndex`, `Limit`). |
| | `/Items/{Id}` | `GET` | Kiểm thử chi tiết cấu trúc Metadata vật phẩm media giữa v10.8 và v10.9. |
| **User & State** | `/Users/AuthenticateByName` | `POST` | Kiểm thử luồng xác thực, khởi tạo AccessToken và cấu trúc Session Payload. |
| | `/Users/{UserId}/FavoriteItems/{Id}` | `POST` / `DELETE` | Kiểm thử tính đồng bộ trạng thái dữ liệu (Stateful Differential Testing). |
| **Search & Hints** | `/Search/Hints` | `GET` | Kiểm thử tìm kiếm gợi ý thời gian thực bằng kỹ thuật Data-Driven Testing (DDT). |

---

## PHẦN E: MÔ HÌNH KIỂM THỬ VÀ QUY TẮC BIÊN (TEST MODEL & SPECIFICATION)

### E.1. Mô Hình So Sánh Semantic (Semantic Differential Test Model)
Mô hình kiểm thử sai biệt được thiết kế theo kiến trúc xử lý dạng đường ống (Pipeline Architecture) gồm 4 giai đoạn chính:
                  +-----------------------------------+
                  |         Test Suite Execution      |
                  |     (Pytest + Data-Driven DDT)    |
                  +-----------------+-----------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
            v                                               v
+-----------------------+                       +-----------------------+
|  Jellyfin v10.8.13    |                       |  Jellyfin v10.9.0     |
| (Container Port 8096) |                       | (Container Port 8097) |
+-----------+-----------+                       +-----------+-----------+
            |                                               |
            | HTTP Response 1                               | HTTP Response 2
            +-----------------------+-----------------------+
                                    v
                  +-----------------------------------+
                  |    Semantic Normalizer Engine     |
                  |  (Loại bỏ Dynamic Fields & Noise) |
                  +-----------------+-----------------+
                                    v
                  +-----------------------------------+
                  |   Differential Comparison Engine  |
                  |     (So sánh JSON Structure/Diff) |
                  +-----------------+-----------------+
                                    v
                  +-----------------------------------+
                  |  Discrepancy Classifier Model     |
                  |   (Gán nhãn taxonomy 6 loại)      |
                  +-----------------+-----------------+
                                    v
                  +-----------------------------------+
                  | Output: Discrepancy Matrix Report |
                  +-----------------------------------+

1. **Giai đoạn Test Execution**: Khởi tạo và gửi các HTTP Request đồng thời tới cả 2 container v10.8 và v10.9 bằng `JellyfinAPIClient`.
2. **Giai đoạn Semantic Normalization**: Áp dụng các quy tắc khử nhiễu (Dung sai thời gian, UUID, Session, Server-Specific Host) được định nghĩa trong `ignore-rules.json`.
3. **Giai đoạn Differential Comparison**: Áp dụng thuật toán so sánh đệ quy trên cây JSON cấu trúc nhằm phát hiện sự khác biệt về Key, Value, hoặc Data Type.
4. **Giai đoạn Classification**: Gán nhãn tự động cho từng điểm sai lệch vào ma trận sai lệch (Discrepancy Matrix).

---

### E.2. Điều Kiện Bất Biến (Invariants Verification)
Hệ thống kiểm thử duy trì và kiểm tra 3 điều kiện bất biến cốt lõi để đảm bảo tính chính xác của kết quả test:

1. **State Invariant (Bất Biến Trạng Thái Initial)**:
   - Trước khi thực thi bất kỳ kịch bản test nào, trạng thái cơ sở dữ liệu (Database State) và tài nguyên media trên cả hai container v10.8 và v10.9 phải được đồng bộ chính xác 100% qua kịch bản Seeding (`G1-06`).
2. **Schema & Contract Invariant (Bất Biến Hợp Đồng API)**:
   - Các trường dữ liệu định danh thuộc tính cốt lõi (như `Name`, `ServerId`, `Type`) phải giữ nguyên kiểu dữ liệu và ý nghĩa ngữ nghĩa (Semantic Integrity) giữa 2 phiên bản. Nếu kiểu dữ liệu thay đổi (ví dụ: `String` $\rightarrow$ `Int`), hệ thống ghi nhận là vi phạm hợp đồng (`API_CONTRACT_BREAKING_CHANGE`).
3. **Persistent State Consistency Invariant (Bất Biến Trạng Thái Lưu Trữ)**:
   - Các thao tác ghi dữ liệu (như đánh dấu yêu thích Favorite Item) trên v10.8 và v10.9 phải dẫn tới sự thay đổi tương đương trong cơ sở dữ liệu nền (SQLite DB State Verification).

---

### E.3. Giả Định Biên & Dung Sai (Boundary Assumptions & Tolerances)
Dung Sai (Tolerance) hiểu đơn giản là "Độ lệch chấp nhận được"
Toàn bộ mô hình so sánh sai biệt chấp nhận các giả định biên và quy tắc dung sai sau đây để hạn chế tối đa nhiễu giả (False Positives):

1. **Dung Sai Thời Gian & Nhiễu Động (Dynamic Noise Tolerance)**:
   - Các trường thời gian thực như `Date` trong HTTP Header, `ServerTime`, `SystemUpdateTimestamp`, hoặc các ID được sinh ngẫu nhiên theo phiên làm việc (`SessionId`, `AccessToken`) được tự động loại bỏ khỏi quá trình so sánh sai biệt.
2. **Dung Sai Định Dạng Chuỗi (String Format Tolerance)**:
   - Chấp nhận sự chênh lệch nhỏ về chuỗi định dạng băm (Hash string) hoặc khoảng trắng chuẩn hóa trong chuỗi JSON, ví dụ thuộc tính `PrimaryImageTag` giữa các bản dựng khác nhau.
3. **Giới Hạn Mạng & Độ Trễ (Network Latency Boundary)**:
   - Trong các kịch bản thử nghiệm giả lập sự cố mạng (với Toxiproxy - `G2-19`), mọi kết nối có độ trễ vượt quá ngưỡng 5000ms hoặc bị Drop Connection sẽ không bị đánh giá là lỗi chức năng API, mà được tách biệt thành báo cáo thử nghiệm độ chịu lỗi (Resilience & Latency Stress Test).