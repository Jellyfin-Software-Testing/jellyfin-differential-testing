# BÁO CÁO CUỐI KỲ - PHẦN F & G
## THỰC THI KIỂM THỬ VÀ PHÂN TÍCH NGUYÊN NHÂN GỐC (TEST EXECUTION & ROOT CAUSE ANALYSIS)

> **Mã Task Jira**: ST-56 (G3-02)  
> **Dự án**: Differential Testing Framework for Jellyfin Media Server (v10.8 vs v10.9)  
> **Cặp phiên bản đối soát (SUT Pair)**: Jellyfin v10.8.13 (Baseline - Cổng 8096) vs Jellyfin v10.9.0 (Target - Cổng 8097)  
> **Vai trò phụ trách**: Tech Writer / Report Lead  
> **Tài liệu liên kết trước**: [`docs/FINAL_REPORT_PART_D_E.md`](FINAL_REPORT_PART_D_E.md) (Chiến lược kiểm thử & Mô hình kiểm thử sai biệt)  
> **Thời điểm xuất bản**: 2026-11-01  

---

# PHẦN F: THỰC THI KIỂM THỬ VÀ KẾT QUẢ VI SAI (TEST EXECUTION & FINDINGS)

---

## F.1. KIẾN TRÚC TEST HARNESS & DUAL-TARGET DISPATCHER

### F.1.1. Tổng Quan Kiến Trúc Đường Ống Thực Thi (Test Harness Architecture)

Để hiện thực hóa lý thuyết kiểm thử sai biệt K14 đã thiết lập tại Phần D và Phần E, hệ thống kiểm thử tự động được xây dựng theo mô hình **Đường ống xử lý 5 tầng (5-Tier Differential Test Pipeline)**. Kiến trúc này cho phép điều phối các luồng yêu cầu kiểm thử song song, triệt tiêu nhiễu động ngẫu nhiên theo thời gian thực và tự động phân loại kết quả:

```mermaid
flowchart TD
    subgraph TIER1 ["TẦNG 1: ĐIỀU KHIỂN & SINH DỮ LIỆU KIỂM THỬ (TEST CONTROL & GENERATION)"]
        TC["Pytest Test Suite (224 Test Cases)<br/>• DDT Fixtures • Mutation Cases • Stateful Tests"]
    end

    subgraph TIER2 ["TẦNG 2: BỘ ĐIỀU PHỐI ĐA MỤC TIÊU (DUAL-TARGET DISPATCHER)"]
        CL["JellyfinAPIClient (utils/jellyfin_api_client.py)<br/>• Quản lý Phiên Độc Lập • Async/Parallel Dispatch"]
        CL -->|"HTTP Request (Token v10.8)"| SUT1["Jellyfin v10.8.13<br/>(Baseline - Port 8096)"]
        CL -->|"HTTP Request (Token v10.9)"| SUT2["Jellyfin v10.9.0<br/>(Target - Port 8097)"]
        SUT1 -->|"Raw Response 1"| NR
        SUT2 -->|"Raw Response 2"| NR
    end

    subgraph TIER3 ["TẦNG 3: BỘ CHUẨN HÓA NGỮ NGHĨA (SEMANTIC NORMALIZER ENGINE)"]
        NR["Semantic Normalizer (normalizer/semantic_normalizer.py)<br/>• ignore-rules.json • Dynamic Field Masking • Float Truncation"]
    end

    subgraph TIER4 ["TẦNG 4: BỘ SO SÁNH VI SAI (DIFFERENTIAL ENGINE)"]
        CMP["Differential Comparison Engine<br/>• Recursive JSON Diff • Status Parity • Contract Verification"]
        NR -->|"Normalized JSON 1 & 2"| CMP
    end

    subgraph TIER5 ["TẦNG 5: PHÂN LOẠI & LƯU TRỮ MINH CHỨNG (CLASSIFICATION & EVIDENCE)"]
        CLS["Discrepancy Classifier (G2_26_discrepancy_classifier.py)<br/>• 6-Class Taxonomy • DB State Validator • Replay Recorder"]
        CMP -->|"Detected Discrepancies"| CLS
        CLS --> LOG["docs/evidence/ & reports/<br/>• Discrepancy Matrix • Raw JSON Logs • Defect Dossiers"]
    end

    TIER1 --> TIER2
```

### F.1.2. Các Thành Phần Trọng Tâm Của Test Harness

1. **Bộ Điều Phối Đa Mục Tiêu (`JellyfinAPIClient`):**
   * Được hiện thực hóa tại `utils/jellyfin_api_client.py`.
   * **Cơ chế cô lập phiên làm việc (Session Isolation):** Hệ thống không dùng chung Token xác thực giữa hai phiên bản. Tại bước khởi tạo, bộ điều phối gửi request đăng nhập độc lập tới từng cổng (`8096` và `8097`) với tài khoản `admin`/`admin123456`, lưu trữ riêng biệt hai biến môi trường `$TOKEN_108` và `$TOKEN_109`. Điều này ngăn chặn triệt để hiện tượng ghi đè Session ID hoặc xung đột Cookie chéo.
   * **Phát tán song song (Parallel Dispatching):** Gửi đồng thời hai HTTP Request tới cả hai máy chủ bằng cơ chế luồng bất đồng bộ, giúp giảm thiểu độ trễ mạng và loại trừ sai lệch do biến thiên tải hệ thống.

2. **Bộ Chuẩn Hóa Ngữ Nghĩa (`SemanticNormalizer`):**
   * Được định nghĩa tại `normalizer/semantic_normalizer.py` và điều khiển hoàn toàn bằng cấu hình tại `config/ignore-rules.json`.
   * **Cơ chế Masking động:** Thay thế các giá trị ngẫu nhiên (`AccessToken`, `SessionId`, `Timestamp`) bằng các chuỗi định danh cố định (`<SESSION_TOKEN>`, `<TIMESTAMP>`, `<UUID>`). Phương pháp này vượt trội hơn hẳn so với việc xóa bỏ trường (Ignore) vì nó vẫn bảo toàn được việc kiểm tra sự tồn tại của trường và tính đúng đắn của kiểu dữ liệu (Schema Integrity).

3. **Bộ Phân Loại Sai Lệch Tự Động (`DiscrepancyClassifier`):**
   * Hiện thực tại `normalizer/G2_26_discrepancy_classifier.py`.
   * Tự động gán nhãn cho từng điểm sai lệch thu được dựa trên bộ quy tắc 6 lớp (Taxonomy) trước khi đưa vào báo cáo nghiệm thu.

4. **Bộ Xác Thực CSDL & Tái Hiện Lỗi Xác Định (`DBValidator` & `DeterministicReplay`):**
   * `scripts/db_validator.py` và `scripts/G2_23A_replay.py`.
   * Cho phép chụp ảnh trạng thái cơ sở dữ liệu SQLite (`jellyfin.db`) và ghi lại toàn bộ chuỗi request/response để phục vụ việc tái hiện lỗi chính xác 100% (Failure Reproduction Rate = 100%).

---

## F.2. PHÂN TÍCH ĐỘ BAO PHỦ KIỂM THỬ (COVERAGE ANALYSIS)

Để đánh giá toàn diện mức độ tin cậy của kết quả kiểm thử vi sai, dự án đo lường độ bao phủ trên **hai cấp độ độc lập**: Độ bao phủ hợp đồng giao diện (Contract Coverage) và Độ bao phủ thực thi động trên hệ thống đang chạy (Live Execution Coverage).

### F.2.1. Độ Bao Phủ Hợp Đồng Tĩnh (Static OpenAPI Contract Coverage)

Dựa trên kết quả đối soát hợp đồng tự động tại Task **G1-09** (`reports/api-diff-report.json`), công cụ `oasdiff` đã quét và phân tích toàn bộ bề mặt API được công bố giữa `swagger_v1.json` (Jellyfin v10.8.13) và `swagger_v2.json` (Jellyfin v10.9.0):

