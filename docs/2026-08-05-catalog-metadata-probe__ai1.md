# Khảo sát định dạng bảng, catalog và OpenMetadata (2026-08-05)

> Ghi chú khảo sát, **chưa phải quyết định**. Số liệu hạ tầng đo trực tiếp trong ngày;
> thông tin sản phẩm trích từ tài liệu chính thức của nhà phát hành.
> Phần orchestration đã có quyết định riêng tại `docs/adr/2026-08-05-retire-prefect-adopt-dagster.md`.

## 1. Câu hỏi đang mở

Kho tin nhắn (`PER01-lifeos/01-Tracking`) sắp đổ vào lake này, đặt ra ba câu chưa có ADR:

1. Giữ Parquet trần hay lên định dạng bảng (Iceberg / Delta / DuckLake)?
2. Nếu lên Iceberg thì catalog loại nào?
3. Có dựng OpenMetadata không, và tốn thêm bao nhiêu dịch vụ?

## 2. Đo được trên hạ tầng

Đo ngày 2026-08-05 qua `ssh root@100.89.161.125`, chỉ đọc, không thay đổi gì.

### 2.1 OpenSearch — LXC 213 `kb-opensearch`

| Hạng mục | Giá trị |
|---|---|
| Phiên bản | **3.7.0** (`distribution: opensearch`, `build_type: deb`, build 2026-06-03) |
| Lucene | 10.4.0 |
| Cụm | `opensearch`, **một nút**, vai trò `dimr` |
| Heap | tối đa 2 GB, đang dùng 20% |
| Giới hạn LXC | 4 nhân, 8192 MB RAM, rootfs 20 GB, swap 1024 MB |
| Đĩa | còn trống 15,2 GB / tổng 19,5 GB |

Index đang có: `gartner-docs` (2.257 tài liệu, 54,8 MB), `kb-sources` (272), `kbtest-sources` (3),
`.plugins-ml-config` (1), và 8 index `top_queries-*` theo ngày.

[WARN] `_cat/nodes` báo `ram.max = 94gb`, trong khi giới hạn thật là 8192 MB. **Đừng dựa vào
con số 94 GB để tính heap.**

Nguyên nhân KHÔNG phải do container nhìn thấy RAM máy chủ: kiểm lại thì `lxcfs` đang hoạt động
(9 điểm gắn) và `/proc/meminfo` trong container báo đúng `MemTotal: 8388608 kB`. Nhiều khả năng
OpenSearch đọc tổng bộ nhớ một lần lúc khởi động, qua đường vòng qua `lxcfs`. Chưa xác định chắc
chắn — nhưng dù nguyên nhân là gì, kết luận thực dụng vẫn giữ: lấy `pct config 213` làm chuẩn,
không lấy số OpenSearch tự báo.

### 2.2 Đối chiếu với yêu cầu OpenMetadata

| Hạng mục | OpenMetadata yêu cầu | Thực tế | Kết luận |
|---|---|---|---|
| OpenSearch | 3.x — tối thiểu 3.0.0, khuyến nghị 3.3.0 | 3.7.0 | [OK] đạt, nhưng cao hơn mức khuyến nghị — kiểm lại lúc cài |
| vCPU cụm tìm kiếm | 2 | 4 | [OK] |
| RAM cụm tìm kiếm | 8 GiB | 8 GiB | [WARN] đúng sàn, không dư |
| Đĩa cụm tìm kiếm | 100 GiB mỗi nút | 20 GB, còn 15,2 GB | **[FAIL] thiếu nhiều** |
| PostgreSQL | 15 trở lên | LXC 204 chạy bản 17 *theo tài liệu, chưa kiểm lại* | [OK] tạm tính |

**Ràng buộc thật là đĩa, không phải phiên bản.** Phiên bản OpenSearch đã đạt; muốn dùng chung
cụm này cho OpenMetadata thì phải nâng rootfs của LXC 213.

## 3. Trích từ tài liệu chính thức

### 3.1 Định dạng bảng

| | Trạng thái | Catalog riêng | Engine đọc được |
|---|---|---|---|
| DuckLake | v1.0 tháng 4/2026, production-ready, cam kết tương thích ngược | Không cần — dùng PostgreSQL / SQLite / DuckDB | **Chỉ DuckDB** |
| Delta Lake | Trưởng thành | Không cần — nhật ký trong `_delta_log/` | Nhiều, qua `delta-rs` không cần Spark |
| Iceberg | Chuẩn chung | **Cần** | Trino, Spark, DuckDB, Flink… |
| Hudi / Paimon | Trưởng thành | Cần | Thiên về Spark / Flink — không hợp stack hiện tại |

### 3.2 OpenMetadata

Connector có: **Trino (PROD)**, **S3 Datalake / S3 Storage (PROD)**, **Dagster (PROD)**.

Connector **không có**: DuckDB, Iceberg trực tiếp (nhìn được gián tiếp qua Trino),
Windmill, Prefect.

