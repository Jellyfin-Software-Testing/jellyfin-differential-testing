# BÁO CÁO THIẾT KẾ MÔ HÌNH PHÂN LOẠI SAI LỆCH (ST-50 / G2-26)

## 1. Thông Tin Chung
- **Mã Task**: ST-50 (G2-26) - Build Evidence-Based Discrepancy Classification Model
- **Mục Tiêu**: Xây dựng mô hình phân loại tự động các điểm sai lệch (Discrepancies) phát hiện được giữa Jellyfin v10.8 và v10.9 dựa trên bằng chứng thu thập (OpenAPI, Release Notes, Runtime Logs).

## 2. Quy Tắc Phân Loại (Classification Taxonomy & Rules)
| Nhãn Phân Loại (Label) | Mô Tả Ý Nghĩa | Quy Tắc Phân Loại (Rule Logic) |
| :--- | :--- | :--- |
| **`DYNAMIC_NOISE`** | Nhiễu dữ liệu động | Nhận diện các thuộc tính biến đổi theo thời gian/mỗi lần gọi (`date`, `time`, `timestamp`, `ticks`, `sessionid`). |
| **`ENVIRONMENT_DIFFERENCE`** | Bất đồng hạ tầng/môi trường | Phát hiện cấu hình hệ thống/mạng khác biệt (`host`, `port`, `url`, `ip`). |
| **`NORMALIZATION_TOLERANCE_ISSUE`** | Sai lệch định dạng không đáng kể | Bất đồng định dạng số thực (float precision) hoặc trailing slash. |
| **`INTENDED_VERSION_CHANGE`** | Thay đổi chủ động theo phiên bản | Thay đổi có trong Release Notes chính thức của Jellyfin v10.9. |
| **`API_CONTRACT_BREAKING_CHANGE`** | Bất đồng cấu trúc API Spec | Mismatch kiểu dữ liệu (`TYPE_MISMATCH`) hoặc thiếu trường so với OpenAPI Specification. |
| **`POTENTIAL_DEFECT`** | Nguồn lỗi tiềm ẩn | Các trường hợp bất thường còn lại cần xác minh thêm bằng Replay Evidence. |

## 3. Bằng Chứng Kiểm Thử Tự Động (Automated Test Evidence)
- **Module Phân Loại**: `normalizer/G2_26_discrepancy_classifier.py`
- **File Test Suite**: `tests/test_G2_26_discrepancy_classifier.py`
- **File Log Bằng Chứng**: `docs/evidence/G2-26/classification_test_run.log`
- **Kết quả thực thi**: **2/2 PASSED (100%)**