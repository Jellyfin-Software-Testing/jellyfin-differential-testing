# Tài Liệu Mô Tả Kiến Trúc Hệ Thống (Architecture Documentation)
## Jellyfin Media Server và Differential Testing Framework (Component và Diff Level)

**Mã Nhiệm Vụ (Task ID)**: G1-13  
**Dự Án**: Jellyfin Differential Testing Framework  
**Tập Tin Sơ Đồ Đi Kèm**:
* **Sơ đồ 1 (Component Level)**: [`jellyfin-component-architecture.puml`](jellyfin-component-architecture.puml)
* **Sơ đồ 2 (Diff Level)**: [`jellyfin-differential-architecture.puml`](jellyfin-differential-architecture.puml)

---

## 1. Tổng Quan và Bố Cục Kiến Trúc Hai Cấp Độ

Để đáp ứng yêu cầu của đề bài "G1-13: Vẽ sơ đồ kiến trúc hệ thống Jellyfin và vị trí tương tác của Differential Testing Framework", tài liệu kỹ thuật này được tổ chức thành hai sơ đồ kiến trúc bổ trợ cho nhau:

* **Sơ đồ 1: Kiến trúc thành phần nội tại Jellyfin (Component Level)**: Đi sâu vào cấu trúc 4 tầng nội bộ của một máy chủ Jellyfin Media Server hoàn chỉnh, làm rõ cách các tầng giao tiếp từ ứng dụng người dùng cuối đến cơ sở dữ liệu và bộ chuyển mã media.
* **Mối liên kết giữa hai hệ thống**: Hai hệ thống được liên kết chặt chẽ thông qua 3 điểm kết nối then chốt:
  * Điểm 1: Tham chiếu tài liệu đặc tả OpenAPI Specification từ tầng API để sinh kịch bản kiểm thử.
  * Điểm 2: Phát các request đồng nhất từ bộ điều phối kép vào cổng API của cả hai phiên bản.
  * Điểm 3: Đối soát trực tiếp trạng thái cơ sở dữ liệu SQLite ngầm tại tầng lưu trữ.
* **Sơ đồ 2: Khung kiểm thử vi sai và tương tác đa phiên bản (Diff Level)**: Thể hiện vị trí Framework kiểm thử vi sai tương tác với hai container Jellyfin chạy song song trong môi trường Docker (phiên bản v10.8 và v10.9), cơ chế lọc nhiễu động và phát hiện các điểm sai lệch.

---

### 2. Thuyết Minh 4 Tầng Nội Tại Của Jellyfin

#### Tầng 1: Client Layer (Giao diện và ứng dụng người dùng cuối)
* **Web UI (jellyfin-web)**: Ứng dụng Single-Page Application (SPA) chạy trên trình duyệt web, giao tiếp với máy chủ thông qua REST API và WebSocket.
* **Mobile, TV và Desktop Apps**: Các ứng dụng native trên các nền tảng Android, iOS, Android TV, Apple TV, Kodi và Roku.
* **Third-party SDKs**: Các bộ thư viện chính thức và cộng đồng phát triển (TypeScript, Kotlin, Swift, Python) dùng để lập trình các ứng dụng kết nối.

#### Tầng 2: API Layer (Jellyfin.Api - ASP.NET Core)
* **Authentication Middleware**: Tiếp nhận mọi request, kiểm tra tính hợp lệ của người dùng qua Header token (X-Emby-Token), API Key hoặc cơ chế QuickConnect.
* **REST API Controllers**: Tập hợp các controller xử lý hơn 340 endpoints (v10.8) và hơn 355 endpoints (v10.9) theo chuẩn đặc tả OpenAPI 3.0.
* **WebSocket Handler**: Kênh giao tiếp hai chiều thời gian thực để cập nhật tiến trình phát media và phục vụ tính năng điều khiển từ xa (Remote Control).

#### Tầng 3: Core Business Logic Layer (Emby.Server.Implementations)
* **LibraryManager**: Quét ổ đĩa, trích xuất và đồng bộ thông tin metadata (đạo diễn, diễn viên, thể loại) từ các nguồn dữ liệu bên ngoài (TheMovieDb, TheOpenDb).
* **PlaybackManager**: Đánh giá khả năng tương thích của thiết bị Client (codec, bitrate, container) để quyết định phát trực tiếp (Direct Play), đóng gói lại (Remux) hay thực hiện chuyển mã (Transcode).
* **UserManager**: Quản trị tài khoản người dùng, mật khẩu, quyền truy cập thư viện và chính sách kiểm soát của phụ huynh.
* **SessionManager**: Quản lý phiên hoạt động của từng thiết bị, ghi nhận vị trí thời gian đang xem dở của từng bộ phim.
* **Các hệ thống con theo phiên bản**:
  * DLNA/UPnP Core: Được tích hợp sẵn trong nhân Core ở phiên bản v10.8; đã được tách hoàn toàn thành Plugin độc lập ở phiên bản v10.9.
  * Lyrics Subsystem và Trickplay Subsystem: Hai hệ thống con mới xuất hiện ở phiên bản v10.9 để xử lý lời bài hát và ảnh thumbnail tua video.