Phần thu thập chạy được **ngoài Airflow**: `metadata ingest -c <tệp yaml>`, hoặc gọi Python
`MetadataWorkflow.create(...).execute()`. Khai `ingestionPipelineFQN` trong tệp cấu hình thì
lần chạy vẫn hiện trạng thái trên giao diện; đổi lại các nút thao tác trong giao diện bị tắt.

Phiên bản tối thiểu: OpenSearch 3.x (khuyến nghị 3.3.0) · Elasticsearch 9.x (khuyến nghị 9.3.0)
· PostgreSQL 15+ · MySQL 8.0.42+.

Định mức tài nguyên cho môi trường thật: cơ sở dữ liệu 4 vCPU / 16 GiB / 100 GB ·
tìm kiếm 2 vCPU / 8 GiB / 100 GiB mỗi nút · Airflow 4 vCPU / 16 GiB / 100 GiB.
Con số "6 GiB / 4 vCPU" trên trang hướng dẫn Docker là mức chạy thử trên máy cá nhân,
không phải mức vận hành.

### 3.3 Dagster và DuckLake

Gói `dagster-ducklake` do **elementl** (Dagster Labs) phát hành, tức là chính thức.
Bản mới nhất **0.0.4** ngày 22/05/2026, tổng cộng 4 bản trong khoảng 7 tháng.
Nó cung cấp `DuckLakeResource` — là **resource**, không phải IO manager: Dagster cấp kết nối,
người dùng tự viết SQL trong asset.

### 3.4 MinIO — loại

Bản cộng đồng đã gỡ bảng quản trị (5/2025), chuyển sang chế độ bảo trì (12/2025),
và **kho mã bị lưu trữ ngày 25/04/2026** — chỉ đọc, không bản phát hành mới, không binary
chính thức. Không chuyển sang MinIO. Iceberg không đòi hỏi MinIO; nó chỉ cần object storage
nói giao thức S3, mà SeaweedFS đã có.

## 4. Kết luận sơ bộ

**DuckLake bị loại dù đã production-ready.** Nó chỉ cho DuckDB đọc, mà OpenMetadata không có
connector DuckDB. Chọn DuckLake là chọn một kho mà catalog không nhìn thấy. Với lake dùng chung
ba nguồn (`stock`, `bds`, `messaging`) thì khoá vào một engine duy nhất ở tầng hạ tầng là thứ
khó gỡ về sau.

**Iceberg là hướng phù hợp**, đánh đổi bằng việc phải dựng thêm một catalog.

**OpenMetadata khả thi hơn tưởng ban đầu.** Sau khi bỏ Airflow và dùng chung hạ tầng sẵn có:

| Thành phần | Dựng mới? |
|---|---|
| Cơ sở dữ liệu | Không — PostgreSQL ở LXC 204 |
| Bộ máy tìm kiếm | Không — OpenSearch 3.7.0 ở LXC 213, **với điều kiện nâng đĩa** |
| Airflow | Không — gọi `metadata ingest` từ Dagster |
| OpenMetadata server | Có |

Từ bốn dịch vụ xuống còn một. Gọi `metadata ingest` từ một asset Dagster còn cho một lợi ích
phụ: cập nhật catalog trở thành một mắt xích trong đồ thị tài sản, chạy ngay sau ETL, thay vì
một lịch riêng chạy lệch pha rồi hiển thị dữ liệu cũ.

Nguyên tắc xuyên suốt: **giữ logic ETL trong repo phát triển dạng lệnh dòng lệnh, đừng để bộ
điều phối giữ logic.** Như vậy đổi bộ điều phối về sau chỉ là viết lại phần gọi.

## 5. Còn mở, cần quyết

| Câu hỏi | Vì sao chưa quyết được |
|---|---|
| OpenMetadata phục vụ phạm vi nào | Riêng kho tin nhắn thì không đáng; làm catalog chung cho cả `stock`, `bds`, `messaging` thì hợp lý — nhưng khi đó là việc của tầng lakehouse, cần kế hoạch riêng |
| Catalog Iceberg loại nào | REST, JDBC trên PostgreSQL 204, hay Nessie — chưa khảo sát |
| Nâng đĩa LXC 213 lên bao nhiêu | Phụ thuộc câu 1 |
| Dùng chung cụm OpenSearch có va nhau không | OpenMetadata tự tạo index; phần Data Insights hiện chưa cho cấu hình tên index (yêu cầu tính năng open trên kho mã upstream) |

## 6. Lệch tài liệu phát hiện lúc khảo sát

Ghi lại để xử lý riêng, không sửa trong ghi chú này:

- **LXC 201 không còn trong `pct list`.** ADR `2026-08-05-retire-prefect-adopt-dagster.md`
  viết "Container 201 giữ lại để tái dùng IP/tài nguyên" — cần đối chiếu lại.
