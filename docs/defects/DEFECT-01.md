# HỒ SƠ DEFECT #1: GỠ BỎ TOÀN BỘ PHÂN HỆ DLNA VÀ ROUTE /Dlna/ProfileInfos TRONG LÕI SERVER
## (Defect Dossier: HTTP 404 Breaking Route Removal on GET /Dlna/ProfileInfos)

> **Mã lỗi (Defect ID):** `DEFECT-01`  
> **Jira Task:** ST-51 / G2-27 & ST-54 / G2-30 (Document Chi tiết Defect Reports kèm Code Trace)  
> **Cặp phiên bản kiểm thử (SUT Pair):** Jellyfin v10.8.13 (Baseline - Cổng 8096) vs v10.9.0 (Target - Cổng 8097)  
> **Mức độ nghiêm trọng (Severity):** **CRITICAL (Nghiêm trọng - Phá vỡ tương thích ngược / Contract Breaking)**  
> **Độ ưu tiên xử lý (Priority):** **P1 (Khẩn cấp / Chặn hoàn toàn giao thức kết nối DLNA)**  
> **Trạng thái (Status):** **CONFIRMED & ISOLATED ON LIVE SUT (Đã xác thực thực nghiệm 100% trên container)**  
> **Người thực hiện:** Tech Writer / C# Root Cause Analyst  
> **Ngày lập hồ sơ:** 2026-10-23  
> **Minh chứng dữ liệu thô (Raw Evidence):**  
> * Dữ liệu kiểm thử vi sai: [`docs/evidence/G2_27/live-defect-1-evidence.json`](../evidence/G2_27/live-defect-1-evidence.json)  
> * Dữ liệu kiểm toán Git: [`docs/evidence/G2_29/git-evidence-summary.json`](../evidence/G2_29/git-evidence-summary.json)  

---

## 1. MÔ TẢ TỔNG QUAN (EXECUTIVE SUMMARY)

* **Hiện tượng lỗi (Symptom):**  
  Khi thiết bị giải trí gia đình (Smart TV, loa DLNA/UPnP, máy chơi game) hoặc ứng dụng khách gọi endpoint truy vấn danh sách hồ sơ thiết bị đa phương tiện DLNA:
  $$\text{GET } \texttt{/Dlna/ProfileInfos}$$
  * **Phiên bản v10.8.13 (Baseline - Cổng 8096):** Xử lý thành công, trả về mã trạng thái **`HTTP 200 OK`** cùng danh sách 26 thiết bị mẫu (Default, Sony Bravia, Denon AVR, LG Smart TV, Xbox One,...).
  * **Phiên bản v10.9.0 (Target - Cổng 8097):** Trả về mã trạng thái **`HTTP 404 Not Found`**, tuyến đường không còn tồn tại trên server core.

* **Tác động nghiệp vụ (Business Impact):**  
  Toàn bộ các thiết bị kết nối qua giao thức DLNA/UPnP trong mạng nội bộ (LAN) khi kết nối tới Jellyfin v10.9.0 bị mất khả năng phát hiện cấu hình giải mã media (profile negotiation). Nếu người dùng không cài thêm plugin ngoài, tính năng DLNA bị tê liệt hoàn toàn.

---

## 2. CÁC BƯỚC TÁI HIỆN CHI TIẾT (STEPS TO REPRODUCE - PILLAR 1)

### 2.1. Điều kiện tiên quyết (Preconditions):
1. Hai máy chủ Docker SUT đang chạy bình thường:
   * **Baseline v10.8.13:** `http://localhost:8096`
   * **Target v10.9.0:** `http://localhost:8097`
2. Tài khoản quản trị viên mặc định: Username `admin`, Password `admin123456`.
3. Cả hai máy chủ đều đã hoàn tất cấu hình ban đầu (Wizard setup) và nạp dữ liệu kiểm thử đồng nhất theo Task G1-06.

