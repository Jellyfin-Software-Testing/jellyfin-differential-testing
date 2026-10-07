# Tài Liệu Cấu Trúc Kiến Trúc & Luồng Dữ Liệu Vi Sai
*(Jellyfin Differential Testing Framework - Architecture & Data Flow)*

Tài liệu này đóng vai trò là "Bản đồ hệ thống", giải thích chi tiết chức năng, nhiệm vụ của các thành phần (Components) và phân tích chiều sâu các kịch bản kiểm thử (Sequence Flows) trong dự án.

---

## 🏗️ PHẦN 1: TỔNG QUAN KIẾN TRÚC HỆ THỐNG (G1-13)

Phần này bao gồm 2 bản vẽ thiết kế tĩnh (Static Architecture) mô tả cách hệ thống được xây dựng và liên kết với nhau.

### 1. Kiến trúc Nội tại Jellyfin (`jellyfin-component-architecture.puml`)
**Chức năng:** Mô tả cấu trúc 4 tầng (4-Tier Architecture) của một máy chủ Jellyfin độc lập.
* **Tầng Client:** Nơi phát sinh các request từ Web, App, SDK.
* **Tầng API:** Chịu trách nhiệm xác thực (Authentication Middleware) và điều hướng REST request.
* **Tầng Core Logic:** Trái tim của hệ thống chứa `LibraryManager` (quản lý thư viện), `PlaybackManager` (quản lý phát video) và hệ thống Plugin.
* **Tầng Infrastructure:** Nơi lưu trữ thực tế (SQLite DB, File System) và công cụ chuyển mã (FFmpeg).

### 2. Kiến trúc Khung Kiểm thử Vi sai (`jellyfin-differential-architecture.puml`)
**Chức năng:** Thể hiện cách Differential Framework bao bọc lấy 2 phiên bản Jellyfin (v10.8 và v10.9) để đối chiếu kết quả.
* **InputGen & Dispatcher:** Sinh dữ liệu test từ OpenAPI Spec và bắn cùng lúc 1 request xuống 2 server (nhân bản luồng giao thông).
* **Normalizer (Bộ lọc nhiễu):** Tiền xử lý dữ liệu. Gọt bỏ các trường thời gian, mã định danh động để tránh báo lỗi sai (False Positives).
* **Comparator (Trọng tài vi sai):** Bộ máy so sánh chuyên sâu 3 cấp độ: Status Code (HTTP), Headers, và Deep Semantic JSON Body.
* **Reporter:** Ghi nhận lỗi (Defects) và xuất bằng chứng (Evidence) kèm lệnh cURL tái hiện lỗi.

---

## 🔄 PHẦN 2: PHÂN TÍCH CHI TIẾT CÁC LUỒNG DỮ LIỆU ĐỘNG (G1-14)

Nếu Phần 1 là bản thiết kế tĩnh, thì Phần 2 là hình ảnh hệ thống "đang chạy" (Runtime Data Flow). Ba sơ đồ dưới đây đại diện cho 3 độ khó khác nhau của kỹ thuật kiểm thử vi sai.

### Luồng 1: Xử lý Contract Breaking Change
* **File sơ đồ:** [`G1-14-seq-breaking-change.md`](./G1-14-seq-breaking-change.md)
* **Bối cảnh:** Ở bản cập nhật v10.9, đội ngũ Jellyfin quyết định thay đổi cơ chế xác thực, gỡ bỏ tham số `{userId}` trên URL (chuyển sang dùng header).
* **Chức năng thể hiện:** Minh họa khả năng "Bắt lỗi Mức 1" của Framework. Khi Dispatcher gửi cùng request `GET /Users/{userId}/Items`, bản v10.8 trả về dữ liệu (HTTP 200), nhưng v10.9 từ chối vì không tìm thấy route (HTTP 404).
* **Điểm mấu chốt:** Comparator ngay lập tức chặn lại ở tầng HTTP Status, không cần tốn tài nguyên so sánh nội dung JSON, và log ngay lập tức một lỗi cấu trúc đặc tả (Contract Breaking).

### Luồng 2: Xác thực & Khử Nhiễu (Token Normalization)
* **File sơ đồ:** [`G1-14-seq-auth-normalization.md`](./G1-14-seq-auth-normalization.md)
* **Bối cảnh:** Luồng đăng nhập hệ thống (`POST /Users/AuthenticateByName`).
* **Chức năng thể hiện:** Bắt buộc phải có trong mọi framework vi sai. Mỗi lần gọi API Login, server sẽ sinh ra một chuỗi `AccessToken` và `SessionId` hoàn toàn mới ngẫu nhiên.
* **Điểm mấu chốt:** Thể hiện sức mạnh của **Normalizer**. Trước khi cho Comparator so sánh, Normalizer dùng Regex can thiệp vào payload, thay thế các token ngẫu nhiên bằng một chuỗi tĩnh (ví dụ: `<MASKED_TOKEN>`). Nếu không có bước này, Test case nào cũng sẽ báo lỗi (Failed).

### Luồng 3: Xử lý Logic Động & So sánh Ngữ nghĩa Sâu
* **File sơ đồ:** [`G1-14-seq-playback-dynamic.md`](./G1-14-seq-playback-dynamic.md)
* **Bối cảnh:** Luồng yêu cầu thông tin phát video (`GET /Items/{itemId}/PlaybackInfo`).
* **Chức năng thể hiện:** Đây là luồng xương sống có logic phức tạp nhất. Server phải gọi xuống PlaybackManager, tính toán codec và trả về một khối JSON khổng lồ chứa hàng loạt URL Streaming động.
* **Điểm mấu chốt:** Khẳng định năng lực "So sánh Mức 3 - Deep Semantic Diff". Khung kiểm thử phải bóc tách sâu vào trong mảng `MediaSources`, gỡ bỏ các tham số Timestamp nằm lẫn trong URL (bằng Normalizer), sau đó phát hiện sự trôi dạt dữ liệu (Schema Drift) nếu cấu trúc phân phối media của bản v10.9 bị thay đổi so với v10.8.

---

## 💡 HƯỚNG DẪN XUẤT ẢNH VÀ KẾT XUẤT SƠ ĐỒ

**1. Với sơ đồ Mermaid (File `.md` - G1-14):**
* **Trực tuyến:** Commit đẩy lên GitHub/GitLab, giao diện web sẽ tự động vẽ luồng. Hoặc dán code tại [mermaid.live](https://mermaid.live).
* **Ngoại tuyến (VS Code):** Cài extension `Markdown Preview Enhanced`, ấn `Ctrl + Shift + V` để xem trước, chuột phải vào ảnh chọn **Save Image As (PNG/SVG)**.

**2. Với sơ đồ PlantUML (File `.puml` - G1-13):**
* **Trực tuyến:** Dán nội dung text vào [Draw.io](https://app.diagrams.net) (Insert > Advanced > PlantUML).
* **Ngoại tuyến (VS Code):** Cài extension `PlantUML`, ấn `Alt + D` để render, sau đó chuột phải chọn **Export Current Diagram**.