* **Plugin System Manager**: Cơ chế mở rộng cho phép bổ sung tính năng mới thông qua giao diện IPlugin mà không cần can thiệp vào mã nguồn Core.

#### Tầng 4: Infrastructure và Storage Layer (Hạ tầng, CSDL và Lưu trữ)
* **SQLite Database (jellyfin.db)**: Cơ sở dữ liệu quan hệ được quản trị qua Entity Framework Core, lưu trữ cấu hình, thông tin người dùng, quyền hạn và danh mục media.
* **File System Storage**: Không gian lưu trữ các tệp tin media thực tế (/media/movies, /media/music).
* **In-memory Cache**: Bộ nhớ đệm lưu tạm metadata và hình ảnh để tăng tốc độ phản hồi và giảm tải đọc ổ cứng.
* **FFmpeg Transcoding Engine**: Ứng dụng dòng lệnh FFmpeg được máy chủ kích hoạt để xử lý chuyển mã video và âm thanh theo thời gian thực.

---

## 3. Ba Điểm Liên Kết Then Chốt Giữa Hai Sơ Đồ (Integration Points)

Điểm giao thoa giữa hệ thống Jellyfin và Khung kiểm thử vi sai được xác định tại 3 vị trí kết nối sau:

| Điểm Liên Kết | Phía Hệ Thống Jellyfin | Phía Testing Framework | Mục Đích Kỹ Thuật |
| :--- | :--- | :--- | :--- |
| **Điểm 1** | OpenAPI Spec (/api-docs/openapi.json) từ Tầng API | Test Dataset và Vector Generator | **Sinh kịch bản tự động**: Framework phân tích cấu trúc OpenAPI của cả hai phiên bản để tự động trích xuất các schema, tham số và sinh ra bộ dữ liệu kiểm thử. |
| **Điểm 2** | Cổng REST API của cả hai Instance (Port 8096 và Port 8097) | Dual Traffic Dispatcher | **Phát request đồng nhất**: Bắn cùng một Request R (giống nhau hoàn toàn về URL, Method, Params, Payload, Headers) tới cả hai phiên bản để kích hoạt xử lý. |
| **Điểm 3** | CSDL SQLite jellyfin.db tại Tầng Lưu trữ | DB State Inspector | **Kiểm tra tác dụng phụ ngầm (Side-Effects)**: Đối soát trực tiếp trạng thái dữ liệu trong các bảng SQLite trước và sau các thao tác ghi (POST, PUT, DELETE) để phát hiện sai lệch ngầm mà API không thể hiện ra response. |

---

## 4. Bảng So Sánh Kiến Trúc Chi Tiết (v10.8.13 và v10.9.11)

Dưới đây là bảng đối chiếu chi tiết giữa hai phiên bản Jellyfin, giải thích nguyên nhân kiến trúc dẫn đến các sai lệch vi sai đã được phát hiện trong dự án:

| Tầng Kiến Trúc | Jellyfin v10.8.13 (Baseline - Port 8096) | Jellyfin v10.9.11 (Target - Port 8097) | Tác Động Trong Kiểm Thử Vi Sai |
| :--- | :--- | :--- | :--- |
| **Client Layer** | Web UI, Mobile Apps, SDKs | Web UI, Mobile Apps, SDKs | Không thay đổi. Framework đóng vai trò thay thế client để gửi request kiểm thử. |
| **REST API Layer** | - Hơn 340 endpoints (OpenAPI 3.0)<br>- Định danh qua URL: /Users/{userId}/... | - Hơn 355 endpoints (OpenAPI 3.0)<br>- Loại bỏ {userId} trên URL, chuyển sang Header X-Emby-Token | **Contract Breaking**: Request gửi kèm {userId} trên URL sẽ trả về mã lỗi 404 trên bản v10.9 (giải thích cho 57 endpoint bị gỡ bỏ ở task G1-09). |
| **Core Business Logic** | - LibraryManager, PlaybackManager<br>- UserManager: Cơ chế xác thực theo URL cũ<br>- DLNA/UPnP Core: Tích hợp trực tiếp trong nhân server | - LibraryManager, PlaybackManager<br>- UserManager: Tái cấu trúc bảo mật<br>- Bổ sung: Lyrics Subsystem và Trickplay Subsystem | **Sai khác nghiệp vụ và tính năng mới**: Xuất hiện thêm 27 endpoint mới về lời bài hát và thumbnail xem trước khi tua video. |
| **Plugin System** | Hệ thống plugin đơn giản, nhiều tính năng đa phương tiện gắn cứng trong Core | DLNA được tách thành Plugin độc lập (không còn nằm trong Core server) | Giải thích nguyên nhân toàn bộ các API thuộc nhóm /Dlna/... bị loại bỏ khỏi core ở bản v10.9. |
| **Database Layer** | SQLite Database (jellyfin.db) Schema v10.8 | SQLite Database (jellyfin.db) Schema v10.9 (nâng cấp thêm bảng và trường mới) | DB State Inspector phát hiện sự khác biệt cấu trúc bảng và dữ liệu ghi ngầm. |
| **Storage Layer** | Thư mục mount /media (chế độ Read-Only) | Thư mục mount /media (chế độ Read-Only) | **Dữ liệu dùng chung**: Đảm bảo cả hai phiên bản cùng đọc một tập dữ liệu media gốc, loại bỏ hoàn toàn sai lệch giả do khác biệt tệp tin. |