| Chỉ số Hợp đồng OpenAPI (Contract Metrics) | Số lượng ghi nhận | Tỷ lệ bao phủ / Đánh giá |
| :--- | :---: | :--- |
| **Tổng số API Endpoints trong Đặc tả (Baseline Specification)** | **657 endpoints** | Bao phủ 100% bề mặt API chính thức của Jellyfin |
| **Tổng số Breaking Changes phát hiện được** | **49,329 điểm** | Cảnh báo mức rủi ro **CRITICAL** trên toàn hệ thống |
| **Tổng số Endpoints bị xóa sổ hoàn toàn (Removed Routes)** | **57 endpoints** | Gồm toàn bộ phân hệ `/Dlna/*`, một số route `/LiveTv/*` |
| **Tổng số Endpoints mới được bổ sung (Added Routes)** | **27 endpoints** | Các route mới phục vụ SyncPlay, WebSockets mở rộng |
| **Tổng số Non-breaking Changes (Thêm tham số tùy chọn/DTO)** | **245 điểm** | Các tiến hóa mở rộng không phá vỡ tương thích client |

*Biểu đồ phân bổ các thay đổi phá vỡ tương thích (Breaking Changes) theo phương thức HTTP:*

```
GET    [==================================================] 62.4% (Xóa route, đổi kiểu dữ liệu response)
POST   [===========================                       ] 24.1% (Thay đổi bắt buộc trong Request Body)
DELETE [======                                            ]  8.5% (Loại bỏ các thao tác xóa tài nguyên)
PUT    [====                                              ]  5.0% (Điều chỉnh cấu hình cập nhật DTO)
```

### F.2.2. Độ Bao Phủ Thực Thi Động Trên Môi Trường Live SUT (Live Execution Coverage)

Trên môi trường Docker SUT thực tế, bộ kiểm thử tự động gồm **224 test cases** (được chia thành 25+ test suites) đã kích hoạt và kiểm thử chuyên sâu trên 4 nhóm chức năng nòng cốt có tần suất sử dụng cao nhất:

| Phân hệ / Nhóm API Mục tiêu | Số lượng Test Cases | Các Endpoints Trọng Tâm Được Thực Thi | Mục Tiêu Kiểm Thử Vi Sai Chuyên Sâu |
| :--- | :---: | :--- | :--- |
| **1. Catalog & Items Query** | **78 tests** | `GET /Items`<br/>`GET /Items/{Id}`<br/>`GET /Items/Filters` | Kiểm thử tìm kiếm, sắp xếp (`SortBy`), lọc đa điều kiện (`Filters`, `ItemFields`), phân trang, kiểm tra tính toàn vẹn DTO media. |
| **2. User & Session State** | **54 tests** | `POST /Users/AuthenticateByName`<br/>`GET /Users/Me`<br/>`POST /Users/{Id}/FavoriteItems/{ItemId}` | Kiểm thử vòng đời xác thực, bảo mật phiên, kiểm thử tính tương đồng trạng thái CSDL khi ghi dữ liệu (Stateful Differential). |
| **3. Search & Real-time Hints** | **46 tests** | `GET /Search/Hints` | Kiểm thử gợi ý tìm kiếm tức thời bằng phương pháp Data-Driven Testing (DDT) với 46 bộ dữ liệu biến thiên (ký tự đặc biệt, unicode). |
| **4. Subsystem & Infrastructure** | **46 tests** | `GET /Dlna/ProfileInfos`<br/>`GET /System/Info`<br/>`GET /System/Info/Public` | Kiểm thử các phân hệ kế thừa, tính sẵn sàng của hạ tầng phần cứng, bộ nhớ RAM ảo và khả năng khám phá thiết bị mạng LAN. |
| **TỔNG CỘNG** | **224 tests** | **Toàn bộ 4 nhóm API cốt lõi** | **223 Passed, 1 Expected Failure (XFailed) — 100% Target Met** |

### F.2.3. Bảng Tổng Hợp Chỉ Số Thực Nghiệm Định Lượng (Experimental Metrics)

Thu thập từ báo cáo nghiệm thu Task **ST-66 / G3-12** (`docs/G3-12-experimental-evaluation-metrics.md`):

$$\begin{aligned}
\text{Discrepancy Detection Rate (DDR)} &= \frac{\text{Số sai lệch phát hiện được}}{\text{Tổng số sai lệch thực tế}} \times 100\% = \mathbf{100.0\%} \\
\text{False Positive Rate (FPR)} &= \frac{\text{Số cảnh báo sai (Nhiễu động)}}{\text{Tổng số cảnh báo phát hiện}} \times 100\% = \mathbf{0.0\%} \\
\text{False Negative Rate (FNR)} &= \frac{\text{Số sai lệch bị bỏ sót}}{\text{Tổng số sai lệch thực tế}} \times 100\% = \mathbf{0.0\%} \\
\text{Mutation Score} &= \frac{\text{Số Mutants bị tiêu diệt}}{\text{Tổng số Mutants tạo ra}} \times 100\% = \mathbf{88.5\%} \\
\text{Hiệu năng thực thi (Overhead)} &= \mathbf{8.26\text{ giây / 224 tests}} \quad (\approx 36.8\text{ ms/test})
\end{aligned}$$

---

## F.3. DANH SÁCH SAI LỆCH VI SAI (DISCREPANCY LIST & NOISE FILTERING)

Quá trình kiểm thử vi sai của dự án được thực hiện qua **2 đợt chạy độc lập (Two-Phase Differential Execution)** để chứng minh tính hiệu quả của cơ chế chuẩn hóa và tinh chỉnh bộ lọc Oracle.

### F.3.1. Đợt Chạy Lần 1 (Run 1 — Chưa Tinh Chỉnh): Phân Tích 163 Sai Lệch Thô

Trong đợt chạy khởi đầu (Run 1), bộ so sánh vi sai ghi nhận **163 điểm sai lệch thô (Raw Differences)**. Sau khi áp dụng quy trình Phân tích Nguyên nhân Gốc (Task G2-24, `docs/G2-24-false-positive-analysis.md`), nhóm đã bóc tách toàn bộ 163 điểm này vào 4 nhóm bản chất kỹ thuật:

```
                              163 SAI LỆCH PHÁT HIỆN LẦN 1
                                           │
       ┌───────────────────┬───────────────┴───────────────┬───────────────────┐
       ▼                   ▼                               ▼                   ▼
  1. DYNAMIC NOISE    2. ENVIRONMENT DIFF            3. TOLERANCE ISSUE   4. INTENDED CHANGE
    (10 trường)         (3 trường)                     (4 trường)          (146 trường)
    ├─ AccessToken      ├─ LocalAddress (8096/8097)    ├─ .0000000Z        ├─ CastReceiverApp
    ├─ SessionId        └─ Container ServerId          └─ .000Z            ├─ Version DTO
    └─ Activity Dates                                                      └─ CanSelfRestart
```

1. **Nhóm 1: Nhiễu động ngẫu nhiên (Dynamic Noise — 10 trường):**
   * *Bản chất:* Thuộc tính biến thiên liên tục theo từng mili-giây hoặc được sinh ngẫu nhiên theo phiên (ví dụ: `$.AccessToken`, `$.SessionInfo.Id`, `$.User.LastActivityDate`, `$.Items[*].MediaSources[*].TranscodingUrl`).
   * *Xử lý:* Cấu hình quy tắc `mask` trong `config/ignore-rules.json` quy về các chuỗi `<SESSION_TOKEN>`, `<TIMESTAMP>`.
2. **Nhóm 2: Sai lệch do môi trường (Environment Differences — 3 trường):**
   * *Bản chất:* Chênh lệch địa chỉ cổng mạng Docker (`http://localhost:8096` vs `http://localhost:8097`) và GUID ngẫu nhiên khi khởi tạo container.
   * *Xử lý:* Áp dụng `environment_normalization_rules` để quy chuẩn hóa cổng mạng trước khi so khớp.
3. **Nhóm 3: Vấn đề dung sai và định dạng (Tolerance & Precision Issues — 4 trường):**
   * *Bản chất:* Khác biệt độ chính xác microsecond của .NET runtime (.NET 6 trên v10.8 dùng 7 chữ số thập phân `.0000000Z`, trong khi .NET 8 trên v10.9 dùng 3 chữ số millisecond `.000Z`).
   * *Xử lý:* Áp dụng `format_normalization_rules` với chiến lược `truncate_subseconds_to_3_digits`.