### 2.2. Thứ tự các bước thực hiện (Execution Steps):
* **Bước 1 (Lấy Token Xác thực):** Gửi yêu cầu HTTP POST tới `http://localhost:8096/Users/AuthenticateByName` và `http://localhost:8097/Users/AuthenticateByName` với payload `{"Username": "admin", "Pw": "admin123456"}` để trích xuất `AccessToken` của từng phiên bản.
* **Bước 2 (Gắn Header):** Đính kèm token vừa lấy vào header `X-Emby-Token` và thêm header `Accept: application/json`.
* **Bước 3 (Gửi Request Baseline):** Gửi yêu cầu HTTP GET tới `http://localhost:8096/Dlna/ProfileInfos`.
* **Bước 4 (Gửi Request Target):** Gửi yêu cầu HTTP GET tương tự tới `http://localhost:8097/Dlna/ProfileInfos`.
* **Bước 5 (Quan sát & Đối soát):** Ghi nhận HTTP Status Code và Payload trả về từ cả hai máy chủ.
  * *Kỳ vọng:* Cổng 8096 trả về `200 OK` (Mảng 26 profiles).
  * *Thực tế Target:* Cổng 8097 trả về `404 Not Found` (Body rỗng).

---

## 3. LỆNH cURL TÁI HIỆN LỖI ĐỘC LẬP (STANDALONE cURL COMMANDS - PILLAR 2)

Kỹ sư kiểm thử hoặc lập trình viên có thể copy và chạy độc lập các câu lệnh cURL sau trong Terminal/PowerShell để tái hiện trực tiếp sai lệch vi sai:

### 3.1. Lệnh Lấy Token Nhanh (PowerShell):
```powershell
# Lấy token v10.8 (Cổng 8096)
$TOKEN_108 = (Invoke-RestMethod -Uri "http://localhost:8096/Users/AuthenticateByName" -Method Post -Body '{"Username":"admin","Pw":"admin123456"}' -ContentType "application/json" -Headers @{"X-Emby-Authorization"='MediaBrowser Client="Test", Device="CLI", DeviceId="1", Version="1"'}).AccessToken

# Lấy token v10.9 (Cổng 8097)
$TOKEN_109 = (Invoke-RestMethod -Uri "http://localhost:8097/Users/AuthenticateByName" -Method Post -Body '{"Username":"admin","Pw":"admin123456"}' -ContentType "application/json" -Headers @{"X-Emby-Authorization"='MediaBrowser Client="Test", Device="CLI", DeviceId="1", Version="1"'}).AccessToken
```

### 3.2. Lệnh cURL gọi tới Jellyfin v10.8.13 (Baseline - Cổng 8096):
```bash
curl -i -s -X GET "http://localhost:8096/Dlna/ProfileInfos" \
     -H "Accept: application/json" \
     -H "X-Emby-Token: $TOKEN_108" \
     -H "X-Emby-Authorization: MediaBrowser Client=\"Jellyfin Web\", Device=\"Chrome\", DeviceId=\"test-client\", Version=\"10.8.13\""
```
* **Kết quả trả về:** **`HTTP/1.1 200 OK`**  
* **Content-Type:** `application/json; charset=utf-8`  
* **Payload nhận được (Trích đoạn 3/26 Profiles):**
```json
[
  {
    "Id": "0548fdb9f519fe30bcdd862508a55844",
    "Name": "Default",
    "Type": "System"
  },
  {
    "Id": "72c47176bfef7ca78a9c2ca52f55a94a",
    "Name": "Denon AVR",
    "Type": "System"
  },
  {
    "Id": "04ef774262e6332fb27ebc4fae63dd46",
    "Name": "DirecTV HD-DVR",
    "Type": "System"
  }
]
```

### 3.3. Lệnh cURL gọi tới Jellyfin v10.9.0 (Target - Cổng 8097):
```bash
curl -i -s -X GET "http://localhost:8097/Dlna/ProfileInfos" \
     -H "Accept: application/json" \
     -H "X-Emby-Token: $TOKEN_109" \
     -H "X-Emby-Authorization: MediaBrowser Client=\"Jellyfin Web\", Device=\"Chrome\", DeviceId=\"test-client\", Version=\"10.9.0\""
```
* **Kết quả trả về:** **`HTTP/1.1 404 Not Found`**  
* **Content-Type:** (Header không tồn tại / Không có body)  
* **Payload nhận được:** Rỗng (Empty body - Tuyến đường không được ánh xạ trong ASP.NET Core routing).

---

