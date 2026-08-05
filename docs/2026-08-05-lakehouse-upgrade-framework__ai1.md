# Khung nâng cấp nền tảng lakehouse (2026-08-05)

> Số liệu hạ tầng đo trực tiếp trong ngày qua `ssh root@100.89.161.125`, chỉ đọc.
> Chưa thực hiện thay đổi nào. Khảo sát nền cho khung này ở
> `docs/2026-08-05-catalog-metadata-probe__ai1.md`.

## 1. Phát hiện quyết định phạm vi

**Đây không phải nâng cấp. Phần lớn là dựng lại.**

Tầng lưu trữ còn nguyên vẹn và khoẻ. Nhưng toàn bộ tầng truy vấn, điều phối và giám sát mô tả
trong `OPS01-homelab/data-infra/_overview.md` **không còn tồn tại trên hạ tầng** — trong khi
tài liệu vẫn mô tả chúng như đang chạy.

Ai đọc tài liệu hiện tại mà không kiểm sẽ thao tác theo một bản đồ sai.

## 2. Hiện trạng đo được

### 2.1 Còn sống

| Thành phần | Ở đâu | Số đo |
|---|---|---|
| **SeaweedFS 3.71** | promax | S3 `192.168.0.200:8333`, filer `:8888`, master `:9333`. Collection `lakehouse` có 7 volume ghi được trên HDD. Topology còn trống 115/150 volume |
| **PostgreSQL 17.9** | LXC 204 `pg-backend` | 4 nhân, 6144 MB, đĩa 80 GB dùng 5,2 GB (7%). DB: `windmill` 20 MB, `labelstudio` 14 MB, `labelstudio_rehearsal` 13 MB, `chatbot_db` 8,4 MB |
| **OpenSearch 3.7.0** | LXC 213 `kb-opensearch` | 4 nhân, 8192 MB, đĩa 20 GB dùng 3,3 GB. Heap 2 GB. Index: `gartner-docs` 54,8 MB, `kb-sources`, 8 index `top_queries-*` |
| **Windmill** | LXC 209 | CE v1.775.1 |
| **stock-gold** | LXC 202 | PostgreSQL Gold + ETL worker |

### 2.2 Đã biến mất

| Thành phần | Tài liệu nói | Thực tế |
|---|---|---|
| **VM 106** — PostgreSQL 16 + `iceberg_catalog`, Loki :3100, Grafana :3000, Superset :8088, Redis :6379 | `data-infra/_overview.md` | `192.168.0.106` không phản hồi, cả ba cổng 3100/3000/8088 đóng. Không có trong `qm list` |
| **K3s** `.102` / `.103` — Trino 439 (NodePort 30080), Prometheus (30090) | `data-infra/_overview.md`, `CLAUDE.md` của repo này | Cả hai địa chỉ không phản hồi |
| **LXC 201** `prefect-server` | `All_projects/CLAUDE.md`, ADR gỡ Prefect ghi "giữ lại container" | Không còn trong `pct list` |
| **VM 100** `ubuntu-ai` | `All_projects/CLAUDE.md` | Không còn trong `qm list` |

promax không nằm trong cluster (`pvecm nodes` báo không phải cluster), nên không có khả năng
các máy trên nằm ở nút khác.

## 3. Quyết định đã chốt

| Quyết định | Nguồn | Trạng thái |
|---|---|---|
| Dagster thay Prefect, mô hình hoá theo asset | `docs/adr/2026-08-05-retire-prefect-adopt-dagster.md` | Phần gỡ Prefect đã xong; Dagster chưa dựng |
| **Iceberg** làm định dạng bảng | Phiên 2026-08-05 | Có sẵn bản thiết kế để dựng lại: `data-infra/iceberg/catalog-schema.sql` + `data-infra/trino/catalog-iceberg.properties` |
| **OpenMetadata theo phương án B** — dùng chung OpenSearch 213 và PostgreSQL 204, bỏ Airflow, gọi `metadata ingest` từ Dagster | Phiên 2026-08-05 | Chưa dựng |
| Giữ **SeaweedFS**, không chuyển MinIO | Phiên 2026-08-05 | Bản cộng đồng MinIO đã bị lưu trữ 25/04/2026 |
| Loại **DuckLake** dù đã production-ready | Phiên 2026-08-05 | OpenMetadata không có connector DuckDB — chọn DuckLake là chọn kho mà catalog không nhìn thấy |

