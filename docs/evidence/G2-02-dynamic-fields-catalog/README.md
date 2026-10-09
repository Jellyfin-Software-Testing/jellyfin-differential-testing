# Hướng Dẫn & Giải Thích Kết Quả Khai Phá Dữ Liệu Nhiễu (Task G2-02)

Tài liệu này giải thích tóm tắt, dễ hiểu về công việc đã làm trong Task G2-02, các tập tin được tạo ra, cách chạy thử nghiệm và ý nghĩa thực tế của các con số kết quả.

---

## 1. Những Tập Tin Nào Đã Được Tạo Và Chỉnh Sửa?

Trong nhiệm vụ này, hệ thống có 3 tập tin quan trọng:

1. **`scripts/g2_02_mine_dynamic_fields.py`**
   * Đây là đoạn mã Python đóng vai trò như một "máy quét". Nó tự động gửi các yêu cầu mạng (requests) liên tiếp 3 lần vào cả hai máy chủ Jellyfin v10.8 và v10.9 để tìm xem những chữ, những số nào tự động thay đổi sau mỗi lần bấm.
2. **`config/ignore-rules.json`**
   * Chứa danh sách các "luật" được viết bằng định dạng JSON. Sau này khi chạy kiểm thử so sánh tự động, hệ thống sẽ đọc tập tin này để biết: *chỗ nào cần che đi, chỗ nào cần chuẩn hóa, và chỗ nào là tính năng mới cần giữ lại để báo cáo*.
3. **`docs/evidence/G2-02-dynamic-fields-catalog.json`**
   * Chứa toàn bộ 266 trường dữ liệu đã được quét cùng với các giá trị mẫu thực tế thu thập được từ máy chủ thật, dùng làm bằng chứng nộp bài.

---

## 2. Cách Chạy

Mở cửa sổ dòng lệnh PowerShell và gõ lệnh sau (sau khi đã chạy g1-06 thành công):

```powershell
python scripts/g2_02_mine_dynamic_fields.py
```

* Máy quét sẽ tự động kiểm tra xem 2 máy chủ Docker có đang bật hay không.
* Nếu máy chủ đang bật, nó sẽ kết nối trực tiếp, quét qua 8 nhóm chức năng chính (thông tin hệ thống, đăng nhập, phiên làm việc, bài hát...) và in ra bảng tổng kết.

---

## 3. Kết Quả Hiển Thị Trên Màn Hình Nói Lên Điều Gì?

Khi chạy xong, màn hình hiện ra bảng tổng kết với 5 con số:

```text
=================================================================
G2-02 SUMMARY REPORT (BÁO CÁO TỔNG KẾT G2-02)
=================================================================
Total Fields Analyzed    : 266 (Tổng số trường dữ liệu đã phân tích)
Dynamic Noise (Masked)   : 7   (Dữ liệu nhiễu động - Đã che mặt)
Format Diffs (Normalize) : 4   (Sai khác định dạng - Chuẩn hóa)
Version Diffs (Preserve) : 157 (Khác biệt phiên bản - Giữ nguyên)
Static Matching Fields   : 98  (Trường dữ liệu tĩnh khớp nhau 100%)
=================================================================
```

### Chi tiết ý nghĩa từng dòng:

1. **Total Fields Analyzed : 266 (Tổng số trường dữ liệu đã phân tích)**
   * Nghĩa là máy quét đã tự động soi kỹ **266 thông tin** khác nhau trả về từ các API của Jellyfin.
2. **Dynamic Noise (Masked) : 7 (Dữ liệu nhiễu động - Đã che mặt)**
   * Có **7 thông tin tự động nhảy số lung tung** sau mỗi lần gọi dù không ai làm gì cả (ví dụ: mã chìa khóa `AccessToken`, mã phiên làm việc `SessionId`, thời gian bấm chuột `LastActivityDate`).
   * **Hành động**: Đã được gắn mặt nạ (Masked) biến thành các chữ cố định như `<ACCESS_TOKEN>` để khi so sánh hai phiên bản không bị báo lỗi giả (False Positive - lỗi giả do giờ giấc chênh lệch).
3. **Format Diffs (Normalize) : 4 (Sai khác định dạng - Đã chuẩn hóa)**
   * Có **4 thông tin cùng chỉ một thời điểm**, nhưng bản cũ v10.8 viết dài dòng với 7 số thập phân siêu nhỏ (microsecond), còn bản mới v10.9 rút gọn lại còn 3 số mili-giây.
   * **Hành động**: Được đưa vào danh sách cắt gọn đuôi (Normalize) để hai bên có cùng độ dài trước khi đối chiếu.
4. **Version Diffs (Preserve) : 157 (Khác biệt phiên bản - Giữ nguyên không che)**
   * **Phần quan trọng nhất**: Có **157 điểm khác nhau** giữa bản v10.8 và v10.9 (ví dụ: số hiệu phiên bản `10.8.13` khác `10.9.0`, hoặc các mục mới được đội ngũ phát triển bổ sung thêm ở bản mới).
   * **Hành động**: Tuyệt đối **KHÔNG ĐƯỢC CHE GIẤU**. Các điểm này được giữ nguyên (Preserve) và đưa vào danh sách Known Differences (những điểm khác biệt đã biết) để người kiểm thử (Tester) đối chiếu xem đây là tính năng mới hay là lỗi phần mềm.
5. **Static Matching Fields : 98 (Trường dữ liệu tĩnh khớp nhau)**
   * Có **98 thông tin hoàn toàn giống nhau 100%** giữa hai bản (ví dụ: tên máy chủ, đường dẫn file nhạc, tên bài hát seed, số lượng bài hát). Cả hai phiên bản đều phản hồi đồng nhất.

---

## 4. Tóm Tắt Giá Trị Đạt Được Của Nhiệm Vụ

Nhiệm vụ G2-02 này giúp trả lời được câu hỏi cốt lõi: 
> *"Khi hai máy chủ Jellyfin trả về kết quả khác nhau, sự khác nhau đó là do thời gian ngẫu nhiên (nhiễu) hay là do mã nguồn phần mềm đã thực sự thay đổi?"*

Nhờ có 7 luật che nhiễu và 4 luật chuẩn hóa được tìm ra ở đây, hệ thống kiểm thử tự động của nhóm sẽ **không bao giờ bị báo lỗi giả ngớ ngẩn**, đồng thời **không bao giờ bỏ sót các lỗi phần mềm thật sự**.
