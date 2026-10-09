# Formal Differential Test Model - Task G2-01

## 1. Mục tiêu
Xây dựng mô hình kiểm thử hộp đen để kiểm chứng sự khác biệt (Differential Testing) giữa Swagger v1 (`specs/swagger_v1.json`) và Swagger v2 (`specs/swagger_v2.json`).

## 2. Kỹ thuật áp dụng & Test Cases mẫu (Cho API Items/Users)

### A. Equivalence Partitioning (Phân vùng tương đương - EP)
Chia dữ liệu đầu vào (ví dụ: tham số `limit` hoặc `id`) thành các phân vùng:
- **Hợp lệ (Valid):** `limit` nhận giá trị từ 1 đến 50.
- **Không hợp lệ (Invalid):** `limit` nhận giá trị `< 1` (ví dụ: 0, âm) hoặc `> 50` (ví dụ: 51), hoặc truyền chuỗi ký tự thay vì số.

### B. Boundary Value Analysis (Phân tích giá trị biên - BVA)
Kiểm thử tại các giá trị biên của tham số `limit` (Min = 1, Max = 50):
- Biên dưới: `limit = 0`, `limit = 1`, `limit = 2`
- Biên trên: `limit = 49`, `limit = 50`, `limit = 51`

### C. Negative Testing (Kiểm thử tiêu cực)
- Gửi request thiếu Token xác thực (Unauthorized).
- Truyền sai định dạng JSON body hoặc thiếu các trường bắt buộc (Required fields).
- Gọi API với `id` không tồn tại trong cơ sở dữ liệu.

### D. State Testing (Kiểm thử trạng thái)
- Kiểm tra trạng thái của Item/User qua các bước: `Draft` -> `Active` -> `Inactive` -> `Deleted`, xem phản hồi từ API v1 và v2 có khớp nhau (Parity Verification) hay không.