### Vì sao chọn phương án B cho OpenMetadata

| Tiêu chí | A — Chưa dựng | **B — Dùng chung** | C — Tách cụm riêng |
|---|---|---|---|
| Dịch vụ dựng mới | 0 | **1** LXC | 2 LXC |
| Đụng vào LXC 213 | Không | Nâng đĩa 20→100 GB, heap 2→4 GB, khởi động lại | Không |
| RAM thêm | 0 | ~6 GB | ~12 GB |
| Rủi ro cho `gartner-docs` | Không | Gián đoạn khi khởi động lại | Không |
| Có nơi tra cứu dữ liệu | Không | Có | Có |

Chọn B vì quy mô thật của cụm 213 rất nhỏ: toàn bộ index cộng lại khoảng 57 MB, đĩa mới dùng
18%, heap mới chạm 20%. Nỗi lo tranh giành tài nguyên gần như không có thật; ghép nối duy nhất
là **vận hành** — đổi heap phải khởi động lại, kho Gartner ngừng vài chục giây. Đó là thứ hẹn
giờ được.

[WARN] Điều kiện chuyển sang C, ghi sẵn để khỏi tranh luận lại: **khi kho Gartner được dùng để
phục vụ người dùng thật**, lúc đó gián đoạn không còn hẹn giờ tuỳ tiện được.

## 4. Khung sáu tầng

| Tầng | Thành phần | Trạng thái | Việc phải làm |
|---|---|---|---|
| **T0** Lưu trữ | SeaweedFS | Sống, khoẻ | Đưa vào as-code + xác minh sao lưu |
| **T1** Định dạng bảng + catalog | Iceberg, JDBC catalog | Mất, còn bản thiết kế | Dựng lại catalog trên PostgreSQL 204 |
| **T2** Điều phối | Dagster | Chưa có | Dựng mới (ADR đã chốt) |
| **T3** Truy vấn | Trino, Superset | Mất | Dựng lại, chọn nơi chạy khi không còn K3s |
| **T4** Catalog nghiệp vụ | OpenMetadata | Chưa có | Dựng theo phương án B |
| **T5** Log và giám sát | Loki, Grafana, Prometheus, agent thu log | Mất một phần, thiếu một phần | Dựng lại + bổ sung |

## 5. Tầng 5 — log và giám sát, chi tiết

| Thành phần | Có sẵn gì | Thiếu gì |
|---|---|---|
| **Loki** | `data-infra/loki/loki-config.yaml` + `loki.service`. Cổng 3100, `path_prefix: /var/loki`, kho `tsdb` với `object_store: filesystem`, `retention_period: 168h` (7 ngày), `retention_enabled: true`. Chạy binary `/usr/local/bin/loki` dưới user `loki` | Không có role ansible. Binary cài tay, ngoài quản lý gói. Lưu trên đĩa local trong khi SeaweedFS đang sống |
| **Grafana** | `data-infra/grafana/datasources.yaml` — Loki `localhost:3100`, Prometheus `192.168.0.103:30090` | Địa chỉ Prometheus trỏ vào nút K3s **đã chết**. Không có role. Không có dashboard nào |
| **Prometheus** | **Không có gì** — chỉ được nhắc tên trong datasources của Grafana | Toàn bộ: cấu hình, nơi chạy, danh sách đích thu thập |
| **Agent thu log** | Không có gì | Chọn `promtail` hay Grafana Alloy; cài lên các LXC cần thu |
| **Exporter chỉ số** | Không có gì | `node_exporter` cho promax và LXC; `postgres_exporter` cho 204 và 202; exporter cho OpenSearch 213 |
| **Cảnh báo** | Không có gì | Chưa có kênh nào — quyết định gửi đi đâu |