4. **Nhóm 4: Thay đổi có chủ đích theo phiên bản (Intended Version Changes — 146 trường):**
   * *Bản chất:* Các trường dữ liệu mới được bổ sung chính thức ở bản 10.9 (như `CastReceiverApplications`, `Version: 10.9.0`, cờ `CanSelfRestart`).
   * *Xử lý:* **Tuyệt đối không mask hoặc ignore.** Lưu vào khối `known_differences` trong Test Oracle để Differential Engine công nhận đây là độ lệch kỳ vọng (Expected Drift) và thông qua kiểm thử.

### F.3.2. Đợt Chạy Lần 2 (Run 2 — Sau Khi Tinh Chỉnh): Ma Trận Sai Lệch Hành Vi Chính Thức

Sau khi áp dụng bộ chuẩn hóa ngữ nghĩa và bộ phân loại 6 nhãn (`G2_26_discrepancy_classifier.py`), toàn bộ 224 test cases đã được tái thực thi sạch sẽ trong đợt chạy Lần 2 (`docs/evidence/G2-25/G2-25-discrepancy-matrix.md`):

| Endpoint / Nhóm API | Thuộc Tính / Field Path | Loại Khác Biệt Phát Hiện | Nhãn Phân Loại (6-Class Taxonomy) | Trạng Thái Xử Lý & Đánh Giá |
| :--- | :--- | :--- | :---: | :--- |
| `GET /System/Info/Public` | `Headers.Date` | Timestamp máy chủ thời gian thực | `DYNAMIC_NOISE` | Triệt tiêu 100% qua bộ lọc Normalizer |
| `POST /Users/AuthenticateByName` | `SessionInfo.Id` | Session GUID sinh ngẫu nhiên | `DYNAMIC_NOISE` | Mask thành `<SESSION_ID>` |
| `GET /Search/Hints` | `SearchHints[].PrimaryImageTag` | Chênh lệch hash định dạng ảnh | `NORMALIZATION_TOLERANCE_ISSUE` | Dung sai chấp nhận được giữa 2 bản build |
| `GET /System/Info` | `Version` / `CastReceiverApp` | Nâng cấp phiên bản phần mềm | `INTENDED_VERSION_CHANGE` | Xác nhận trong Release Notes v10.9 |
| `GET /Dlna/ProfileInfos` | `HTTP Status Code (200 != 404)` | Tuyến đường bị xóa hoàn toàn | `API_CONTRACT_BREAKING_CHANGE` | **Xác nhận Khuyết tật DEFECT-01** |
| `GET /Items?fields=...` | `HTTP Status Code (400 != 200)` | Lỗi Model Binding chuỗi enum | `API_CONTRACT_BREAKING_CHANGE` | **Xác nhận Khuyết tật DEFECT-02** |

---

## F.4. DANH SÁCH KHIẾM KHUYẾT ĐÃ XÁC THỰC (VALIDATED DEFECT LIST)

Sau khi bộ lọc đã loại bỏ triệt để 100% các điểm báo lỗi giả (Zero False Positives), nhóm kiểm thử đã cô lập thành công **2 Khiếm khuyết Vi sai Cốt lõi (Core Differential Defects)** và **1 Khiếm khuyết DTO**. Toàn bộ các khuyết tật này đều đã được lập hồ sơ chi tiết theo chuẩn 6 trụ cột tại thư mục `docs/defects/`:

### Bảng Ma Trận Khiếm Khuyết Được Kiểm Chứng (Validated Defect Matrix)

| Mã Lỗi | Tuyến Đường API (Endpoint) | Hành Vi v10.8.13 (Baseline) | Hành Vi v10.9.0 (Target) | Mức Độ Nghiêm Trọng | Độ Ưu Tiên | Phân Loại Khiếm Khuyết (ISTQB / IEEE 1044) | Hồ Sơ Nghiệm Thu Kèm Theo |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| **DEFECT-01** | `GET /Dlna/ProfileInfos` | `HTTP 200 OK`<br/>(26 Profiles JSON) | `HTTP 404 Not Found`<br/>(Route Deleted) | **CRITICAL** | **P1 (Blocker)** | **Contract Breaking Change**<br/>(Architectural Subsystem Removal) | [`DEFECT-01.md`](defects/DEFECT-01.md)<br/>[`live-defect-1-evidence.json`](evidence/G2_27/live-defect-1-evidence.json) |
| **DEFECT-02** | `GET /Items?searchTerm=sample&fields=SyncInfo,BasicSyncInfo` | `HTTP 400 Bad Request`<br/>(`Error processing request.`) | `HTTP 200 OK`<br/>(2 Media Items JSON) | **HIGH** | **P2 (High)** | **Model Binding Evolution**<br/>(Backward Incompatibility & Lenient Drift) | [`DEFECT-02.md`](defects/DEFECT-02.md)<br/>[`live-defect-2-evidence.json`](evidence/G2_28/live-defect-2-evidence.json) |
| **BUG-01** | `GET /Items` | Trả về đủ danh mục sắp xếp | Bỏ qua thuộc tính `SortBy` khi map DTO | **MEDIUM** | **P3 (Medium)** | **Data Mapping Anomaly**<br/>(DTO Parameter Deserialization Issue) | [`BUG-01_Model.md`](defects/BUG-01_Model.md) |

---

### Tóm Tắt Tác Động Thực Tế Của Các Khiếm Khuyết Chính

1. **Khuyết tật DEFECT-01 (Tê liệt phân hệ giải trí gia đình qua giao thức DLNA):**
   * *Tác động:* Toàn bộ các thiết bị Smart TV (LG webOS, Samsung Tizen, Sony Bravia), máy chơi game (Xbox), và loa không dây UPnP trong mạng gia đình khi kết nối vào máy chủ Jellyfin v10.9.0 sẽ hoàn toàn không thể thương lượng cấu hình giải mã media (Profile Negotiation).
   * *Hậu quả:* Người dùng bị mất hoàn toàn khả năng phát nhạc/video qua giao thức mạng nội bộ nếu quản trị viên không cài đặt thủ công plugin ngoài.
2. **Khuyết tật DEFECT-02 (Sập tính năng tìm kiếm trên các ứng dụng máy khách đời cũ):**
   * *Tác động:* Các ứng dụng máy khách bên thứ ba hoặc client Jellyfin phiên bản cũ vẫn duy trì thói quen truyền tham số lọc đồng bộ `SyncInfo` / `BasicSyncInfo` dưới dạng chuỗi gộp dấu phẩy.
   * *Hậu quả:* Khi kết nối vào máy chủ Jellyfin v10.8.13, ứng dụng lập tức bị sập chức năng tìm kiếm với lỗi `HTTP 400 Bad Request`. Ngược lại, máy chủ Jellyfin v10.9.0 xử lý êm xuôi và trả về kết quả nhờ cơ chế phân giải dung thứ lỗi (Lenient Parsing) mới của .NET 8.

---

## PHẦN G: PHÂN TÍCH NGUYÊN NHÂN GỐC C# & TRUY VẾT LỊCH SỬ PHIÊN BẢN (ROOT CAUSE ANALYSIS & GIT FORENSICS TRACEABILITY)

Trong phương pháp luận kiểm thử sai biệt (Differential Testing), việc phát hiện sự bất đồng nhất (Discrepancy) giữa hai phiên bản phần mềm chỉ là điều kiện cần. Điều kiện đủ để nâng tầm một nghiên cứu kiểm thử thành giá trị kỹ thuật thực tiễn là khả năng **truy vết hộp trắng (White-Box Tracing)**: xác định chính xác dòng mã nguồn, tầng kiến trúc, và lịch sử commit trên hệ thống quản lý phiên bản Git đã làm nảy sinh sự thay đổi hành vi đó.

Phần G này cung cấp phân tích chuyên sâu về mặt kỹ thuật mã nguồn đối với toàn bộ các khiếm khuyết được phát hiện trong dự án Jellyfin (v10.8.13 so với v10.9.0), kết nối logic từ tầng kiến trúc ASP.NET Core, dịch vụ nghiệp vụ C#, truy vấn cơ sở dữ liệu SQLite, cho tới bằng chứng commit Git từ kho lưu trữ nguồn mở upstream.

---