---

## 5. Mô Tả Chi Tiết Các Mô-đun Khung Kiểm Thử Vi Sai

* **Test Dataset và Generator**: Lưu trữ bộ dữ liệu kiểm thử (Test Vectors), các chuỗi kịch bản kiểm thử có trạng thái (Stateful Sequences) và hạt giống dữ liệu tái hiện lỗi (Replay Seeds).
* **Dual Traffic Dispatcher**: Đóng vai trò là HTTP Client Wrapper, có nhiệm vụ gửi đồng thời hoặc tuần tự cùng một Request R tới cổng 8096 và 8097, đồng thời ghi nhận thời gian phản hồi của từng bên.
* **Configuration và Masking Rules (config/ignore-rules.json)**: Tập hợp các quy tắc loại bỏ nhiễu động (dynamic noise) không cần so sánh (như DateCreated, LastModified, ServerId, AccessToken) và danh sách các sai lệch đã biết trước (Known Differences).
* **Response Normalizer**: Làm sạch và che giấu (masking) các trường dữ liệu động trước khi đưa vào so sánh, giúp giảm thiểu tối đa tỷ lệ báo lỗi giả (False Positives).
* **Differential Comparator**: Trọng tài so sánh vi sai (Test Oracle), thực hiện đối chiếu theo 3 mức:
  * Mức 1: So sánh mã trạng thái phản hồi HTTP Status Code (ví dụ: 200 so với 404).
  * Mức 2: So sánh Headers và cấu trúc dữ liệu Schema DTO.
  * Mức 3: So sánh ngữ nghĩa sâu của nội dung JSON body (giá trị thuộc tính, thứ tự danh sách sắp xếp).
* **Evidence và Defect Logger**: Ghi nhận toàn bộ sai lệch vào tập tin reports/api-diff-report.json, tự động sinh lệnh curl để tái hiện lỗi và trích xuất đường dẫn mã nguồn C# để lập hồ sơ defect trong thư mục docs/defects/.

---

## 6. Quy Trình Luồng Dữ Liệu Vi Sai 5 Bước (Execution Flow)

1. **Bước 1 (Generate)**: Mô-đun InputGen nạp tập dữ liệu kiểm thử vào bộ điều phối Dual Dispatcher.
2. **Bước 2 (Dispatch - Điểm 2)**: Dual Dispatcher phát cùng một Request R tới cổng 8096 (Jellyfin v10.8) và cổng 8097 (Jellyfin v10.9).
3. **Bước 3 (Capture)**: Framework thu thập hai phản hồi thô:
   * Phản hồi thô Response 1 từ Jellyfin v10.8.
   * Phản hồi thô Response 2 từ Jellyfin v10.9.
4. **Bước 4 (Normalize)**: Bộ Normalizer loại bỏ các trường nhiễu động dựa theo cấu hình ignore-rules.json để thu được hai phản hồi đã làm sạch.
5. **Bước 5 (Compare và Log - Điểm 3)**: Bộ Comparator so sánh hai phản hồi sạch; đồng thời DB State Inspector đối soát snapshot cơ sở dữ liệu SQLite tương ứng. Mọi sai khác vượt ngưỡng cho phép sẽ được ghi nhận vào hồ sơ lỗi.

---

## 7. Hướng Dẫn Mở, Render và Xuất Ảnh

### 8.1. Xem và xuất ảnh bằng Extension PlantUML trong VS Code
1. Mở một trong hai tệp tin:
   * [`jellyfin-component-architecture.puml`](jellyfin-component-architecture.puml) (Sơ đồ 1 - Component Level)
   * [`jellyfin-differential-architecture.puml`](jellyfin-differential-architecture.puml) (Sơ đồ 2 - Diff Level)
2. Nhấn tổ hợp phím `Alt + D` để mở cửa sổ xem trước (Preview) trực tiếp bên cạnh.
3. Nhấp chuột phải vào tệp tin `.puml` và chọn **Export Current Diagram**, sau đó chọn định dạng png hoặc svg để xuất hình ảnh chất lượng cao.

### 8.2. Mở và chỉnh sửa trên trang web Draw.io
1. Truy cập vào trang web: [app.diagrams.net](https://app.diagrams.net/).
2. Trên thanh công cụ, chọn mục **Arrange**, sau đó chọn **Insert**, chọn **Advanced** và chọn **PlantUML**.
3. Sao chép toàn bộ nội dung từ tệp tin `.puml` tương ứng và dán vào ô nhập liệu, sau đó nhấn nút **Insert**.
4. Draw.io sẽ tự động vẽ sơ đồ với các khối hộp và đường kết nối thẳng hàng, không bị giao cắt.
5. Bạn có thể lưu tệp tin dưới định dạng `.drawio` hoặc xuất ra hình ảnh định dạng `.png`.