Ba đề xuất bổ sung so với cấu hình cũ:

1. **Chuyển `object_store` của Loki từ `filesystem` sang S3.** SeaweedFS đang sống và collection
   `lakehouse` đã có chỗ. Log nằm trên đĩa local của một máy là thứ mất cùng máy đó — đúng cái
   vừa xảy ra với VM 106.
2. **Nâng retention từ 7 ngày lên 30 ngày.** Bảy ngày quá ngắn để truy vết sự cố dữ liệu, vốn
   thường chỉ lộ ra khi ai đó đọc báo cáo tuần. Chuyển sang S3 rồi thì chi phí lưu không còn là
   ràng buộc.
3. **Đặt Prometheus cùng chỗ với Loki và Grafana**, một LXC quan sát duy nhất, thay vì rải như
   trước (Loki trên VM 106, Prometheus trên K3s).

## 6. Thứ tự thi công

**Nguyên tắc quan trọng nhất: tầng 5 làm sớm, không làm cuối.**

Mọi tầng dựng sau đều cần chỗ đổ log để chẩn đoán. Dựng Dagster, Trino, OpenMetadata trước rồi
mới dựng log là tự làm mù mình đúng lúc cần nhìn nhất.

### 6.0 Độ phủ as-code hiện tại và tiền đề bị thiếu

Đo ngày 2026-08-05 trên promax:

| Chỉ số | Giá trị đo được | Cách đo |
|---|---|---|
| LXC đang chạy | 15 (200, 202–215) | `pct list` |
| Có role ansible đủ 5 file | 2 — `windmill` (209), `labelstudio` (215) | `ls ansible/roles/*/tasks/` |
| Có trong `inventory.yml` nhưng chưa có role | 1 — `vaultwarden` (211) | `ansible/inventory.yml` |
| Việc sao lưu định kỳ toàn máy (`vzdump`) | **không có job nào** | `/etc/pve/jobs.cfg` không tồn tại; `/var/lib/vz/dump/` rỗng |
| Timer sao lưu cấp ứng dụng | 2 — `labelstudio-backup`, `vaultwarden-backup` | `systemctl list-timers` |
| Đĩa vật lý | 1 HDD 1,8 TB + 1 NVMe 1,9 TB, **không RAID** | `lsblk -d` |

Hai hệ quả buộc phải chèn một bước trước bước 1:

1. **13 trong 15 container không có bản sao nào.** Trong đó có PostgreSQL 204 (giữ `chatbot_db`,
   `windmill`, `labelstudio`), PostgreSQL Gold 202, và Vault trên 200 (giữ mọi bí mật hạ tầng).
2. **Kho sao lưu nằm cùng một đĩa vật lý với dữ liệu nó bảo vệ.** `hdd-backup` trỏ
   `/mnt/hdd/backup`, còn SeaweedFS ghi vào `/mnt/hdd/seaweedfs` — cùng `/dev/sda`. Một đĩa
   hỏng là mất đồng thời dữ liệu lẫn bản sao. `smartctl -H /dev/sda` hiện PASSED, nên đây là
   việc phải làm sớm chứ chưa phải sự cố.

Chừng nào chưa có bản sao, giá trị của as-code chỉ còn một nửa: dựng lại được phần mềm, nhưng
không dựng lại được dữ liệu — mà dữ liệu mới là thứ không thể tái tạo.

### 6.1 Bảng thứ tự