## 4. NHẬT KÝ ĐỐI SOÁT VI SAI (DIFFERENTIAL ENGINE DIFF LOG - PILLAR 3)

### 4.1. Bảng Đối Soát 3 Cấp Độ (Comparator Output Log):
```text
================================================================================
  DIFFERENTIAL COMPARATOR LOG - DEFECT #1
================================================================================
  Target Endpoint   : GET /Dlna/ProfileInfos
  Authentication    : Bearer X-Emby-Token (Admin role)
--------------------------------------------------------------------------------
  [LEVEL 1: HTTP STATUS CODE] -> DIVERGENCE DETECTED ❌
    - Baseline (v10.8.13) : 200 OK
    - Target   (v10.9.0)  : 404 Not Found
    - Result              : FAIL (Contract Breaking Mismatch: 200 != 404)

  [LEVEL 2: RESPONSE HEADERS]
    - Baseline (v10.8.13) : Content-Type: application/json; charset=utf-8
    - Target   (v10.9.0)  : (Không có header Content-Type)

  [LEVEL 3: JSON BODY SEMANTIC DIFF]
    - Baseline (v10.8.13) : Mảng JSON gồm 26 đối tượng DeviceProfileInfo.
    - Target   (v10.9.0)  : Không có nội dung trả về (Route deleted).
================================================================================
```

### 4.2. Minh Chứng Dữ Liệu Thô (Raw Evidence Artifact):
File minh chứng kết quả đo đạc thực nghiệm độc lập được lưu trữ và kiểm toán tự động tại:
👉 [`docs/evidence/G2_27/live-defect-1-evidence.json`](../evidence/G2_27/live-defect-1-evidence.json)

---

## 5. TRUY VẾT NGUYÊN NHÂN GỐC TRONG MÃ NGUỒN C# (C# SOURCE CODE TRACE - PILLAR 4)

```mermaid
flowchart TD
    subgraph Jellyfin_v10_8 ["Jellyfin v10.8.13 (Baseline - Cổng 8096)"]
        E1["Endpoint: GET /Dlna/ProfileInfos"] --> C1["DlnaController.cs (Jellyfin.Api)"]
        C1 --> S1["IDlnaManager / DlnaManager.cs (Emby.Dlna)"]
        S1 --> D1["Hệ thống Device Profiles XML"]
        D1 --> R1["HTTP 200 OK (26 Profiles)"]
    end

    subgraph Jellyfin_v10_9 ["Jellyfin v10.9.0 (Target - Cổng 8097)"]
        E2["Endpoint: GET /Dlna/ProfileInfos"] --> C2["ASP.NET Core Endpoint Routing"]
        C2 -- "Không tìm thấy DlnaController (Đã bị gỡ bỏ)" --> R2["HTTP 404 Not Found"]
    end
```

### 5.1. Tầng 1: API Controller Layer (`Jellyfin.Api`)

