# [DEFECT-01] Mất trường SortBy trong Response API /Items

- **Phiên bản lỗi:** v10.9.0
- **Endpoint:** `GET /Items`
- **Nguyên nhân gốc rễ (Root Cause):** Hàm xử lý query parameter bỏ qua trường SortBy khi mapping DTO.
- **Vị trí code C# gây lỗi:** [ItemsController.cs - Line 145](https://github.com/jellyfin/jellyfin/blob/v10.9.0/Jellyfin.Api/Controllers/ItemsController.cs#L145)