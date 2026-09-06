# Tăng trưởng dữ liệu và điểm nghẽn — mốc nền 2026-09-06

Tài liệu này chốt **một mốc nền đo được** và **một danh sách chỉ số cần theo dõi**, để khi dựng
Prometheus (bước 5 của khung nâng cấp nền tảng) thì đã có sẵn thứ cần thu, thay vì thu tất cả rồi
lọc sau.

Mọi con số dưới đây kèm lệnh sinh ra nó. Đo lại bằng đúng lệnh đó thì so sánh mới có nghĩa; đo bằng
lệnh khác thì con số mới không nối tiếp được với mốc này.

## 1. Mốc nền — 2026-09-06

### 1.1 Đĩa

| Vùng | Thiết bị | Tổng | Đang dùng | Trống |
|---|---|---|---|---|
| `/mnt/hdd` | `/dev/sda1` (đĩa cơ) | 1,8 TB | 603 GB (35%) | 1,2 TB |
| `/` | `pve-root` (SSD) | 94 GB | 27 GB (31%) | 63 GB |
| thin pool `pve/data` | SSD | 1,71 TB | 14,45% (~247 GB) | ~1,46 TB |

`df -h /mnt/hdd /` · `lvs -o lv_name,lv_size,data_percent pve`

`/mnt/hdd` chia ra: `backup` 362 GB · `projects` 174 GB · `seaweedfs` 24 GB · `trongnq` 22 GB ·
`iso` 18 GB (`du -sh /mnt/hdd/*`).

### 1.2 Sao lưu — đang chạy, không phải chưa có

| Việc | Lịch | Đích | Giữ lại |
|---|---|---|---|
| `vzdump: daily-guests` | 01:00 mỗi ngày, toàn bộ guest, zstd | `hdd-backup` = `/mnt/hdd/backup/dump` | `keep-daily=7, keep-weekly=4` → **tối đa 11 bản** |
| `pggold-backup.timer` | ~01:44 | `/mnt/hdd/backup/pg-gold` | — |
| `pg204-backup.timer` | ~02:31 | `/mnt/hdd/backup/pg-204` | — |
| `labelstudio-backup.timer` | ~03:30 | `/mnt/hdd/backup/labelstudio` | — |
| `vaultwarden-backup.timer` | ~04:01 | `/mnt/hdd/backup/vaultwarden` | — |
| `offsite-encrypt.timer` | ~04:21 | ExternalSSD, mã hoá `age` | `KEEP=3` |

`cat /etc/pve/jobs.cfg` · `systemctl list-timers --all`

Khung nâng cấp nền tảng ngày 2026-08-05 ghi "không có job sao lưu nào". Câu đó mô tả ngày 05/08 và
**đã hết hiệu lực từ 2026-09-04**; suy luận từ nó là suy luận trên số cũ ba tuần.

### 1.3 Kho đối tượng

| Bucket | Dung lượng | Ghi chú |
|---|---|---|
| `project-assets` | 12,89 GB | tệp đính kèm |
| `llm-logs` | 8,68 GB | nội dung phiên tác tử CLI |
| `learning-hub` | 3,27 GB | dự án khác |
| `tuyen-dung` | 3,39 MB | |
| `lakehouse` | 663 KB | kho Iceberg mới + Bronze/Silver **còn rỗng** |
| `crawl-*`, `marketpulse`, `stock-data` | 0 | chưa dùng |

`echo "s3.bucket.list" | weed shell -master=localhost:9333`

Cụm: **172.386 tệp**, siêu dữ liệu filer (LevelDB2) 4,6 MB. Volume: `hdd` 49/100, `ssd` 14/50, trần
30 GB mỗi volume. Bucket `lakehouse` nằm ở rack `hdd`.

### 1.4 Cơ sở dữ liệu

| Cụm | CSDL | Dung lượng |
|---|---|---|
| LXC 202 (Docker) | `stock_market` | 14 GB |
| LXC 204 | `llm_logs` | 460 MB |
| LXC 204 | `nocodb_meta` | 54 MB |
| LXC 204 | phần còn lại (7 CSDL) | ~105 MB |
| LXC 204 | `iceberg_catalog` | 7,6 MB |

## 2. Nhịp tăng đo được

| Nguồn | Nhịp | Cách đo |
|---|---|---|
| `vzdump` mỗi lượt | 34 GB / 13 guest (16/08) → **53 GB / 19 guest** (06/09) | tổng `.tar.zst` theo ngày trong `dump/` |
| `cc_events` | **6.332 dòng/ngày** (04/08 → 05/09) | `min(ts)`, `max(ts)`, `count(*)` |
| `llm_logs` trong PostgreSQL | ~14 MB/ngày | 460 MB / 33 ngày |
| bucket `llm-logs` | ~260 MB/ngày | 8,68 GB / ~33 ngày |
| `daily_ohlcv` | **0 — đứng yên** từ 2026-04-14 | `max(trade_date)` |