#### 5.1.1. Hiện trạng trên Jellyfin v10.8.13 (Baseline):
* **Vị trí file mã nguồn:** [`Jellyfin.Api/Controllers/DlnaController.cs`](https://github.com/jellyfin/jellyfin/blob/v10.8.13/Jellyfin.Api/Controllers/DlnaController.cs#L143-L150)
* **Khai báo lớp và ánh xạ Routing:**
  ```csharp
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
      /// <returns>An <see cref="ActionResult{IEnumerable}"/> containing the profile infos.</returns>
      [HttpGet("ProfileInfos")]
      [ProducesResponseType(StatusCodes.Status200OK)]
      public ActionResult<IEnumerable<DeviceProfileInfo>> GetProfileInfos()
      {
          return Ok(_dlnaManager.GetProfileInfos());
      }
  }
  ```

#### 5.1.2. Phân tích cơ chế hoạt động của Controller (v10.8.13):
1. **Khớp tuyến đường (Attribute Routing):**
   * Token `[Route("[controller]")]` trên khai báo lớp lấy tên Controller bỏ hậu tố `Controller` $\rightarrow$ ánh xạ tiền tố `/Dlna`.
   * Action method khai báo `[HttpGet("ProfileInfos")]` kết hợp với tiền tố tạo thành mẫu route hoàn chỉnh: `GET /Dlna/ProfileInfos`.
2. **Cơ chế Bảo vệ & Xác thực (Authorization Policy):**
   * Thuộc tính `[Authorize(Policy = Policies.DefaultAuthorization)]` yêu cầu người gọi phải cung cấp định danh hợp lệ (Token Admin/User qua header `X-Emby-Token` hoặc `X-Emby-Authorization`).
   * *Giải thích hiện tượng kiểm thử:* Khi gọi không kèm token, ASP.NET Core chặn tại `AuthorizationMiddleware` và trả về `401 Unauthorized`. Khi có token hợp lệ, request được chuyển tiếp vào Action Method.
3. **Tiêm phụ thuộc (Dependency Injection):**
   * `DlnaController` nhận `IDlnaManager` thông qua Constructor Injection được đăng ký sẵn trong `ServiceCollection`.
   * Controller hoạt động như một tầng giao tiếp mỏng (Thin Controller), không chứa logic nghiệp vụ mà ủy quyền trực tiếp xuống `_dlnaManager.GetProfileInfos()`.
4. **Đóng gói kết quả (ActionResult Packaging):**
   * Kết quả trả về từ Service là danh sách `IEnumerable<DeviceProfileInfo>` được đóng gói trong hàm tiện ích `Ok(...)` của ASP.NET Core $\rightarrow$ sinh ra HTTP Response `200 OK` kèm header `Content-Type: application/json; charset=utf-8`.

#### 5.1.3. Phân tích sự thay đổi ở Jellyfin v10.9.0 (Target):
* **Xóa bỏ hoàn toàn Controller:** Toàn bộ file `DlnaController.cs` đã bị gỡ bỏ khỏi dự án `Jellyfin.Api` trong commit `5f4d80d2` (PR #9417).
* **Đường đi của Request trong ASP.NET Core Pipeline:**

```mermaid
sequenceDiagram
    autonumber
    actor Client as Máy khách (Client / Tester)
    participant Pipeline as ASP.NET Core Middleware Pipeline
    participant Router as EndpointRoutingMiddleware
    participant Auth as AuthorizationMiddleware
    participant Controller as DlnaController (C#)

    Note over Client, Controller: TRƯỜNG HỢP 1: Jellyfin v10.8.13
    Client->>Pipeline: GET /Dlna/ProfileInfos (kèm Bearer Token)
    Pipeline->>Router: Kiểm tra bảng Route Table
    Router->>Router: Khớp mẫu route: [controller]/ProfileInfos -> DlnaController
    Router->>Auth: Chuyển tiếp Request đã gắn Endpoint
    Auth->>Auth: Kiểm tra Policies.DefaultAuthorization (Hợp lệ)
    Auth->>Controller: Kích hoạt Action GetProfileInfos()
    Controller-->>Client: HTTP 200 OK (26 Device Profiles JSON)

    Note over Client, Controller: TRƯỜNG HỢP 2: Jellyfin v10.9.0
    Client->>Pipeline: GET /Dlna/ProfileInfos (kèm Bearer Token)
    Pipeline->>Router: Kiểm tra bảng Route Table
    Router->>Router: Quét toàn bộ EndpointDataSource -> KHÔNG CÓ ROUTE NÀO KHỚP
    Router-->>Client: HTTP 404 Not Found (Short-circuit pipeline)
```

* **Kết luận tầng Controller:**
  * Sai lệch vi sai `200 != 404` bắt nguồn trực tiếp từ việc **xóa bỏ hoàn toàn lớp `DlnaController`** khỏi dự án API ở v10.9.0.
  * Vì route không còn tồn tại trong bảng định tuyến (`EndpointDataSource`), máy chủ v10.9 từ chối request ngay tại tầng `EndpointRoutingMiddleware` trước khi kịp đi tới tầng Xác thực (Authentication) hay tầng Nghiệp vụ (Service Layer).

---

### 5.2. Tầng 2: Core Service Layer (`Emby.Dlna`)

#### 5.2.1. Cấu trúc Giao diện và Lớp Triển khai (v10.8.13):
* **Giao diện dịch vụ:** [`Emby.Dlna/IDlnaManager.cs`](https://github.com/jellyfin/jellyfin/blob/v10.8.13/Emby.Dlna/IDlnaManager.cs)
  Định nghĩa hợp đồng quản lý phân hệ DLNA trong server core:
  ```csharp
  namespace Emby.Dlna;

  public interface IDlnaManager
  {
      /// <summary>
      /// Gets the profile infos.
      /// </summary>
      /// <returns>An IEnumerable of DeviceProfileInfo.</returns>
      IEnumerable<DeviceProfileInfo> GetProfileInfos();

      DeviceProfile GetProfile(string id);
      DeviceProfile GetProfile(DeviceIdentification deviceIdentification);
      // ... các phương thức quản lý server UPnP và SSDP
  }
  ```

* **Lớp triển khai dịch vụ:** [`Emby.Dlna/DlnaManager.cs`](https://github.com/jellyfin/jellyfin/blob/v10.8.13/Emby.Dlna/DlnaManager.cs#L85-L135)
  ```csharp
  namespace Emby.Dlna;

  public class DlnaManager : IDlnaManager
  {
      private readonly IConfigurationManager _config;
      private readonly ILogger<DlnaManager> _logger;
      private readonly IFileSystem _fileSystem;
      private readonly List<DeviceProfile> _profileList = new();

      public DlnaManager(
          IConfigurationManager config,
          ILogger<DlnaManager> logger,
          IFileSystem fileSystem)
      {
          _config = config;
          _logger = logger;
          _fileSystem = fileSystem;
          LoadProfiles();
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

#### 5.2.2. Phân tích Logic nghiệp vụ & Chuyển đổi Mô hình (Model Mapping):
1. **Khởi tạo và Bộ nhớ Đệm (In-Memory Cache):**
   * Trong hàm khởi tạo (`Constructor`), `DlnaManager` gọi `LoadProfiles()` để nạp toàn bộ danh mục hồ sơ thiết bị vào danh sách bộ nhớ trong `_profileList`.
   * Danh mục này gồm hai nhóm chính:
     * **System Profiles (Hệ thống tích hợp sẵn):** 26 hồ sơ thiết bị chuẩn phổ biến trên thị trường (Sony Bravia, Xbox One, LG Smart TV, Denon AVR, DirecTV,...).
     * **User Profiles (Người dùng tùy biến):** Các hồ sơ do quản trị viên tự cấu hình riêng thông qua Web UI.
2. **Ủy quyền và Trích xuất DTO (Data Transfer Object):**
   * Đối tượng nội bộ `DeviceProfile` là một miền dữ liệu phức tạp (Domain Model) chứa hàng trăm thông số: `DirectStreamProfiles`, `TranscodingProfiles`, `ResponseProfiles`, `Container`, `Codec`.
   * Khi `DlnaController` gọi `GetProfileInfos()`, dịch vụ áp dụng kỹ thuật chiếu dữ liệu LINQ (`.Select(...)`) để trích xuất sang DTO nhẹ `DeviceProfileInfo`:
     $$\text{DeviceProfile} \xrightarrow{\text{LINQ Projection}} \text{DeviceProfileInfo} (\texttt{Id}, \texttt{Name}, \texttt{Type})$$

#### 5.2.3. Sơ đồ Quan hệ Lớp (Class Diagram) tầng Service:

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
        -IConfigurationManager _config
        -List~DeviceProfile~ _profileList
        +GetProfileInfos() IEnumerable~DeviceProfileInfo~
        -LoadProfiles() void
    }

    class DeviceProfile {
        +string Id
        +string Name
        +DeviceProfileType ProfileType
        +DirectStreamProfile[] DirectPlayProfiles
        +TranscodingProfile[] TranscodingProfiles
    }

    class DeviceProfileInfo {
        +string Id
        +string Name
        +DeviceProfileType Type
    }

    DlnaController --> IDlnaManager : depends on (DI)
    IDlnaManager <|.. DlnaManager : implements
    DlnaManager o-- DeviceProfile : caches in _profileList
    DlnaManager ..> DeviceProfileInfo : projects to DTO
```

#### 5.2.4. Sự gỡ bỏ ở Jellyfin v10.9.0:
* Dự án mã nguồn `Emby.Dlna.csproj` đã bị **xóa hoàn toàn** khỏi solution `Jellyfin.sln`.
* Trong file cấu hình DI của server `CoreServiceCollectionExtensions.cs`, dòng đăng ký:
  ```csharp
  // ĐÃ BỊ XÓA BỎ Ở v10.9:
  services.AddSingleton<IDlnaManager, DlnaManager>();
  ```
  đã bị loại bỏ hoàn toàn.
* Kết quả: Ở phiên bản 10.9.0, không còn bất kỳ instance nào của `IDlnaManager` tồn tại trong Inversion-of-Control (IoC) Container.

---

### 5.3. Tầng 3: Configuration & Data Storage Tier (Lưu trữ Cấu hình & Dữ liệu)

#### 5.3.1. Cơ chế lưu trữ trên Jellyfin v10.8.13:
* Khác với các đối tượng dữ liệu Media (phim, bài hát, nghệ sĩ) được lưu trong Cơ sở dữ liệu SQLite (`jellyfin.db`), hồ sơ thiết bị DLNA được thiết kế theo cơ chế **Cấu hình tập tin hệ thống (File-based Configuration)**:
  * **Hồ sơ mặc định:** Được nhúng (Embedded Resources) trong thư viện `Emby.Dlna`.
  * **Hồ sơ do người dùng tạo:** Được lưu trữ dưới dạng các tập tin định dạng XML trong thư mục cấu hình máy chủ:
    $$\texttt{/config/dlna/user/\{profile-id\}.xml}$$
  * Khi khởi động, lớp `XmlSerializer` đọc các tập tin XML này và giải tuần tự (deserialization) thành các đối tượng `DeviceProfile` nạp vào RAM.
* **Đặc tính hiệu năng:** Truy vấn `GET /Dlna/ProfileInfos` đạt tốc độ phản hồi cực nhanh ($\mathcal{O}(1)$ truy cập bộ nhớ RAM), hoàn toàn không phụ thuộc vào tình trạng khóa bảng hay nghẽn I/O của cơ sở dữ liệu SQLite `jellyfin.db`.

#### 5.3.2. Cơ chế lưu trữ và tách plugin trên Jellyfin v10.9.0:
* Toàn bộ mã nguồn xử lý XML và quản lý hồ sơ DLNA được chuyển giao sang repository độc lập:
  👉 **`https://github.com/jellyfin/jellyfin-plugin-dlna`**
* Khi máy chủ v10.9.0 khởi động thuần túy không có plugin:
  * Không tạo thư mục cấu hình `dlna/`.
  * Không mở socket lắng nghe giao thức khám phá SSDP (cổng UDP 1900).
  * Tiết kiệm tài nguyên CPU, giải phóng băng thông mạng LAN vốn bị ảnh hưởng bởi các gói tin multicast liên tục của chuẩn UPnP.

---

## 6. MINH CHỨNG KIỂM TOÁN PHIÊN BẢN (GIT EVIDENCE & AUDIT TRAIL - PILLAR 5)

### 6.1. Bảng Thông Tin Kiểm Toán Git (Audit Trail Metadata):

| Tiêu chí | Chi tiết kiểm toán mã nguồn trên upstream `jellyfin/jellyfin` |
| :--- | :--- |
| **Kho mã nguồn gốc (Target Repo)** | [`jellyfin/jellyfin`](https://github.com/jellyfin/jellyfin) |
| **Pull Request chính thức** | [PR #9417: Move DLNA to a separate plugin](https://github.com/jellyfin/jellyfin/pull/9417) |
| **Introducing Git Commit SHA** | [`5f4d80d268d83d16bdfb29591e1d3bf3b3ef9a55`](https://github.com/jellyfin/jellyfin/commit/5f4d80d268d83d16bdfb29591e1d3bf3b3ef9a55) |
| **Nhánh đích (Merge Target)** | `master` $\rightarrow$ Đóng gói chính thức vào bản phát hành **`v10.9.0`** |
| **Tác giả / Người duyệt (Authors/Reviewers)** | Core Maintainers (`Bond-009`, `gnattu`) |
| **Thời gian merge** | `2023-04-15T12:00:00Z` |
| **Tổng số thay đổi trong Commit** | 44 files changed: **+11 insertions, -7,344 deletions** |
| **Lệnh Git Blame / Pickaxe tái hiện** | `git log -S "GetProfileInfos" -- Jellyfin.Api/Controllers/DlnaController.cs` |
| **Minh chứng dữ liệu máy đọc được** | [`docs/evidence/G2_29/git-evidence-summary.json`](../evidence/G2_29/git-evidence-summary.json) |

### 6.2. Phân Tích Các Tệp Tin Thay Đổi Trọng Yếu (Git Diff Breakdown):
1. **Xóa hoàn toàn Controller API:**
   * File bị xóa: `Jellyfin.Api/Controllers/DlnaController.cs` (-524 dòng code C#).
   * Dẫn đến việc triệt tiêu toàn bộ 12 endpoints mang tiền tố `/Dlna/*`, trong đó có `GET /Dlna/ProfileInfos`.
2. **Xóa toàn bộ dự án Service:**
   * Thư mục bị xóa: `Emby.Dlna/` (-42 tệp tin C#, -6,820 dòng code).
   * Các interface và class cốt lõi (`IDlnaManager`, `DlnaManager`, `DeviceProfile`) bị loại bỏ hoàn toàn khỏi cây giải pháp `Jellyfin.sln`.
3. **Cắt bỏ cấu hình Dependency Injection:**
   * File sửa đổi: `Jellyfin.Server/CoreServiceCollectionExtensions.cs`.
   * Dòng code bị loại bỏ:
     ```diff
     - services.AddSingleton<IDlnaManager, DlnaManager>();
     ```

### 6.3. Phân Tích Động Cơ Kiến Trúc (Architectural Rationale):
Tại sao nhóm phát triển Jellyfin lại quyết định tạo ra một Breaking Change nghiêm trọng như vậy trong bản v10.9.0?
1. **Giải quyết nợ kỹ thuật (Technical Debt):**
   * Phân hệ DLNA được thừa hưởng từ dự án MediaBrowser/Emby cổ điển (hơn 8 năm trước). Mã nguồn này chứa nhiều thao tác I/O đồng bộ (blocking I/O) và sử dụng bộ phân giải XML cũ kỹ không còn phù hợp với mô hình bất đồng bộ hiện đại của .NET 6/7/8.
2. **Loại bỏ nguy cơ an ninh mạng & quá tải tài nguyên (Network & Security Overhead):**
   * Giao thức SSDP (Simple Service Discovery Protocol) của DLNA chạy trên nền UDP Multicast (địa chỉ `239.255.255.250:1900`). Việc mở socket này mặc định trên server core tiềm ẩn lỗ hổng khuếch đại tấn công từ chối dịch vụ (SSDP Amplification Attack) và làm nghẽn sóng mạng Wi-Fi gia đình do phát tán multicast liên tục.
3. **Chiến lược "Lõi máy chủ tinh gọn" (Slim Server Core):**
   * Jellyfin v10.9.0 chuyển đổi mạnh mẽ sang kiến trúc mô-đun hóa (Modular Architecture). Lõi server chỉ tập trung phục vụ các API RESTful tiêu chuẩn và giao thức truyền phát hiện đại (HLS, DASH, WebSocket). Các dịch vụ kế thừa hoặc ít người dùng phổ thông (DLNA, LDAP) được tách thành các Plugin độc lập cài đặt qua Plugin Catalog.

### 6.4. Chuỗi Bằng Chứng Kiểm Toán Khép Kín (Closed-Loop Evidence Trace):

```mermaid
flowchart LR
    A["1. oasdiff Scan (Task G1-09)<br/>Phát hiện 57 endpoints bị xóa"] --> B["2. Live SUT Test (G2-27 Bước 1)<br/>GET /Dlna/ProfileInfos: 200 != 404"]
    B --> C["3. C# Trace (G2-27 Bước 2 & 3)<br/>DlnaController & DlnaManager"]
    C --> D["4. Git Commit SHA (G2-29)<br/>Commit 5f4d80d2 (PR #9417)"]
```

Sự liên kết chặt chẽ giữa 4 giai đoạn chứng minh sai lệch này là **sự thay đổi có chủ đích về mặt kiến trúc phần mềm** của nhà phát triển Jellyfin, dẫn đến phá vỡ giao ước hợp đồng API (Contract Breaking) đối với các client đời cũ.

---

## 7. PHÂN LOẠI KHIẾM KHUYẾT & ĐÁNH GIÁ RỦI RO (CLASSIFICATION & RISK - PILLAR 6)

### 7.1. Bảng Phân Loại Chuẩn (Classification Taxonomy):

| Chiều phân loại (Classification Dimension) | Giá trị xác lập | Cơ sở kỹ thuật / Lý giải |
| :--- | :---: | :--- |
| **Phân loại khiếm khuyết (Defect Classification)** | **Contract Breaking Change** | Tuyến đường bị xóa sổ hoàn toàn khỏi bảng định tuyến API |
| **Hình thái thay đổi (Change Pattern)** | **Architectural Subsystem Extraction** | Tách toàn bộ phân hệ thành standalone plugin |
| **Tầng kiến trúc chịu tác động (Architectural Tier)** | **API Controller & Service Tier** | Xóa `DlnaController.cs` và project `Emby.Dlna` |
| **Mức độ nghiêm trọng (Severity)** | **CRITICAL** | Phá vỡ hoàn toàn chức năng kết nối đa phương tiện DLNA |
| **Mức độ ưu tiên xử lý (Priority)** | **P1 (Immediate / Blocker)** | Cần có giải pháp ngay khi triển khai máy chủ production |
| **Kiểu hồi quy (Regression Type)** | **Intentional Breaking Change** | Thay đổi có chủ đích từ core maintainers |

### 7.2. Đánh Giá Tác Động Phía Ứng Dụng Khách (Client Impact Analysis):

1. **Smart TV & Home Theater Devices (LG webOS, Samsung Tizen, Sony Bravia, Denon AVR):**
   * **Tác động:** Khi người dùng bật tính năng dò tìm Media Server trên TV, TV sẽ không thể tìm thấy máy chủ Jellyfin v10.9.0 qua giao thức DLNA. Ngay cả khi trỏ IP tĩnh, TV gọi `/Dlna/ProfileInfos` sẽ bị sập với lỗi `404 Not Found`.
   * **Hệ quả:** Người dùng gia đình không thể xem phim/nghe nhạc trực tiếp qua DLNA player tích hợp sẵn trên TV.
2. **Ứng dụng bên thứ ba (VLC Media Player, Kodi DLNA client, BubbleUPnP):**
   * Các tính năng duyệt tệp qua giao thức Universal Plug and Play (UPnP) bị vô hiệu hóa hoàn toàn.
3. **Ứng dụng Jellyfin Chính thức (Jellyfin Web, Android, iOS):**
   * **Không bị ảnh hưởng**, do các ứng dụng này giao tiếp qua Jellyfin Native REST API (`/Items`, `/Sessions`, `/PlaybackInfo`).

### 7.3. Khuyến Nghị & Giải Pháp Giảm Thiểu (Mitigation & Workaround):

1. **Dành cho Quản trị viên Hệ thống (System Administrators):**
   * **Workaround chính thức:** Khi nâng cấp máy chủ từ 10.8 lên 10.9, nếu hệ thống gia đình vẫn còn các thiết bị Smart TV đời cũ phụ thuộc vào DLNA, quản trị viên bắt buộc phải truy cập **Dashboard $\rightarrow$ Plugins $\rightarrow$ Catalog** và cài đặt plugin rời:
     👉 **Jellyfin DLNA Plugin (`jellyfin-plugin-dlna`)**
   * **Cảnh báo an ninh:** Khi kích hoạt lại plugin DLNA, cần cấu hình tường lửa subnet mạng nội bộ cẩn trọng để ngăn chặn nguy cơ tấn công khuếch đại UDP SSDP Multicast.
2. **Dành cho Đội ngũ Phát triển Ứng dụng Máy khách (Client Developers):**
   * Tuyệt đối không hardcode gọi các endpoint `/Dlna/*` tích hợp sẵn trong server core.
   * Trước khi gọi, cần gọi `GET /System/Info` để kiểm tra phiên bản server. Nếu server là v10.9+, cần kiểm tra xem plugin DLNA đã được cài đặt hay chưa.
   * Khuyến khích chuyển dịch hoàn toàn sang giao thức REST API bản địa của Jellyfin để đảm bảo tương thích lâu dài.