| Thứ tự | Việc | Vì sao ở vị trí này | Phụ thuộc |
|---|---|---|---|
| **0a** | Khai lịch `vzdump` cho toàn bộ LXC bằng file, đích **ngoài** `/dev/sda` | Không có bản sao thì mọi bước sau đều đặt cược vào một đĩa cơ đơn lẻ | — |
| **0b** | `pg_dump` định kỳ cho 204 và 202; sao lưu Vault (unseal key + KV) trên 200 | `vzdump` container đang chạy không bảo đảm CSDL nhất quán; Vault mất là mất mọi bí mật | 0a |
| 1 | Đưa SeaweedFS vào as-code + xác minh khôi phục được thật | Toàn bộ dữ liệu lake nằm ở đây và nó **đang chạy không có role**. Rủi ro cao nhất trong tất cả | 0a |
| 2 | Loki + Grafana + agent thu log, trên một LXC quan sát | Để mọi bước sau có chỗ nhìn khi hỏng | 1 |
| 3 | Dựng lại Iceberg catalog trên PostgreSQL 204 | 204 mới dùng 7% đĩa, thừa sức. Có sẵn schema để nạp | 1 |
| 4 | Dagster | ADR đã chốt; là nơi gọi mọi thứ về sau | 2, 3 |
| 5 | Prometheus + exporter + cảnh báo | Sau khi đã có thứ đáng đo | 2 |
| 6 | Trino | Khi cần truy vấn liên nguồn; phải chọn nơi chạy vì K3s không còn | 3 |
| 7 | **OpenMetadata (phương án B)** | Nó **ăn** siêu dữ liệu của các tầng dưới. Dựng trước thì không có gì để ăn | 3, 4, 6 |
| 8 | Superset | Giao diện cuối, chỉ có nghĩa khi Trino đã chạy | 6 |

Bước 7 kéo theo hai việc phụ trên LXC 213, đã ghi chi tiết ở mục 7 của tài liệu khảo sát:
nâng rootfs 20 GB → 100 GB (thin pool còn ~1,5 TiB nên gần như không tốn), và nâng heap
2 GB → 4 GB khi tải thật tăng. Cả hai phải đi qua role ansible, không gõ tay.

## 7. Rủi ro

| Rủi ro | Mức | Ghi chú |
|---|---|---|
| **Tài liệu mô tả hạ tầng không tồn tại** | Cao | `data-infra/_overview.md` và các tài liệu vận hành của repo này mô tả VM 106 và K3s như đang chạy. Phải đánh dấu tại chỗ ngay, trước khi ai đó thao tác theo |
| **SeaweedFS không có role ansible** | Cao | Toàn bộ dữ liệu lake nằm ở đó. Không có role nghĩa là không tái lập được nếu hỏng |
| **Chưa xác minh sao lưu cho collection `lakehouse`** | Cao | Chưa kiểm trong phiên này |
| **Địa chỉ S3 mâu thuẫn giữa các tài liệu** | Trung bình | `CLAUDE.md` của repo này ghi `192.168.0.102:30333` — nút K3s đã chết. Đường đúng là `192.168.0.200:8333`, khớp với `data-infra/trino/catalog-iceberg.properties` |
| **Tên bucket không thống nhất** | Trung bình | Repo này dùng `lakehouse/bronze/stock/...`; thiết kế di trú của 01-Tracking dùng `s3://messaging/bronze/...` |
| **PostgreSQL 204 thành điểm hỏng chung** | Trung bình | Sẽ gánh `windmill`, `labelstudio`, `chatbot_db`, thêm `iceberg_catalog` và `openmetadata`. Tải hiện rất nhẹ nhưng cần theo dõi |

## 8. Còn mở, cần quyết

| Câu hỏi | Ảnh hưởng |
|---|---|
| Trino chạy ở đâu khi không còn K3s | Chặn bước 6 và 8 |
| Prometheus chạy ở đâu, thu những đích nào | Chặn bước 5 |
| Cảnh báo gửi đi đâu | Chặn bước 5 |
| Retention log giữ 7 hay 30 ngày | Ảnh hưởng thiết kế kho Loki |
| Có dựng lại Redis không | `_overview.md` ghi Redis làm cache cho Superset — chỉ cần khi tới bước 8 |
| Tên bucket cho nguồn `messaging` | Cần chốt trước khi 01-Tracking viết phần ghi bronze |

## Related

- `docs/2026-08-05-catalog-metadata-probe__ai1.md`
- `docs/adr/2026-08-05-retire-prefect-adopt-dagster.md`
- `docs/adr/2026-04-13-platform-decisions.md`
- `docs/architecture.md`
- `docs/seaweedfs-ops.md`
- `docs/runbook.md`
- `CLAUDE.md`