## 3. Điểm nghẽn, xếp theo thứ tự sẽ chạm

Đĩa **không** phải điểm nghẽn gần: còn 1,2 TB trống, nhịp S3 khoảng 10 GB/tháng. Thứ chạm trước là
những cái dưới đây, theo đúng thứ tự.

### N1 — Kho đối tượng không có bản sao nào (đang hiện hữu)

`vzdump` chụp guest; SeaweedFS chạy **native trên host** nên không lượt nào chạm tới. `offsite-encrypt`
đóng gói bảy nguồn, không có `/mnt/hdd/seaweedfs`. 24 GB, mười bucket, không bản sao.

Nặng hơn một khoảng trống thường: catalog Iceberg nằm trong `iceberg_catalog` trên LXC 204 và **được
sao lưu hàng đêm**, còn dữ liệu bảng nằm trong `lakehouse` thì không. Khôi phục từ thứ đang có sẽ cho
ra một catalog trỏ tới tệp không quay lại được — trạng thái trông như đã khôi phục mà không trả lời
được truy vấn nào. Nợ `OPS01-homelab/docs/tech-debt.md` TD-46.

Đây không phải vấn đề tăng trưởng, nhưng tăng trưởng làm nó nặng dần: càng nhiều dữ liệu thì khoảng
trống càng đắt.

### N2 — Hệ số nhân 11× của chính sách giữ bản sao

`keep-daily=7` + `keep-weekly=4` giữ tới **11 bản** mỗi guest. Nghĩa là **mỗi 1 GB ghi vào bất kỳ
container nào tốn khoảng 11 GB trên `/dev/sda`**. Đây là cơ chế biến tăng trưởng dữ liệu thành áp lực
đĩa, và nó khuếch đại mọi thứ khác trong danh sách này.

Ở kích thước hiện tại, kho ổn định quanh **583 GB** (11 × 53 GB); hôm nay 356 GB. Còn dư, nhưng nhịp
tăng bám theo dữ liệu trong container chứ không theo số guest — và `daily_ohlcv` đang **đứng yên**.
Bật lại đường ống nạp là lúc con số này đổi hình: `stock_market` từ 14 GB lên gấp ba thì kho sao lưu
đi theo, nhân 11.

### N3 — Vỡ vụn tệp nhỏ của Iceberg

Một bảng, một ảnh chụp, 663 KB dữ liệu → **21 tệp trải trên 7 volume**. Mỗi lần ghi Iceberg sinh tối
thiểu năm tệp: Parquet, `metadata.json`, manifest `.avro`, snapshot `.avro`, `.stats`. Chưa có job
`optimize` (gộp tệp) lẫn `expire_snapshots` (dọn ảnh chụp cũ), nên số tệp chỉ tăng một chiều.

Điểm chịu tải không phải dung lượng mà là **siêu dữ liệu filer** (LevelDB2, nay 4,6 MB / 172.386 tệp)
và số volume. Trần hiện tại: `hdd` còn 51 volume trống.

### N4 — Trần của tầng SSD hẹp hơn nhiều so với vẻ ngoài

`ssd` mới dùng 14/50 volume, nghe như còn 36 × 30 GB = 1,08 TB. Nhưng volume SSD nằm ở
`/data/seaweedfs-ssd`, tức trên `pve-root` — **chỉ còn 63 GB trống**. Đĩa hết trước volume, và con số
volume sẽ không báo trước điều đó. Bucket `lakehouse` hiện ở rack `hdd`; nếu về sau chuyển tầng nóng
sang `ssd` thì đây là trần thật.

### N5 — Trino một nút, heap 8 GB

Máy còn rất rộng (13 GB / 94 GB RAM, load 0,68). Nhưng Trino chạy một nút vừa điều phối vừa làm việc,
heap khai cứng 8 GB. Truy vấn nặng đầu tiên sẽ chạm trần heap chứ không chạm trần máy.

### N6 — Hai quyết định còn treo đang định đoạt nhịp tăng

- **Retention log 7 hay 30 ngày** — quyết định này nhân trực tiếp vào 260 MB/ngày của `llm-logs`:
  7 ngày ≈ 1,8 GB thường trú, 30 ngày ≈ 7,8 GB.
- **16% `cc_events` có `ts` rỗng** (38.177 / 240.786) — chặn phân vùng theo thời gian, và do đó chặn
  luôn mọi chính sách retention dựa trên thời gian. Không sửa cái này thì không cắt log theo tuổi được.

## 4. Danh sách chỉ số cần theo dõi

Thu khi dựng Prometheus. Ngưỡng đặt theo mốc nền mục 1, không phải theo cảm tính.

