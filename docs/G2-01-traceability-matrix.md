# Traceability Matrix - Task G2-01

Bảng ánh xạ liên kết từ Yêu cầu thiết kế (Swagger) đến Kịch bản Test, Kết quả thực thi và Defect tương ứng:

| Mã Requirement (API Endpoint) | Mô tả Yêu cầu từ Swagger | Kỹ thuật Test | Mã Test Case (Postman / Script) | Trạng thái Thực thi (Execution) | Mã Bug liên quan (nếu có) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /Items (v1 vs v2)` | Lấy danh sách items với phân trang `limit` | EP & BVA | `TC_ITEM_01` (Limit hợp lệ)<br>`TC_ITEM_02` (Biên `limit=0, 51`) | Passed | - |
| `GET /Items/{id}` | Lấy chi tiết item theo ID | Negative | `TC_ITEM_03` (ID không tồn tại) | Failed | `DEFECT-01` |
| `POST /Users/auth` | Đăng nhập hệ thống | State & Negative | `TC_AUTH_01` (Sai mật khẩu)<br>`TC_AUTH_02` (Sai trạng thái tài khoản) | Passed | - |