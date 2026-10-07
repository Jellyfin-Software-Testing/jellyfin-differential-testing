# G1-15 — Manual Initial Runs & Snapshots

Ngày thực hiện: 2026-10-03 (Asia/Saigon). Điều kiện đầu vào: báo cáo G1-06 ghi `status: equivalent` và hai container Jellyfin ở trạng thái healthy trước khi chạy.

## Các request đã gọi thủ công

Cùng một nhóm request được gọi trên `http://localhost:8096` (Jellyfin 10.8.13) và `http://localhost:8097` (Jellyfin 10.9.0) bằng PowerShell/cURL:

1. `GET /System/Info/Public`
2. `POST /Users/AuthenticateByName`
3. `GET /Users/Me`
4. `GET /Library/VirtualFolders`
5. `GET /Items?UserId=<user-id>&ParentId=<library-id>&Recursive=true&IncludeItemTypes=Audio`

Xác thực thành công trên cả hai instance; token được giữ tạm trong biến PowerShell để gọi các API cần quyền. Response đăng nhập không được lưu vì chứa `AccessToken`. `UserId` và `ParentId` được lấy riêng từ response của từng instance, không dùng ID của một phiên bản cho phiên bản còn lại.

## Response snapshots

| Nội dung | v10.8.13 | v10.9.0 | Nhận xét |
| --- | --- | --- | --- |
| Thông tin công khai | [JSON](v108/system-info-public.json) | [JSON](v109/system-info-public.json) | `Version` đúng theo từng image. |
| User hiện tại | [JSON](v108/users-me.json) | [JSON](v109/users-me.json) | Cả hai là `admin`, `Policy.IsAdministrator=true`. |
| Thư viện | [JSON](v108/virtual-folders.json) | [JSON](v109/virtual-folders.json) | Cùng thư viện `Differential Seed Music`, loại `music`, location `/media/seed-music`. |
| Audio seed | [JSON](v108/items-seed.json) | [JSON](v109/items-seed.json) | Mỗi bên trả `TotalRecordCount=2`, gồm `01 - Reference Tone` và `02 - Comparison Tone`; cả hai item đều là `Audio` với `RunTimeTicks=10000000`. |

Cả tám snapshot trên là JSON hợp lệ. `Version`, `ServerId`, user ID, library/item ID và thời điểm hoạt động khác nhau giữa hai instance là giá trị gắn với phiên bản hoặc lần khởi tạo riêng. Response `Users/Me` cũng có một số trường chỉ xuất hiện ở v10.9.0; bảng trên so sánh các trường chung cần cho initial run. Response `/Items` hiện không trả `Path` và `Size`, nên không dùng hai trường này để kết luận về dữ liệu media.

## Container logs

| Instance | Log chụp ban đầu | Log chụp sau các request |
| --- | --- | --- |
| v10.8.13 | [container.log](v108/container.log) | [container-after-runs.log](v108/container-after-runs.log) |
| v10.9.0 | [container.log](v109/container.log) | [container-after-runs.log](v109/container-after-runs.log) |

Mỗi file là 200 dòng cuối của container tại thời điểm chụp. Log ban đầu được chụp trước một số request có xác thực; bộ `container-after-runs.log` được chụp sau khi hoàn tất các snapshot. Giá trị access token do Jellyfin ghi trong log đã được thay bằng `[REDACTED]` trước khi đưa vào Git.

Log v10.8.13 có lỗi post-scan `Not enough valid pictures provided to create a splashscreen!`. Log v10.9.0 có cảnh báo thư mục playlists trống/không truy cập được. Cả hai quan sát được giữ nguyên trong evidence; các response thư viện và hai audio seed vẫn được thu thập thành công. Riêng các log này không đủ để kết luận nguyên nhân hay mức độ ảnh hưởng của những thông báo đó.

## Kết luận và giới hạn

Initial run thủ công đã tạo response snapshots và logs cho cả hai phiên bản. Các trường cốt lõi của user, thư viện và hai item seed khớp nhau về mặt ngữ nghĩa; khác biệt phiên bản và ID được ghi nhận. Đây là bằng chứng cho các request nêu trên, không phải kết luận rằng mọi API của hai phiên bản có hành vi giống nhau.
