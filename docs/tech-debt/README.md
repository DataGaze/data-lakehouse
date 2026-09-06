# Nợ kỹ thuật

`open/` — món nợ chưa xử lý. `resolved/` — đã xử lý.

Một tệp một món nợ, đặt tên `TD-NN-mo-ta-ngan.md`. Trả xong thì `git mv` sang `resolved/`, **giữ
nguyên tên và số hiệu** — số hiệu không tái sử dụng, không đánh lại, để commit cũ vẫn tra được.

Mỗi hồ sơ phải có đủ: bối cảnh đo được (mỗi con số kèm lệnh sinh ra nó), các phương án đã cân,
**phương án bị loại kèm lý do loại**, khuyến nghị, việc cụ thể, điều kiện đóng. Thiếu lý do loại thì
vài tháng sau có người đề xuất lại đúng cái đã bị loại.

Chuyển sang `resolved/` chỉ khi điều kiện đóng ghi trong chính hồ sơ đã verify bằng máy — không
chuyển vì "hình như xong". Đóng một phần thì hạ mức nghiêm trọng, ghi rõ còn thiếu vế nào, và vẫn để
ở `open/`.

Quy ước đầy đủ: mục "Nợ kỹ thuật — Convention (DEV*/OPS*)" trong global CLAUDE.md của `agentsmith`.