- **Bảng container trong `All_projects/CLAUDE.md` thiếu bảy mục**: 207 `ssi-reader`,
  208 `indicator-engine`, 210 `ai-lxc`, 212 `headscale`, 213 `kb-opensearch`,
  214 `promax-gpu`, 215 `labelstudio`.
- **Địa chỉ S3 không khớp giữa hai tài liệu.** `DATA02-lakehouse/CLAUDE.md` ghi
  `S3_ENDPOINT=http://192.168.0.102:30333` (NodePort của K3s), còn thiết kế di trú của
  01-Tracking dùng `http://192.168.0.200:8333` (cổng S3 trực tiếp trên promax). Cần chốt
  một đường chuẩn trước khi khối ghi bronze được viết.
- **Tên bucket cũng khác**: lake dùng `lakehouse/bronze/stock/...`, thiết kế 01-Tracking
  dùng `s3://messaging/bronze/...`. Cần đưa vào hợp đồng giữa hai bên.

## 7. Đề xuất nâng cấp và sửa chữa

Chưa thực hiện gì. Cả ba đề xuất dưới đây đều là thay đổi trên môi trường đang chạy, nên phải
đi đường OPS (role ansible + sao lưu trước), không gõ tay tại chỗ.

### 7.1 Nâng rootfs LXC 213 từ 20 GB lên 100 GB

Khả thi. Số đo ngày 2026-08-05:

| Hạng mục | Giá trị |
|---|---|
| `local-lvm` (lvmthin) | tổng ~1,71 TiB, đã dùng **12,04%**, còn ~1,5 TiB |
| VG `pve` | VSize 1,86 TiB, VFree 16,25 GB |
| rootfs LXC 213 | 20 GB, đã dùng **3,3 GB (18%)** |

Con số VFree 16,25 GB của VG trông đáng lo nhưng không cản trở: đó là phần chưa cấp phát nằm
**ngoài** thin pool. Chỗ thật để lấy là trong `local-lvm`, còn khoảng 1,5 TiB.

Vì là thin provisioning nên cấp 100 GB **không chiếm ngay 100 GB** — chỉ chiếm theo lượng ghi
thật, hiện mới 3,3 GB. Đây là lý do nên cấp rộng tay ngay từ đầu thay vì nâng dần.

Lệnh đề xuất (chưa chạy): `pct resize 213 rootfs +80G`

[WARN] Mức 100 GiB là khuyến nghị của OpenMetadata cho môi trường doanh nghiệp. Catalog cho ba
nguồn ở quy mô này sẽ nhỏ hơn nhiều — 60 GB nhiều khả năng đã dư. Chọn 100 GB không phải vì cần,
mà vì thin provisioning khiến chi phí của việc cấp rộng gần bằng không.

### 7.2 Nâng heap JVM từ 2 GB lên 4 GB

`/etc/opensearch/jvm.options` hiện đặt `-Xms2g -Xmx2g` trên container 8192 MB — tức **25% RAM**,
trong khi hướng dẫn chung của OpenSearch là khoảng 50%. Đáng chú ý: chính tệp đó đã có sẵn hai
dòng `## -Xms4g` và `## -Xmx4g` đang bị chú thích.

Chưa gấp — heap mới dùng 20%. Chỉ nên nâng khi OpenMetadata thật sự bắt đầu ghi index. Thao tác
cần khởi động lại dịch vụ, tức là gián đoạn `gartner-docs` và `kb-sources`.

### 7.3 Đưa LXC 213 vào khuôn as-code

`OPS01-homelab/ansible/roles/` hiện chỉ có `common`, `labelstudio`, `windmill`. OpenSearch được
cài bằng gói deb, nằm ngoài khuôn — cùng tình trạng vaultwarden trước đây.

Hai thao tác 7.1 và 7.2 nên được ghi thành role thay vì gõ tay, đúng quy tắc "không sửa trực tiếp
trên môi trường đã triển khai". Nếu gõ tay thì lần triển khai sau sẽ ghi đè mất.

### 7.4 Thứ tự thực hiện

| Thứ tự | Việc | Điều kiện |
|---|---|---|
| 1 | Chốt phạm vi OpenMetadata (riêng messaging hay chung cả lake) | Chưa quyết — xem mục 5 |
| 2 | Viết role ansible cho opensearch | Sau khi có 1 |
| 3 | Nâng rootfs qua role | Sau 2, có sao lưu |
| 4 | Nâng heap qua role | Chỉ khi tải thật tăng |

Không làm bước 3 và 4 trước bước 1: nếu phạm vi cuối cùng chỉ là kho tin nhắn thì có thể kết luận
là không dựng OpenMetadata, và cả hai lần nâng đều thừa.

## Related

- `docs/adr/2026-08-05-retire-prefect-adopt-dagster.md`
- `docs/adr/2026-04-13-platform-decisions.md`
- `docs/architecture.md`
- `docs/seaweedfs-ops.md`
- `CLAUDE.md`