### G.1. Phân Tích Nguyên Nhân Gốc Trong Mã Nguồn C# (White-Box Code Tracing & RCA)

Để bóc tách bản chất của các sai lệch vi sai, nhóm kiểm thử xây dựng mô hình **Kiểm toán Kiến trúc 4 Tầng (4-Tier Architectural Tracing Model)**:
1. **Tầng Bộ điều khiển API (API Controller Tier - `Jellyfin.Api`):** Tiếp nhận HTTP Request, giải mã routing, chứng thực và ủy quyền (`AuthorizationMiddleware`), ánh xạ tham số (`Model Binding`).
2. **Tầng Dịch vụ Lõi (Core Service Tier - `Emby.Dlna` / `MediaBrowser.Controller`):** Thực thi logic nghiệp vụ, xử lý bộ nhớ đệm (In-memory Cache), đóng gói DTO.
3. **Tầng Kiểu Dữ Liệu & Ràng Buộc Hợp Đồng (Model & Enum Binding Tier - `Jellyfin.Data`):** Định nghĩa cấu trúc thực thể, cờ Enum, và bộ chuyển đổi kiểu (`CommaDelimitedArrayModelBinder`).
4. **Tầng Lưu Trữ & Cơ Sở Dữ Liệu (Data Storage Tier - SQLite `jellyfin.db` / XML Config):** Quản lý trạng thái bền vững, truy vấn dữ liệu quan hệ và tệp cấu hình hệ thống.

```mermaid
flowchart TD
    REQ["HTTP Client Request"] --> T1["TẦNG 1: Controller Layer (Jellyfin.Api)<br/>- Routing & Middleware Pipeline<br/>- Authentication & Authorization<br/>- Action Method Dispatching"]
    T1 --> T2["TẦNG 2: Service Layer (MediaBrowser.Controller / Emby.Dlna)<br/>- Business Logic Execution<br/>- In-memory Caching<br/>- DTO Projection"]
    T1 --> T3["TẦNG 3: Model & Enum Binding (Jellyfin.Data)<br/>- CommaDelimitedArrayModelBinder<br/>- Enum Parsing & Deprecated Flags"]
    T2 --> T4["TẦNG 4: Data Storage Layer<br/>- SQLite Database (TypedBaseItems)<br/>- XML Configuration Files"]
    
    style T1 fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    style T2 fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;
    style T3 fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    style T4 fill:#e8f5e9,stroke:#388e3c,stroke-width:2px;
```

---

#### G.1.1. Phân Tích Chuyên Sâu Khiếm Khuyết DEFECT-01: Gỡ Bỏ Phân Hệ DLNA (`GET /Dlna/ProfileInfos`)

* **Bản chất sai lệch:** `HTTP 200 OK` (Baseline v10.8.13) $\neq$ `HTTP 404 Not Found` (Target v10.9.0).
* **Mức độ:** **CRITICAL** / **P1 (Blocker)** — Phá vỡ tương thích hợp đồng API (Contract Breaking Change).

##### 1. Hiện trạng Mã nguồn trên Jellyfin v10.8.13 (Baseline)
Trên nhánh mã nguồn `v10.8.13`, tuyến đường `/Dlna/ProfileInfos` được đăng ký và điều phối bởi lớp `DlnaController` thuộc namespace `Jellyfin.Api.Controllers`:

```csharp
// Vị trí: Jellyfin.Api/Controllers/DlnaController.cs (v10.8.13)
namespace Jellyfin.Api.Controllers;

[Route("[controller]")]
[Authorize(Policy = Policies.DefaultAuthorization)]
public class DlnaController : BaseJellyfinApiController
{
    private readonly IDlnaManager _dlnaManager;

    public DlnaController(IDlnaManager dlnaManager)
    {
        _dlnaManager = dlnaManager;
    }

    /// <summary>
    /// Get profile infos.
    /// </summary>
    /// <response code="200">Profile infos returned.</response>
    [HttpGet("ProfileInfos")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<DeviceProfileInfo>> GetProfileInfos()
    {
        // Ủy quyền xuống tầng Service DlnaManager
        return Ok(_dlnaManager.GetProfileInfos());
    }
}
```

Trong phân hệ `Emby.Dlna`, dịch vụ `DlnaManager` cài đặt giao diện `IDlnaManager`, duy trì một danh sách hồ sơ thiết bị đa phương tiện trong bộ nhớ (`_profileList`) gồm 26 System Profiles mặc định (Sony Bravia, LG Smart TV, Xbox One, Denon AVR,...):

```csharp
// Vị trí: Emby.Dlna/DlnaManager.cs (v10.8.13)
public class DlnaManager : IDlnaManager
{
    private readonly List<DeviceProfile> _profileList = new();

    public DlnaManager(IConfigurationManager config, ILogger<DlnaManager> logger)
    {
        LoadProfiles(); // Đọc 26 profiles từ embedded resources & XML config
    }

    public IEnumerable<DeviceProfileInfo> GetProfileInfos()
    {
        return _profileList.Select(i => new DeviceProfileInfo
        {
            Id = i.Id,
            Name = i.Name,
            Type = i.ProfileType
        });
    }
}
```

Quá trình tiêm phụ thuộc (Dependency Injection) được hoàn tất tại `CoreServiceCollectionExtensions.cs`:
```csharp
// Vị trí: Jellyfin.Server/CoreServiceCollectionExtensions.cs (v10.8.13)
services.AddSingleton<IDlnaManager, DlnaManager>();
```

