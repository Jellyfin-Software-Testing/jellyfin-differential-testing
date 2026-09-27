# Hướng Dẫn Đóng Góp (Contributing Guidelines)

Rất hoan nghênh các thành viên tham gia phát triển Dự án **Jellyfin Differential Testing Framework**.
Vui lòng tuân thủ quy trình làm việc dưới đây để đảm bảo chất lượng codebase và tính minh bạch minh chứng (Evidence).

---

## 1. Phân Công Vai Trò & Trách Nhiệm (Team Roles)

- **QA Lead**: Quản lý Test Model, Traceability Matrix, Differential Engine, Mutation Verification.
- **DevOps Lead**: Quản lý Docker Environment, CI/CD, Infrastructure, Prometheus & k6 Benchmark.
- **Tester 2 (Senior Core)**: Xây dựng Normalizer, Stateful Testing, Concurrency Testing, DB Validator.
- **Tester 1 (Execution)**: Quản lý Dataset, Parity Verification, Replay Utility, Test Execution.
- **Tech Writer**: Phân tích OpenAPI Diff, C# Code Root Cause Analysis (RCA), Git Blame & Final Reports.

---

## 2. Quy Trình Quản Lý Nhánh (Branching Model)

Dự án áp dụng mô hình **Gitflow thu gọn**:
* `main`: Nhánh chứa sản phẩm hoàn chỉnh, ổn định dùng để đóng gói nộp bài và demo.
* `develop`: Nhánh tích hợp chính cho mọi tính năng đang phát triển trong Sprint.
* `feature/<Mã-Task>-<Tên-ngắn-gọn>`: Nhánh làm việc cá nhân cho từng Task Jira (Ví dụ: `feature/G1-03-v108-docker-env`).
* `bugfix/<Mã-Bug>-<Tên-bug>`: Nhánh xử lý bug hoặc sai lệch (false positive).

---

## 3. Quy Trình Tạo & Merge Pull Request (PR)

1. **Tạo nhánh mới** từ nhánh `develop`:
```bash
git checkout develop
git pull origin develop
git checkout -b feature/<Mã-Task>-<Tên-ngắn-gọn>

```

2. **Commit công việc**:
* Cú pháp Commit Message chuẩn: `[Mã-Task] Mô tả ngắn gọn công việc`
* *Ví dụ:* `[G2-05] Add JellyfinAPIClient wrapper with trace logging`


3. **Push và Tạo Pull Request**:
* Push nhánh cá nhân lên GitHub:
```bash
git push -u origin feature/<Mã-Task>-<Tên-ngắn-gọn>

```


* Tạo PR hướng vào nhánh **`develop`** (tuyệt đối KHÔNG tạo PR trực tiếp vào `main`).
* Gắn nhãn (Labels) tương ứng (Ví dụ: `Automation`, `Infra`, `Documentation`, `Verification`).
* Chỉ định người Review (Reviewers): QA Lead hoặc thành viên phối hợp liên quan.



---

## 4. Quy Định Duyệt PR (Code Review & Approval)

Mọi PR **bắt buộc phải có ít nhất 1 Approval** từ thành viên khác mới đủ điều kiện Merge.

**Checklist bắt buộc trước khi Approve**:

* [ ] Code tuân thủ chuẩn format PEP8 (dành cho Python).
* [ ] Đã chạy thử nghiệm local thành công, không phát sinh lỗi vặt.
* [ ] Đính kèm file log / evidence deliverable tương ứng với yêu cầu trong Jira Task.

*Chọn hình thức **Squash and Merge** khi hợp nhất nhánh để giữ lịch sử Git luôn gọn gàng.*

---

## 5. Báo Cáo Defect & Minh Chứng (Evidence Rules)

Mọi Defect tìm thấy phải được lưu trữ đúng cấu trúc trong thư mục `docs/defects/`.

Hồ sơ Defect chuẩn bắt buộc phải bao gồm:

* Lệnh cURL tái hiện lỗi.
* Diff Log từ Differential Engine.
* Đường dẫn (Permalink) trỏ đến dòng code C# bị lỗi trên repository gốc của Jellyfin.
* Git Commit SHA gây ra sai lệch.

*Mọi cập nhật trong `config/ignore-rules.json` đều phải kèm lý do phân loại dữ liệu nhiễu (dynamic noise) cụ thể.*

---

## 6. Hướng Dẫn Thao Tác Git Nhanh (Git Cheat Sheet Cho Nhóm)

Để thực hiện task, mở Terminal / Git Bash ngay tại thư mục dự án (`jellyfin-differential-testing`) và thực hiện các lệnh sau:

### Bước 1: Chuyển sang nhánh `develop` & lấy code mới nhất

```bash
git checkout develop
git pull origin develop

```

### Bước 2: Tạo nhánh cá nhân từ `develop`

```bash
git checkout -b feature/<Mã-Task>-<Tên-ngắn-gọn>
# Ví dụ: git checkout -b feature/G1-01-contributing-guidelines

```

### Bước 3: Thêm các file chỉnh sửa vào Git Tracking

```bash
git add .

```

### Bước 4: Commit thay đổi đúng cú pháp Jira Task

```bash
git commit -m "[<Mã-Task>] Mô tả ngắn gọn công việc đã hoàn thành"
# Ví dụ: git commit -m "[G1-01] Add CONTRIBUTING.md guidelines and Git cheat sheet"

```

### Bước 5: Push nhánh cá nhân lên GitHub

```bash
git push -u origin feature/<Mã-Task>-<Tên-ngắn-gọn>
# Ví dụ: git push -u origin feature/G1-01-contributing-guidelines

```

### Bước 6: Tạo PR & Dọn dẹp sau khi Merge

1. Lên giao diện Web GitHub của nhóm, tạo Pull Request hướng từ nhánh feature về nhánh **`develop`**.
2. Nhờ 1 thành viên trong nhóm bấm **Approve** và tiến hành **Squash and Merge**.
3. Sau khi PR đã được merge thành công, xóa nhánh feature ở máy local để giữ Repo gọn gàng:
```bash
git checkout develop
git pull origin develop
git branch -d feature/<Mã-Task>-<Tên-ngắn-gọn>

```