| # | Chỉ số | Cách lấy | Ngưỡng cảnh báo | Vì sao ngưỡng đó |
|---|---|---|---|---|
| M1 | `/mnt/hdd` còn trống | `node_filesystem_avail_bytes` | < 300 GB | Đủ chỗ cho một lượt `vzdump` đầy (53 GB) cộng biên an toàn |
| M2 | Dung lượng `/mnt/hdd/backup/dump` | `du -sb` | > 700 GB | Trên mức ổn định tính toán 583 GB → chính sách giữ bản sao hoặc kích thước guest đã đổi |
| M3 | Dung lượng một lượt `vzdump` | tổng `.tar.zst` cùng ngày | tăng > 20% so với tuần trước | Bắt được lúc dữ liệu trong container nhảy bậc, trước khi nhân 11 |
| M4 | Số tệp toàn cụm SeaweedFS | `volume.list` → cộng `file_count` | > 1.000.000 | Mốc để nghĩ tới gộp tệp Iceberg; nền là 172.386 |
| M5 | Kích thước `filerldb2` | `du -sb` | > 500 MB | Siêu dữ liệu filer là chỗ vỡ vụn tệp nhỏ biểu hiện thành độ trễ; nền 4,6 MB |
| M6 | Volume đã dùng / trần, theo tầng | `volume.list` topology | `hdd` > 80/100 hoặc `ssd` > 40/50 | Còn kịp thêm volume server trước khi ghi bị từ chối |
| M7 | `/` (pve-root) còn trống | `node_filesystem_avail_bytes` | < 20 GB | Trần thật của tầng `ssd` (N4), và cũng là rootfs của Proxmox |
| M8 | thin pool `pve/data` phần trăm | `lvs data_percent` | > 70% | `vzdump mode=snapshot` cần chỗ trong pool; pool đầy là mọi guest dừng |
| M9 | Số tệp mỗi bảng Iceberg | `SELECT count(*) FROM ..."$files"` | > 1.000 tệp/bảng | Mốc chạy `ALTER TABLE ... EXECUTE optimize` |
| M10 | Số ảnh chụp mỗi bảng Iceberg | `..."$snapshots"` | > 100 | Mốc chạy `expire_snapshots`; chưa có job nào dọn |
| M11 | Nhịp `cc_events` | `count(*)` theo ngày | lệch > 50% so với 6.332/ngày | Bắt cả đường ống dừng lẫn đường ống chạy loạn |
| M12 | Tỷ lệ `cc_events.ts` rỗng | `count(*) FILTER (WHERE ts IS NULL)` | > 5% | Nền hiện tại 16% — chỉ số này phải **giảm**, và nó chặn retention theo thời gian |
| M13 | Heap Trino đang dùng | JMX `/v1/jmx` hoặc exporter | > 80% của 8 GB | Trino một nút; chạm trần heap là truy vấn hỏng, không phải chậm |
| M14 | Tuổi bản sao mới nhất của SeaweedFS | (chưa có nguồn) | tồn tại | **Chỉ số này chưa đo được vì chưa có bản sao nào** — xem N1 / TD-46 |

M14 cố ý để trong bảng dù chưa thu được: một dòng trống trong bảng theo dõi nhắc rằng khoảng trống
vẫn còn, tốt hơn là bỏ nó ra khỏi bảng rồi quên.

## 5. Điều nên làm trước khi tăng trưởng thật bắt đầu

Xếp theo giá trị trên công sức, không phải theo mức độ nguy hiểm:

| Ưu tiên | Việc | Vì sao trước | Hồ sơ khắc phục |
|---|---|---|---|
| 1 | Đưa `/mnt/hdd/seaweedfs` vào một đường sao lưu | N1 — rẻ nhất khi kho mới 24 GB, đắt dần theo từng tháng | TD-46 |
| 2 | Chốt retention log 7 hay 30 ngày | N6 — quyết định này định đoạt nhịp tăng lớn nhất đang chạy | chưa mở, là câu hỏi còn treo |
| 3 | Sửa `ts` rỗng của `cc_events` | N6 — không có nó thì không thi hành được retention vừa chốt | chưa mở |
| 4 | Job `optimize` + `expire_snapshots` cho Iceberg | N3 — dựng lúc còn một bảng thì rẻ, lúc có trăm bảng thì không | TD-47 |

Phương án chi tiết cho từng món — các lựa chọn đã cân, lý do loại, việc cụ thể và điều kiện đóng —
nằm ở `OPS01-homelab/docs/tech-debt/`. Đừng chép lại vào đây: hai bản sẽ lệch nhau.

## Related

- `superpowers/specs/2026-09-06-trino-deployment-design.md`
- `2026-08-05-lakehouse-upgrade-framework__ai1.md`
- `seaweedfs-ops.md`
- `../.claude/PROGRESS.md`
