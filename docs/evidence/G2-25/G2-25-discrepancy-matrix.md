# BÁO CÁO DIFFERENTIAL TEST RUN LẦN 2 & DISCREPANCY MATRIX (ST-49 / G2-25)

## 1. Thông Tin Nhiệm Vụ
- **Mã Task**: ST-49 (G2-25) - Chạy Differential Test Suite Lần 2 & Lập Discrepancy Matrix
- **Mục Tiêu**: Thực thi lại toàn bộ Differential Test Suite trên môi trường Jellyfin v10.8 vs v10.9 sau khi đã áp dụng bộ lọc Normalization và Discrepancy Classifier Model.
- **Log Thực Thi Chi Tiết**: `docs/evidence/G2-25/second_test_run.log`
- **Kết Quả Test Suite**: **223 passed, 1 xfailed** (100% Passed / Expected Behaviors).

## 2. Ma Trận Sai Lệch Hành Vi (Discrepancy Matrix)
Dưới đây là ma trận tổng hợp các sai lệch thu thập được giữa 2 bản Jellyfin:

| Endpoint / Nhóm API | Thuộc Tính / Field Path | Loại Khác Biệt | Nhãn Phân Loại (Label) | Trạng Thái Xử Lý |
| :--- | :--- | :--- | :--- | :--- |
| `GET /System/Info/Public` | `Headers.Date` | Dynamic Timestamp | `DYNAMIC_NOISE` | Khử nhiễu tự động qua Normalizer |
| `GET /Users` | `Users[].Id` | Type Mismatch | `API_CONTRACT_BREAKING_CHANGE` | Phát hiện gãy contract API ở v10.9 |
| `GET /Search/Hints` | `SearchHints[].PrimaryImageTag` | String Format | `NORMALIZATION_TOLERANCE_ISSUE` | Bỏ qua chênh lệch format hash |
| `POST /Users/AuthenticateByName` | `SessionInfo.Id` | Session GUID | `DYNAMIC_NOISE` | Khử nhiễu tự động qua Normalizer |

## 3. Kết Luận
- Bộ test suite lần 2 đã chạy sạch sẽ, ổn định và lọc chính xác các điểm sai lệch hành vi giữa Jellyfin v10.8 và v10.9.
- Dữ liệu thu thập đủ điều kiện để tổng hợp báo cáo đánh giá chất lượng cuối kỳ.