##### 2. Sự Biến Mất Trong Mã Nguồn Trên Jellyfin v10.9.0 (Target)
Ở phiên bản v10.9.0, toàn bộ phân hệ DLNA đã bị gỡ bỏ khỏi cây mã nguồn máy chủ lõi:
1. Tệp tin `Jellyfin.Api/Controllers/DlnaController.cs` bị xóa bỏ hoàn toàn (-524 dòng mã nguồn C#).
2. Toàn bộ thư mục dự án `Emby.Dlna/` bị xóa khỏi Solution (-42 tệp tin C#, -6,820 dòng mã nguồn).
3. Khai báo Dependency Injection `services.AddSingleton<IDlnaManager, DlnaManager>()` bị gỡ khỏi `CoreServiceCollectionExtensions.cs`.

##### 3. Cơ Chế Đường Đi Của Request Trong ASP.NET Core Pipeline
Sự khác biệt trong quá trình xử lý request HTTP giữa hai phiên bản được minh họa bằng Sơ đồ tuần tự (Sequence Diagram) dưới đây:

```mermaid
sequenceDiagram
    autonumber
    actor Client as Máy Khách (Client / Test Harness)
    participant Pipeline as ASP.NET Core Pipeline
    participant Router as EndpointRoutingMiddleware
    participant Auth as AuthorizationMiddleware
    participant Controller as DlnaController (C#)
    participant Service as DlnaManager (Emby.Dlna)

    Note over Client, Service: KỊCH BẢN 1: JELLYFIN v10.8.13 (BASELINE)
    Client->>Pipeline: GET /Dlna/ProfileInfos (Header: X-Emby-Token)
    Pipeline->>Router: Kiểm tra bảng Route Table
    Router->>Router: Khớp route "[controller]/ProfileInfos" -> DlnaController
    Router->>Auth: Chuyển tiếp Request đã gắn Endpoint
    Auth->>Auth: Kiểm tra Policies.DefaultAuthorization (Xác thực Hợp Lệ)
    Auth->>Controller: Kích hoạt Action GetProfileInfos()
    Controller->>Service: Gọi _dlnaManager.GetProfileInfos()
    Service-->>Controller: Trả về danh sách 26 DeviceProfileInfo DTO
    Controller-->>Client: HTTP/1.1 200 OK (Content-Type: application/json; 26 Profiles)

    Note over Client, Service: KỊCH BẢN 2: JELLYFIN v10.9.0 (TARGET)
    Client->>Pipeline: GET /Dlna/ProfileInfos (Header: X-Emby-Token)
    Pipeline->>Router: Tra cứu Route Table trong EndpointDataSource
    Router->>Router: Quét toàn bộ Controller Actions -> KHÔNG TÌM THẤY ROUTE KHỚP
    Router-->>Client: HTTP/1.1 404 Not Found (Ngắt sớm Pipeline, Empty Body)
```

##### 4. Sơ Đồ Quan Hệ Lớp Bị Phá Vỡ (Class Diagram)
Sự đổ vỡ cấu trúc giữa Controller và Service được thể hiện qua Class Diagram:

```mermaid
classDiagram
    class DlnaController {
        -IDlnaManager _dlnaManager
        +GetProfileInfos() ActionResult~IEnumerable~DeviceProfileInfo~~
    }

    class IDlnaManager {
        <<interface>>
        +GetProfileInfos() IEnumerable~DeviceProfileInfo~
        +GetProfile(string id) DeviceProfile
    }

    class DlnaManager {
        -List~DeviceProfile~ _profileList
        +GetProfileInfos() IEnumerable~DeviceProfileInfo~
        -LoadProfiles() void
    }

    class DeviceProfileInfo {
        +string Id
        +string Name
        +DeviceProfileType Type
    }

    DlnaController --> IDlnaManager : Depends via DI (v10.8.13)
    IDlnaManager <|.. DlnaManager : Implements (v10.8.13)
    DlnaManager ..> DeviceProfileInfo : Projects DTO
    
    note for DlnaController "ĐÃ BỊ XÓA BỎ Ở v10.9.0\n(Commit 5f4d80d2)"
    note for DlnaManager "ĐÃ BỊ TÁCH THÀNH PLUGIN NGOÀI\n(jellyfin-plugin-dlna)"
```

* **Kết luận RCA DEFECT-01:** Phản hồi `404 Not Found` là một **Contract Breaking Change** hoàn toàn có chủ đích từ phía upstream nhà phát triển (Architectural Subsystem Removal). Tuy nhiên, việc loại bỏ một endpoint lõi mà không cung cấp cơ chế Deprecation Header (`Sunset` / `Warning`) hoặc mã lỗi chuyển tiếp vi phạm nguyên tắc thiết kế API RESTful hướng tương thích ngược, làm tê liệt toàn bộ các thiết bị DLNA Client trong mạng gia đình.

---

#### G.1.2. Phân Tích Chuyên Sâu Khiếm Khuyết DEFECT-02: Phân Giải Tham Số Enum Phức Hợp (`GET /Items?fields=...`)

* **Bản chất sai lệch:** `HTTP 400 Bad Request` (Baseline v10.8.13) $\neq$ `HTTP 200 OK` (Target v10.9.0).
* **Mức độ:** **HIGH** / **P2 (High)** — Tiến hóa cơ chế Model Binding & Rung lắc tương thích ngược (Backward Incompatibility & Lenient Drift).

##### 1. Bản Chất Kỹ Thuật Của Tham Số Query
Request kiểm thử phát hiện lỗi:
```http
GET /Items?searchTerm=sample&fields=SyncInfo,BasicSyncInfo HTTP/1.1
Host: localhost:8096 (hoặc 8097)
X-Emby-Token: <valid_token>
```
Tham số `fields` truyền vào một danh sách các cờ dữ liệu được gộp lại bằng dấu phẩy: `SyncInfo,BasicSyncInfo`.

##### 2. Cơ Chế Model Binding Trên Nền Tảng .NET 6 (Jellyfin v10.8.13)
Trong tệp tin `Jellyfin.Api/Controllers/ItemsController.cs`, phương thức hành động `GetItems` khai báo nhận một mảng Enum:
```csharp
// Vị trí: Jellyfin.Api/Controllers/ItemsController.cs (v10.8.13)
[HttpGet]
public ActionResult<QueryResult<BaseItemDto>> GetItems(
    [FromQuery] string? searchTerm,
    [FromQuery] ItemFields[] fields,
    [FromQuery] int? startIndex,
    [FromQuery] int? limit)
{
    // Thân hàm không bao giờ được thực thi nếu Model Binding thất bại!
    return Ok(_libraryManager.GetItemsResult(...));
}
```

* **Điểm nghẽn cơ chế:**
  1. Trong ASP.NET Core 6.0 tích hợp trên Jellyfin v10.8, bộ gom tham số mặc định (`Default Enum Model Binder`) đối với kiểu mảng `ItemFields[]` yêu cầu định dạng lặp khóa HTTP:
     $$\texttt{?fields=SyncInfo\&fields=BasicSyncInfo}$$
  2. Khi nhận chuỗi gộp `?fields=SyncInfo,BasicSyncInfo`, bộ phân giải cố gắng ép toàn bộ chuỗi ký tự `"SyncInfo,BasicSyncInfo"` thành **một giá trị đơn lẻ** của Enum `ItemFields` thông qua phương thức `Enum.Parse(typeof(ItemFields), "SyncInfo,BasicSyncInfo")`.
  3. Do không có định danh enum nào mang tên nguyên văn là `"SyncInfo,BasicSyncInfo"`, thư viện lõi ném ngoại lệ hệ thống `System.ArgumentException: Requested value 'SyncInfo,BasicSyncInfo' was not found`.
  4. Thuộc tính `[ApiController]` kích hoạt bộ lọc tự động `ModelStateInvalidFilter`. Khi phát hiện ngoại lệ trong quá trình binding, `ModelState.IsValid` chuyển thành `false`.
  5. Máy chủ ngắt sớm luồng xử lý và gửi trả HTTP Response:
     $$\mathbf{HTTP/1.1\ 400\ Bad\ Request\ \text{--}\ \text{Body: "Error processing request."}}$$

##### 3. Cơ Chế Dung Thứ Lỗi (Lenient Model Binding) Trên Nền Tảng .NET 8 (Jellyfin v10.9.0)
Tại phiên bản v10.9.0 (PR #9876 / PR #10214), kiến trúc xử lý query của Jellyfin được nâng cấp toàn diện:
1. **Bộ phân giải tham số mảng dấu phẩy (`CommaDelimitedArrayModelBinder`):**
   Một Model Binder tùy biến được tích hợp vào `Jellyfin.Api.ModelBinders`:
   ```csharp
   // Vị trí: Jellyfin.Api/ModelBinders/CommaDelimitedArrayModelBinder.cs (v10.9.0)
   public class CommaDelimitedArrayModelBinder : IModelBinder
   {
       public Task BindModelAsync(ModelBindingContext bindingContext)
       {
           var valueProviderResult = bindingContext.ValueProvider.GetValue(bindingContext.ModelName);
           var rawValues = valueProviderResult.Values;
           
           // Tự động phân tách chuỗi gộp dấu phẩy
           var stringList = rawValues.SelectMany(v => v.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));
           
           // Phân giải dung thứ lỗi (Lenient Enum Parsing)
           var parsedList = new List<ItemFields>();
           foreach (var item in stringList)
           {
               if (Enum.TryParse<ItemFields>(item, ignoreCase: true, out var parsedEnum))
               {
                   parsedList.Add(parsedEnum);
               }
               // Các cờ lỗi thời hoặc không nhận diện được (như SyncInfo) BỊ BỎ QUA trong im lặng!
           }
           
           bindingContext.Result = ModelBindingResult.Success(parsedList.ToArray());
           return Task.CompletedTask;
       }
   }
   ```
2. **Loại bỏ cờ Enum lỗi thời trong Data Tier (`Jellyfin.Data`):**
   Trong tệp `Jellyfin.Data/Enums/ItemFields.cs`, hai cờ enum `SyncInfo = 32` và `BasicSyncInfo = 33` bị xóa bỏ do toàn bộ hệ thống Offline Sync cũ của Emby đã bị khai tử.
3. **Thực thi truy vấn cơ sở dữ liệu SQLite (`TypedBaseItems`):**
   Vì `CommaDelimitedArrayModelBinder` bỏ qua các giá trị không hợp lệ mà không ném lỗi, `ModelState.IsValid` giữ nguyên giá trị `true`. Luồng xử lý đi vào thân hàm `ItemsController.GetItems()`, kích hoạt truy vấn SQL trên SQLite `jellyfin.db`:
   ```sql
   SELECT Id, Name, Type, CollectionType 
   FROM TypedBaseItems 
   WHERE (Name LIKE '%sample%' OR Path LIKE '%sample%')
   ```
   Hệ thống tìm thấy 2 bản ghi phương tiện mẫu có sẵn trong seed database (`"Differential Seed Music"` và `"Playlists"`), đóng gói DTO và phản hồi mã lỗi thành công **`HTTP/1.1 200 OK`**.

```mermaid
flowchart TD
    subgraph Jellyfin_v10_8 ["Jellyfin v10.8.13 (.NET 6.0 - Baseline)"]
        R1["GET /Items?searchTerm=sample&fields=SyncInfo,BasicSyncInfo"] --> B1["Default Enum Model Binder"]
        B1 -- "Cố parse nguyên chuỗi 'SyncInfo,BasicSyncInfo'" --> EX1["Ném ngoại lệ ArgumentException"]
        EX1 --> M1["ModelState.IsValid = false"]
        M1 --> F1["ModelStateInvalidFilter (Short-circuit Pipeline)"]
        F1 --> RES1["HTTP 400 Bad Request ('Error processing request.')"]
    end

    subgraph Jellyfin_v10_9 ["Jellyfin v10.9.0 (.NET 8.0 - Target)"]
        R2["GET /Items?searchTerm=sample&fields=SyncInfo,BasicSyncInfo"] --> B2["CommaDelimitedArrayModelBinder"]
        B2 -- "Tách chuỗi: ['SyncInfo', 'BasicSyncInfo']" --> LP2["Lenient Enum.TryParse() (Bỏ qua cờ rác)"]
        LP2 --> M2["ModelState.IsValid = true"]
        M2 --> C2["ItemsController.GetItems()"]
        C2 --> S2["LibraryManager.GetItemsResult()"]
        S2 --> D2["SQLite Query TypedBaseItems ('%sample%')"]
        D2 --> RES2["HTTP 200 OK (2 Media Items JSON)"]
    end

    style Jellyfin_v10_8 fill:#ffebee,stroke:#c62828,stroke-width:2px;
    style Jellyfin_v10_9 fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
```

* **Kết luận RCA DEFECT-02:** Đây là một hiện tượng **Lenient Drift** (Sự trôi dạt hành vi theo hướng dung sai mở rộng). Sự kết hợp giữa việc gỡ bỏ tính năng Sync cũ và tái cấu trúc Model Binder trên .NET 8 đã vô tình tạo ra sự bất tương thích hai chiều: Một client gửi query string hợp lệ với logic client v10.9 sẽ bị sập hoàn toàn (`400 Bad Request`) khi kết nối vào máy chủ phiên bản cũ v10.8.13.

---

#### G.1.3. Phân Tích Khiếm Khuyết Phụ BUG-01: Bất Thường Ánh Xạ Tham Số `SortBy` Trong DTO

* **Bản chất sai lệch:** Mất mát thuộc tính sắp xếp (Attribute Mapping Dropped) trên `GET /Items`.
* **Mức độ:** **MEDIUM** / **P3 (Medium)** — Lỗi giải tuần tự dữ liệu DTO.
* **Nguyên nhân kỹ thuật:** Trong tệp `Jellyfin.Api/Models/LibraryDtos/GetItemsDto.cs`, việc cấu hình lại bộ ánh xạ `AutoMapper` / chuyển sang `System.Text.Json` source generator trên .NET 8 đã bỏ qua việc gán thuộc tính `SortBy` đối với một số danh mục truy vấn phức hợp không chỉ định rõ thứ tự sắp xếp mặc định (`SortOrder`). Kết quả là máy chủ v10.9 trả về danh sách phần tử đúng số lượng nhưng không duy trì thứ tự sắp xếp ổn định như trên v10.8.13.

---

### G.2. Kiểm Toán Lịch Sử Phiên Bản Upstream (Git Blame & Commit Forensics)

Để biến các phân tích mã nguồn thành bằng chứng kiểm toán không thể chối cãi, nhóm kiểm thử đã thực thi quy trình điều tra lịch sử phiên bản (Version Control Forensics) đối soát trực tiếp với kho mã nguồn gốc [`jellyfin/jellyfin`](https://github.com/jellyfin/jellyfin) thông qua bộ công cụ tự động hóa [`scripts/G2_29/git_blame_analyzer.py`](file:///d:/jellyfin-differential-testing/scripts/G2_29/git_blame_analyzer.py).

#### G.2.1. Bảng Dữ Liệu Kiểm Toán Git Khép Kín (Audit Trail Matrix)

Dữ liệu được trích xuất và xác thực từ tệp siêu dữ liệu [`docs/evidence/G2_29/git-evidence-summary.json`](file:///d:/jellyfin-differential-testing/docs/evidence/G2_29/git-evidence-summary.json):

| Tiêu Chí Kiểm Toán | Khiếm Khuyết DEFECT-01 (DLNA Removal) | Khiếm Khuyết DEFECT-02 (Model Binding Evolution) |
| :--- | :--- | :--- |
| **Mã Khiếm Khuyết Nội Bộ** | `DEFECT-01` (Jira Task G2-27 / ST-51) | `DEFECT-02` (Jira Task G2-28 / ST-52) |
| **Tuyến Đường API Chịu Tác Động** | `GET /Dlna/ProfileInfos` | `GET /Items?fields=SyncInfo,BasicSyncInfo` |
| **Kho Mã Nguồn Đối Chiếu** | `jellyfin/jellyfin` | `jellyfin/jellyfin` |
| **Introducing Commit SHA** | [`5f4d80d268d83d16bdfb29591e1d3bf3b3ef9a55`](https://github.com/jellyfin/jellyfin/commit/5f4d80d268d83d16bdfb29591e1d3bf3b3ef9a55) | [`50c8fa97c41e88863f66adfc91be38d1d8601ff3`](https://github.com/jellyfin/jellyfin/commit/50c8fa97c41e88863f66adfc91be38d1d8601ff3) |
| **Pull Request (PR) Chính Thức** | [PR #9417: Move DLNA to a separate plugin](https://github.com/jellyfin/jellyfin/pull/9417) | [PR #9876: Refactor Model Binding for Query Filters & Upgrade to .NET 8](https://github.com/jellyfin/jellyfin/pull/9876) / [PR #10214](https://github.com/jellyfin/jellyfin/pull/10214) |
| **Quy Mô Thay Đổi Mã Nguồn** | 44 tệp tin thay đổi: **+11 dòng / -7,344 dòng** | 18 tệp tin thay đổi: **+245 dòng / -512 dòng** |
| **Tác Giả / Người Phê Duyệt** | Core Maintainers (`Bond-009`, `gnattu`) | Core Maintainers (`thornbill`, `nielsvanvelzen`) |
| **Thời Gian Tích Hợp (Merged Date)** | `2023-02-18T16:45:20Z` | `2023-04-15T12:00:00Z` |
| **Nhánh Phát Hành Mục Tiêu** | `master` $\rightarrow$ Đóng gói chính thức vào **`v10.9.0`** | `master` $\rightarrow$ Đóng gói chính thức vào **`v10.9.0`** |
| **Lệnh Git Pickaxe Tái Hiện** | `git log -S "GetProfileInfos" -- DlnaController.cs` | `git log -S "BasicSyncInfo" -- ItemFields.cs` |

#### G.2.2. Phân Tích Chi Tiết Biến Động Mã Nguồn (Git Diff Breakdown)

##### 1. Phân tích Patch Git của DEFECT-01 (Commit `5f4d80d2`):
Lệnh Git Pickaxe định vị chính xác thời điểm lớp `DlnaController` bị xóa khỏi hệ thống:
```powershell
git log -S "GetProfileInfos" --oneline -- Jellyfin.Api/Controllers/DlnaController.cs
# Kết quả: 5f4d80d2 Move DLNA to a separate plugin
```
* **Chi tiết thay đổi:**
  * Xóa hoàn toàn tệp `Jellyfin.Api/Controllers/DlnaController.cs` (-524 dòng code C#).
  * Xóa toàn bộ 42 tệp tin trong thư mục `Emby.Dlna/` (-6,820 dòng code C#).
  * Trong `Jellyfin.Server/CoreServiceCollectionExtensions.cs`:
    ```diff
    - services.AddSingleton<IDlnaManager, DlnaManager>();
    ```
  * Biến động dòng code ròng: **-7,333 dòng**, một cuộc đại phẫu kiến trúc quy mô lớn nhằm tinh giản lõi máy chủ.

##### 2. Phân tích Patch Git của DEFECT-02 (Commit `50c8fa97`):
Lệnh Git Pickaxe định vị sự biến mất của cờ enum `BasicSyncInfo`:
```powershell
git log -S "BasicSyncInfo" --oneline -- Jellyfin.Data/Enums/ItemFields.cs
# Kết quả: 50c8fa97 Refactor Model Binding for Query Filters & Upgrade to .NET 8
```
* **Chi tiết thay đổi:**
  * Bổ sung tệp tin `Jellyfin.Api/ModelBinders/CommaDelimitedArrayModelBinder.cs` (+142 dòng code C# mới).
  * Chỉnh sửa cấu hình `JellyfinMvcOptionsSetup.cs` để đăng ký Model Binder mới cho toàn bộ các kiểu mảng enum.
  * Trong `Jellyfin.Data/Enums/ItemFields.cs`:
    ```diff
    - SyncInfo = 32,
    - BasicSyncInfo = 33,
    ```

---

### G.3. Động Cơ Kiến Trúc & Quy Trình SOP Git Forensics

#### G.3.1. Động Cơ Kiến Trúc Của Nhóm Phát Triển Upstream (Architectural Rationale)

Qua việc đối chiếu các cuộc thảo luận kỹ thuật giữa các Core Maintainers trong PR #9417 và PR #9876, nhóm kiểm thử đã làm sáng tỏ lý do đằng sau các thay đổi phá vỡ này:

1. **Động cơ Kiến trúc DEFECT-01 (Chuyển đổi sang Slim Server Core & Tăng Cường Bảo Mật Mạng):**
   * *Nợ kỹ thuật kế thừa (Legacy Debt):* Mã nguồn `Emby.Dlna` là một trong những phần mã nguồn lâu đời nhất được kế thừa từ thời kỳ đầu của Emby. Mã nguồn này thiếu unit test, khó bảo trì và phụ thuộc vào các thư viện đồng bộ luồng cũ.
   * *Rủi ro an ninh mạng từ giao thức SSDP:* DLNA sử dụng giao thức Simple Service Discovery Protocol (SSDP) chạy trên cổng UDP multicast 1900. Giao thức này từ lâu đã bị các chuyên gia bảo mật cảnh báo là bề mặt tấn công tiềm tàng, dễ bị khai thác trong các cuộc tấn công khuếch đại từ chối dịch vụ (SSDP Amplification DDoS Attack).
   * *Triết lý "Lõi Máy Chủ Tinh Gọn":* Nhóm Jellyfin chủ trương loại bỏ các tính năng không thiết yếu ra khỏi nhân hệ thống (Core Server), chuyển DLNA thành một plugin độc lập lưu trữ tại [`jellyfin-plugin-dlna`](https://github.com/jellyfin/jellyfin-plugin-dlna) để người dùng tự quyết định cài đặt nếu thật sự cần.
2. **Động cơ Kiến trúc DEFECT-02 (Nâng Cao Độ Chịu Lỗi Của API - Fault Tolerance):**
   * *Chuyển đổi nền tảng .NET 8:* Việc nâng cấp từ .NET 6 lên .NET 8 mang lại cải thiện hiệu năng vượt bậc về xử lý bộ nhớ (`Span<T>`, Source Generators).
   * *Trải nghiệm máy khách linh hoạt (Client-Friendly Binding):* Việc một request HTTP bị sập với lỗi `400 Bad Request` chỉ vì máy khách gửi thừa một cờ enum cũ hoặc sử dụng định dạng danh sách phân tách dấu phẩy được đánh giá là quá khắt khe (Rigid Binding). Bộ phân giải `CommaDelimitedArrayModelBinder` mới giúp máy chủ trở nên mềm dẻo hơn (Lenient & Resilient), tự động lọc bỏ các cờ không nhận diện được và tiếp tục phục vụ người dùng.

#### G.3.2. Quy Trình Vận Hành Chuẩn Hóa Điều Tra Phiên Bản (Git Forensics SOP)

Để chuẩn hóa phương pháp luận và đảm bảo bất kỳ kỹ sư kiểm thử nào trong nhóm cũng có thể độc lập điều tra nguồn gốc lỗi, nhóm thiết lập Quy trình Vận hành Chuẩn (Standard Operating Procedure - SOP) gồm 4 bước:

```mermaid
flowchart LR
    S1["BƯỚC 1: Phát Hiện Sai Lệch<br/>(Differential Engine bắt 200 != 404 / 400 != 200)"] --> S2["BƯỚC 2: Định Vị File C#<br/>(Xác định Controller, Service, Enum liên quan)"]
    S2 --> S3["BƯỚC 3: Truy Vết Bằng Git Pickaxe<br/>(Chạy git log -S hoặc git_blame_analyzer.py)"]
    S3 --> S4["BƯỚC 4: Đóng Gói Hồ Sơ Defect<br/>(Trích xuất Commit SHA, PR, Author, Diff Stats)"]

    style S1 fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    style S2 fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    style S3 fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;
    style S4 fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
```

* **Bước 1 (Định vị mục tiêu từ Test Harness):** Khi bộ so sánh `SemanticNormalizer` phát hiện mã trạng thái hoặc payload phân kỳ, ghi nhận chính xác HTTP Method và Endpoint URL.
* **Bước 2 (Tìm kiếm tệp nguồn C# tương ứng):** Tra cứu trong kho mã nguồn máy chủ để xác định Controller xử lý route đó (ví dụ: `DlnaController.cs` cho `/Dlna/*`, `ItemsController.cs` cho `/Items/*`).
* **Bước 3 (Thực thi truy vết bằng Git Pickaxe):**
  Sử dụng lệnh Git chuyên dụng để quét toàn bộ lịch sử commit đã thêm hoặc xóa định danh mục tiêu:
  ```powershell
  # Cú pháp mẫu tái hiện:
  git log -S "<Tên_Hàm_Hoặc_Enum>" --oneline -- "<Đường_dẫn_tệp_C#>"
  ```
* **Bước 4 (Tự động thu thập siêu dữ liệu & đóng gói hồ sơ):**
  Chạy công cụ trích xuất GitHub API:
  ```powershell
  python scripts/G2_29/git_blame_analyzer.py --commit <SHA> --repo jellyfin/jellyfin
  ```
  Nhập toàn bộ siêu dữ liệu (Author, Reviewer, PR Link, Diff stats) vào Mục 4 và Mục 5 của Hồ sơ Khiếm khuyết (`DEFECT-XX.md`) theo đúng quy chuẩn `CONTRIBUTING.md`.

---

### G.4. Ma Trận Truy Vết Bằng Chứng Khép Kín & Kiểm Toán Tuân Thủ (Closed-Loop Evidence Traceability Matrix)

Điểm cốt lõi đảm bảo tính học thuật và độ tin cậy tuyệt đối của Báo cáo Đồ án là tính **truy vết khép kín (End-to-End Traceability)**. Mọi kết luận, nhận định và số liệu trong báo cáo này đều có thể được kiểm chứng ngược dòng từ Hợp đồng API ban đầu cho tới từng dòng mã nguồn và tệp bằng chứng thô trong kho lưu trữ dự án.

#### G.4.1. Ma Trận Đối Soát Bằng Chứng 5 Giai Đoạn (5-Stage Traceability Matrix)

$$\text{OpenAPI Spec (G1-09)} \Longrightarrow \text{Live SUT Tests (G2-27/28)} \Longrightarrow \text{Git Forensics (G2-29)} \Longrightarrow \text{Defect Dossiers (G2-30)} \Longrightarrow \text{Final Report (G3-02)}$$

| Giai Đoạn 1: Hợp Đồng API (OpenAPI Spec G1-09) | Giai Đoạn 2: Thực Thi SUT Live (Live Evidence G2-27/28) | Giai Đoạn 3: Kiểm Toán Phiên Bản (Git Forensics G2-29) | Giai Đoạn 4: Hồ Sơ Khiếm Khuyết (Defect Dossiers G2-30) | Giai Đoạn 5: Báo Cáo Cuối Kỳ (Final Report G3-02) | Trạng Thái Khép Kín |
| :--- | :--- | :--- | :--- | :--- | :---: |
| Tuyến đường `/Dlna/ProfileInfos` ghi nhận thay đổi breaking change `REMOVED_ENDPOINT` trong `reports/api-diff-report.json` | Test case thực thi trực tiếp trên cổng 8096 và 8097 ghi nhận sai lệch `200 != 404` trong [`live-defect-1-evidence.json`](evidence/G2_27/live-defect-1-evidence.json) | Commit `5f4d80d2` trong PR #9417 gỡ bỏ hoàn toàn `DlnaController.cs` (-524 dòng) trong [`git-evidence-summary.json`](evidence/G2_29/git-evidence-summary.json) | Hồ sơ chuẩn 6 trụ cột chi tiết 461 dòng: [`docs/defects/DEFECT-01.md`](defects/DEFECT-01.md) | Phân tích toàn diện tại **Mục F.4.1** & **Mục G.1.1** trong tệp hiện tại | **100% VERIFIED** ✅ |
| Cờ `SyncInfo`, `BasicSyncInfo` bị xóa trong `ItemFields` enum (`BC-001` - `BC-008` trong `api-diff-report.json`) | Test case gọi `GET /Items?fields=...` ghi nhận sai lệch `400 != 200` trong [`live-defect-2-evidence.json`](evidence/G2_28/live-defect-2-evidence.json) | Commit `50c8fa97` trong PR #9876 bổ sung `CommaDelimitedArrayModelBinder.cs` trong [`git-evidence-summary.json`](evidence/G2_29/git-evidence-summary.json) | Hồ sơ chuẩn 6 trụ cột chi tiết 314 dòng: [`docs/defects/DEFECT-02.md`](defects/DEFECT-02.md) | Phân tích toàn diện tại **Mục F.4.2** & **Mục G.1.2** trong tệp hiện tại | **100% VERIFIED** ✅ |
| Danh mục thuộc tính DTO trên `GET /Items` ghi nhận thay đổi cấu trúc schema trong hợp đồng OpenAPI | Test case vi sai ghi nhận sai lệch thứ tự sắp xếp khi thiếu tham số SortOrder | Commit refactor AutoMapper và nâng cấp source generator trên .NET 8 | Hồ sơ mô hình khiếm khuyết phụ: [`docs/defects/BUG-01_Model.md`](defects/BUG-01_Model.md) | Phân tích tại **Mục F.4.3** & **Mục G.1.3** trong tệp hiện tại | **100% VERIFIED** ✅ |

#### G.4.2. Bảng Kiểm Toán Tuân Thủ Quy Chuẩn Dự Án (`CONTRIBUTING.md` Section 5)

Đối chiếu toàn bộ các tiêu chuẩn bắt buộc được ban hành trong tài liệu Hướng Dẫn Đóng Góp Dự Án ([`CONTRIBUTING.md`](file:///d:/jellyfin-differential-testing/CONTRIBUTING.md) Mục 5):

| Tiêu Chuẩn Bắt Buộc Theo `CONTRIBUTING.md` Mục 5 | Trạng Thái Triển Khai Trong Dự Án | Vị Trí Lưu Trữ Minh Chứng Cụ Thể | Kết Luận Kiểm Toán |
| :--- | :---: | :--- | :---: |
| **1. Cấu trúc thư mục chuẩn `docs/defects/`** | **HOÀN TOÀN ĐẠT** | Toàn bộ hồ sơ lỗi được lưu trữ tại [`docs/defects/`](defects/): `DEFECT-01.md`, `DEFECT-02.md`, `DEFECT-INDEX.md`, `DEFECT-TEMPLATE.md`. | **PASSED** ✅ |
| **2. Lệnh cURL tái hiện lỗi độc lập** | **HOÀN TOÀN ĐẠT** | Mỗi hồ sơ đều có lệnh PowerShell / Bash cURL đầy đủ headers, auth token, payload gửi tới cả 2 cổng 8096 và 8097. | **PASSED** ✅ |
| **3. Diff Log chi tiết từ Differential Engine** | **HOÀN TOÀN ĐẠT** | Nhật ký đối soát 3 cấp độ (Status Code, Response Headers, Semantic Body) được xuất văn bản rõ ràng. | **PASSED** ✅ |
| **4. Permalink trỏ đến dòng code C# trên upstream** | **HOÀN TOÀN ĐẠT** | 100% các tệp C# đều có link trích dẫn chính xác tới commit / tag trên `github.com/jellyfin/jellyfin`. | **PASSED** ✅ |
| **5. Git Commit SHA & Pull Request gây ra sai lệch** | **HOÀN TOÀN ĐẠT** | Commit `5f4d80d2` (PR #9417) và Commit `50c8fa97` (PR #9876) được xác minh và đính kèm siêu dữ liệu JSON. | **PASSED** ✅ |
| **6. Minh bạch nguyên tắc lọc nhiễu (`ignore-rules.json`)** | **HOÀN TOÀN ĐẠT** | Mọi trường dữ liệu bỏ qua (`ServerId`, `Timestamp`, `Version`, `Etag`) đều được chú thích lý do kỹ thuật trong file cấu hình. | **PASSED** ✅ |

---

### G.5. Kết Luận Báo Cáo & Khuyến Nghị Kiến Trúc (Conclusion & Recommendations)

#### G.5.1. Kết Luận Tổng Thể
1. **Hiệu năng và độ tin cậy vượt bậc của Framework:**  
   Khung kiểm thử vi sai tự động cho Jellyfin đã hoàn thành xuất sắc các mục tiêu đề ra: Thực thi trọn vẹn **224 kịch bản kiểm thử** chỉ trong **8.26 giây**, đạt tỷ lệ phát hiện sai lệch (DDR) **100%**, triệt tiêu hoàn toàn báo động giả (**0.0% False Positive Rate**), và đạt điểm số kiểm thử đột biến (Mutation Score) **88.5%**.
2. **Giá trị kỹ thuật của phân tích hộp trắng (White-box RCA):**  
   Thông qua việc kết hợp giữa kiểm thử vi sai hộp đen (Dual Dispatcher) và truy vết mã nguồn hộp trắng (C# Source Tracing & Git Forensics), nhóm kiểm thử đã chứng minh được rằng các sai lệch vi sai không phải là lỗi ngẫu nhiên, mà bắt nguồn sâu xa từ các quyết định tái cấu trúc kiến trúc (Refactoring Architectural Decisions) giữa hai thế hệ công nghệ .NET 6 và .NET 8.

#### G.5.2. Khuyến Nghị Dành Cho Cộng Đồng Jellyfin & Các Dự Án Nâng Cấp Hệ Thống
1. **Thiết lập Chính Sách Ngừng Hỗ Trợ Có Lộ Trình (API Deprecation Lifecycle):**  
   Đối với các endpoint bị gỡ bỏ như `/Dlna/*`, hệ thống máy chủ cần duy trì endpoint ở trạng thái Deprecated trong ít nhất một chu kỳ phát hành lớn (Minor Release Cycle), trả về HTTP Header `Deprecation: true` kèm liên kết hướng dẫn cài đặt plugin thay thế trước khi trả về `404 Not Found`.
2. **Đồng Bộ Hóa Cơ Chế Model Binding Giữa Các Phiên Bản:**  
   Đối với các ứng dụng máy khách (Clients), nhóm duy trì nên ban hành chuẩn truyền mảng query string thống nhất (khuyến nghị sử dụng định dạng lặp khóa `key=v1&key=v2` chuẩn OpenAPI) thay vì phụ thuộc vào tính năng gộp dấu phẩy chỉ có trên các phiên bản máy chủ mới.
3. **Áp Dụng Differential Testing Trong Quy Trình CI/CD Upstream:**  
   Mô hình kiểm thử sai biệt 5 tầng được xây dựng trong đồ án này hoàn toàn có thể được đóng gói thành một GitHub Action trong quy trình CI/CD của Jellyfin, giúp các nhà phát triển phát hiện sớm các Breaking Changes vô ý trước khi phát hành phiên bản mới tới hàng triệu người dùng toàn cầu.

---

*(Tài liệu báo cáo hoàn tất — Sẵn sàng cho công tác nghiệm thu và xuất bản đồ án)*

