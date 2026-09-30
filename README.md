# Jellyfin Differential Testing

Framework kiểm thử vi sai cho Jellyfin Server v10.8.13 và v10.9.0. Hai phiên
bản được chạy song song, nhận cùng request và được so sánh sau khi chuẩn hoá
những giá trị động như server ID, access token và version.

## Chạy G1-06 từ máy mới

G1-06 chuẩn bị state ban đầu tương đương: cùng Setup Wizard, admin, cấu hình,
library và seed-data. Không cần mở trình duyệt để thao tác wizard thủ công.

### Yêu cầu

- Docker Desktop đang chạy.
- Python 3.10 trở lên (`py -3 --version`).

### Lệnh chạy

Chạy toàn bộ lệnh sau từ thư mục gốc repository:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
docker compose -f docker/docker-compose.yml up -d
python -m pytest -q
python scripts/g1_06_setup_and_verify.py
```

Kết quả đúng phải kết thúc bằng:

```text
G1-06 success: normalized initial states are equivalent.
```

Evidence được tạo tại `docs/evidence/G1-06-initial-state-parity.json`; trường
`status` phải là `equivalent` trước khi bắt đầu Differential Testing.

## Môi trường được tạo

| Server | Image | Host URL |
| --- | --- | --- |
| Baseline | `jellyfin/jellyfin:10.8.13` | `http://localhost:8096` |
| Candidate | `jellyfin/jellyfin:10.9.0` | `http://localhost:8097` |

Script G1-06 tự tạo hai file WAV có nội dung xác định theo
`data/dataset-manifest.json`, mount chung chúng read-only vào `/media`, chạy
Setup Wizard qua API, tạo library `Differential Seed Music` và so sánh state.
Credential development mặc định là `admin` / `admin123456`; chỉ sử dụng trong
container test cục bộ. Có thể đặt biến `JELLYFIN_ADMIN_PASSWORD` trước khi chạy
để dùng mật khẩu khác trên cả hai server.

## Chạy lại hoặc reset

Khi state hiện có đã đúng, chỉ cần chạy lại:

```powershell
python scripts/g1_06_setup_and_verify.py
```

Nếu script báo state cũ khác manifest, dừng containers trước:

```powershell
docker compose -f docker/docker-compose.yml down
```

Sau đó chỉ xoá bốn thư mục runtime sau rồi chạy lại phần **Lệnh chạy**:

- `docker/v10.8/config`
- `docker/v10.8/cache`
- `docker/v10.9/config`
- `docker/v10.9/cache`

Không xoá `data/seed-data`, vì đây là seed dataset dùng chung của hai server.

Chi tiết kỹ thuật và các field được so sánh: `docs/G1-06-setup-wizard-and-initial-seeding.md`.
