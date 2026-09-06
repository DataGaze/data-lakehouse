# Thiết kế triển khai Trino — giai đoạn 1

> Ngày: 2026-09-06 · Trạng thái: đã duyệt, chờ lập kế hoạch thi công
> Mọi số đo hạ tầng trong tài liệu này lấy trực tiếp trên promax ngày 2026-09-06 qua
> `ssh root@100.89.161.125`, chỉ đọc, chưa thay đổi gì.

## 1. Bối cảnh

`docs/2026-08-05-lakehouse-upgrade-framework__ai1.md` xếp Trino là **bước 6** trong tám bước
dựng lại nền tảng, và ghi rõ hai thứ chặn nó: K3s không còn nên chưa có nơi chạy, và tầng
log-giám sát (bước 2) lẽ ra phải đi trước.

Quyết định của phiên này: **làm Trino trước, tầng log làm sau**. Đánh đổi được chấp nhận có ý
thức — khi Trino lỗi sẽ phải chẩn đoán bằng `journalctl` tại chỗ trên LXC 220 thay vì tra tập
trung. Ghi lại ở đây để lần sau không phải tranh luận lại vì sao thứ tự bị đảo.

Trino cũ chạy trên K3s (bản 439, NodePort 30080). Cụm K3s và VM 106 đã bị xoá, nên đây là
**dựng lại**, không phải nâng cấp. Cấu hình cũ còn trong `OPS01-homelab/data-infra/trino/` và
`OPS01-homelab/k3s/trino/`, dùng làm tham chiếu chứ không dùng lại nguyên văn (lý do ở mục 7).

## 2. Hiện trạng đo được

| Hạng mục | Số đo 2026-09-06 |
|---|---|
| promax | 20 nhân, 94 GB RAM (81 GB rảnh), root 63 GB trống, `local-lvm` 1,5 TB trống, HDD 1,2 TB trống |
| LXC đang chạy | 18 (200, 202–211, 213–219) — 201, 212, 220 trống |
| IP đã dùng trong `192.168.0.0/24` | .104, .105, .106, .111, .113, .116–.124, .127, .128, .203, .213 |
| LXC 202 `stock-gold` | PostgreSQL trong Docker, DB `stock_market`: `ticks` 12 GB, `candles_5m` 690 MB, `microstructure_5m` 569 MB, `candles_15m` 471 MB, `daily_ohlcv` 6,8 MB. Vai đăng nhập duy nhất: `stock` |
| LXC 204 `pg-backend` | PostgreSQL 17.9. DB: `llm_logs` 455 MB, `nocodb_meta` 54 MB, `nocodb_content` 21 MB, `n8n` 16 MB, `labelstudio` 14 MB, `windmill` 21 MB, `chatbot_db` 8,5 MB, `llm_logs_test` 8,2 MB |
| LXC 205 `superset` | Superset 4.1.4, venv Python 3.11, SQLAlchemy 1.4.54. **Chưa có driver Trino** |
| SeaweedFS | Sống: S3 `192.168.0.200:8333`, master `:9333`, filer `:8888` |
| Iceberg catalog | Chưa tồn tại. Cấu hình cũ trỏ `192.168.0.106:5432/iceberg_catalog`; địa chỉ .106 nay thuộc LXC 214 `promax-gpu`, không phải VM cũ |
| Template LXC | `debian-13-standard_13.1-2`, `debian-12-standard_12.12-1`, `ubuntu-24.04-standard_24.04-2` |

## 3. Phạm vi

**Trong phạm vi:** một nút Trino duy nhất (vừa coordinator vừa worker) làm tầng truy vấn liên
nguồn cho hai cụm PostgreSQL đang chạy; lọc cổng ở mức mạng; nối lại Superset.

**Ngoài phạm vi, để giai đoạn 2:** Iceberg trên SeaweedFS và catalog JDBC đi kèm; tầng
log-giám sát; Dagster; cụm nhiều worker; xác thực người dùng ở tầng ứng dụng.

Ranh giới sở hữu: `OPS01-homelab` giữ vòng đời máy chủ (LXC, role, ghim phiên bản, sao lưu,
healthcheck). `DATA02-lakehouse` giữ quyết định nền tảng và tài liệu kiến trúc.

Trino **không ghi** vào nguồn nào ở giai đoạn 1 — mọi tài khoản đều chỉ đọc.

## 4. Máy chủ

| Thuộc tính | Giá trị | Lý do |
|---|---|---|
| LXC ID | 220 | 201 và 212 cũng trống, nhưng 201 từng là `prefect-server`; dùng ID mới để không lẫn với dấu vết cũ |
| Hostname | `trino` | |
| IP | 192.168.0.125/24, gateway 192.168.0.1 | Khai cứng trong `/etc/pve/lxc/220.conf` như 204/216/218/219, KHÔNG dùng DHCP — tránh lặp lại điều kiện đã gây sự cố bốn tháng ở LXC 211 |
| Nền | Debian 13 (`debian-13-standard_13.1-2`) | Cùng bản với n8n, omniroute, nocodb |
| Nhân | 6 | |
| RAM | 16384 MB, swap 512 | Heap 8 GB cộng bộ nhớ ngoài heap của JVM cộng đệm hệ điều hành |
| Đĩa | `local-lvm`, 40 GB | Tarball 851 MB, JDK 141 MB, cộng chỗ cho spill khi truy vấn lớn |
| TUN | `lxc.cgroup2.devices.allow: c 10:200 rwm` + mount `/dev/net/tun` | Để vào tailnet, truy vấn được từ MacBook Air mà không phải nhảy qua promax |
| `nesting` | Không bật | Chạy native, không có Docker trong container này |
| `onboot` | 1 | |
| Timezone | `Asia/Ho_Chi_Minh` | |
| `unprivileged` | 1 | |

## 5. Artifact và ghim phiên bản

Hai mục **riêng** trong `ansible/versions.yml`. Tách vì chúng lên phiên bản độc lập với nhau —
cùng lý do đã tách `vaultwarden` khỏi `vaultwarden_web`: nâng cái này không tự kéo cái kia, mà
gộp một mục thì sự lệch đó không có gì báo.

| Mục | Kho nguồn | Phiên bản | Tệp | Kích thước | sha256 |
|---|---|---|---|---|---|
| `trino` | `trinodb/trino` | `483` (phát hành 2026-07-18) | `trino-server-483.tar.gz` | 851 MB | `4f3978428f26f36398c94b85a3e03b5301394919c8a4271b497b0fcd1698d0cb` |
| `trino` (cli) | `trinodb/trino` | `483` | `trino-cli-483` | 15,8 MB | `182a1daca97bd14e7aa9b25cb62c6d0fd96fa80313e5431ac91da3184cebb601` |
| `trino_jdk` | `adoptium/temurin25-binaries` | `jdk-25.0.4.1+1` | `OpenJDK25U-jdk_x64_linux_hotspot_25.0.4.1_1.tar.gz` | 141 MB | `dbb698396d478e7fa2b1e50f4103324b2a99b90569ee27c33f2261f9215cf41e` |

`hash_source` cho hai mục Trino là `GitHub Releases API assets[].digest`, cho JDK là
`Adoptium API binary.package.checksum`.

Ghi chú phân phối: Trino **đã rời Maven Central**. `repo1.maven.org` dừng ở bản 476
(`maven-metadata.xml` ghi `lastUpdated` 2025-06-06); bản 483 chỉ có trên GitHub Releases. Ai
tra theo đường Maven cũ sẽ kết luận nhầm là 483 không tồn tại.

### 5.1 Vì sao ghim JDK vào kho riêng của dòng 25

Trino 483 chạy **đúng Java 25.x**: Java 24 và Java 26 đều bị từ chối ngay lúc khởi động, không
phải cảnh báo mà là dừng. Debian 13 không có `openjdk-25` mặc định, nên nếu lấy JDK qua `apt`
thì một lần `apt upgrade` trượt sang dòng 26 là Trino không lên lại được, và triệu chứng chỉ lộ
ra lúc khởi động lại — có thể hàng tuần sau khi nguyên nhân đã trôi khỏi trí nhớ.

Chốt chặn: ghim vào kho `adoptium/temurin25-binaries`, là kho **chỉ chứa dòng 25**. Nhờ vậy
`update-radar.sh` so bản mới nhất của chính kho đó nên không bao giờ đề xuất Java 26, và JDK
giải nén ra `/opt/jdk-25` nằm ngoài tầm quản lý gói.

Đây là bù đắp có chủ đích cho thứ mà bản đóng gói Docker vốn cho sẵn. Phương án Docker đã được
cân và loại ở phiên 2026-09-06; lý do chọn native là giữ đúng hình dạng của mười một role đang
chạy trực tiếp trên OS.

Cả hai tarball tải về `/opt/trino/`, giải nén xong xoá tệp nén để không giữ lại 851 MB thừa.

## 6. Catalog

Connector PostgreSQL của Trino ánh xạ **một catalog cho một database**. Số tệp catalog vì thế
bằng số database muốn mở, không phải số cụm.

| Tệp catalog | Đích | Nội dung |
|---|---|---|
| `gold.properties` | `192.168.0.113:5432/stock_market` (LXC 202) | `ticks`, `candles_*`, `microstructure_*`, `daily_ohlcv` |
| `telemetry.properties` | `192.168.0.119:5432/llm_logs` (LXC 204) | Đường ống log CLI agent — chỉ số, không giữ nội dung |
| `nocodb.properties` | `192.168.0.119:5432/nocodb_content` (LXC 204) | Nội dung do người soạn, gồm schema `toeic` |

Mở thêm database về sau tốn đúng một tệp, không sửa gì khác.

Cố ý **không** mở: `windmill`, `n8n`, `labelstudio`, `nocodb_meta`, `chatbot_db`,
`llm_logs_test`. Đó là siêu dữ liệu ứng dụng, không phải dữ liệu để phân tích; mở ra chỉ làm
rộng bề mặt đọc mà không thêm giá trị.

## 7. Cấu hình Trino

Cấu hình còn trong `OPS01-homelab/data-infra/trino/` là của bản 439 và **đã lỗi thời** —
thiếu `--add-modules=jdk.incubator.vector`, `-XX:+ExitOnOutOfMemoryError`,
`-XX:PerMethodRecompilationCutoff`, `-XX:PerBytecodeRecompilationCutoff`,
`-XX:-OmitStackTraceInFastThrow`, `-Djdk.nio.maxCachedBufferSize`. Viết lại theo khuyến nghị
của bản 483 thay vì chép lại.

Bốn tệp `config.properties`, `node.properties`, `jvm.config`, `log.properties` do template của
role sinh, không soạn tay trên máy.

Heap: `-Xmx8G` khai tường minh, **không** dùng `-XX:MaxRAMPercentage`. Trong LXC, giới hạn bộ
nhớ nhìn từ trong ra không phải lúc nào cũng là con số đặt ở `/etc/pve/lxc/220.conf`, nên số
phần trăm sinh ra một giá trị heap khó đoán trước; con số tuyệt đối thì đọc là biết.

`node.id` sinh một lần lúc provision và lưu lại; khởi động lại không được đổi danh tính nút.

## 8. Tài khoản và bí mật

Một vai chỉ đọc `trino_ro` trên mỗi cụm, hai mật khẩu khác nhau.

**LXC 202** (PostgreSQL chạy trong Docker, mọi lệnh psql phải qua `docker exec postgres-gold`,
vai đăng nhập hiện có là `stock`, không phải `postgres`):

```sql
CREATE ROLE trino_ro LOGIN PASSWORD '<...>';
GRANT CONNECT ON DATABASE stock_market TO trino_ro;
GRANT USAGE ON SCHEMA public TO trino_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO trino_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO trino_ro;
```

**LXC 204**: cùng khuôn, áp cho `llm_logs` và `nocodb_content`. Riêng `nocodb_content` chứa
nhiều schema (mỗi ứng dụng một schema, ứng dụng đầu là `toeic`) nên `GRANT USAGE` và
`ALTER DEFAULT PRIVILEGES` phải lặp cho từng schema, không chỉ `public`.

`pg_hba.conf` hai bên thêm đúng một dòng cho `192.168.0.125/32`.

Mật khẩu truyền lúc provision qua `-e trino_gold_password='<...>' -e trino_backend_password='<...>'`.
Role ghi vào `/etc/trino/catalog/*.properties`, chmod 600, sở hữu bởi user `trino`. `preflight.yml`
**REFUSE** nếu chưa có tệp catalog mà cũng không truyền mật khẩu — đúng khuôn `nocodb` đang dùng,
để không bao giờ sinh ra một tệp catalog có mật khẩu rỗng trông như đã cấu hình xong.

Bản ghi chính thức cất ở Vault `infra/trino`. Playbook **không** đọc Vault lúc chạy; không role
nào trong repo làm thế, và thêm một đường phụ thuộc lúc chạy sẽ khiến việc khôi phục thảm hoạ
phụ thuộc vào một dịch vụ khác cũng đang phải khôi phục.

## 9. Bảo vệ cổng — mức 1, lọc mạng

Trino mặc định **không có xác thực**. Mở cổng 8080 cho toàn LAN nghĩa là mọi máy trong
`192.168.0.0/24` đọc được `stock_market` và hai database sau lưng mà không cần thông tin đăng
nhập nào — đúng dạng nợ đang mắc ở OpenSearch LXC 213 (TD-28).

`nftables` trên LXC 220 chỉ cho cổng 8080 từ:

| Nguồn | Vì sao |
|---|---|
| `192.168.0.116/32` | Superset, LXC 205 |
| `192.168.0.107/32` | Mac mini, máy điều khiển ansible |
| `100.64.0.0/10` | Dải tailnet — truy vấn từ MacBook Air |

Phần LAN còn lại bị chặn.

Đây là nợ kỹ thuật có chủ đích. Ghi vào `OPS01-homelab/docs/tech-debt.md` kèm **điều kiện nâng
cấp viết sẵn**: khi có người dùng thật ngoài chủ sở hữu truy vấn Trino, chuyển sang xác thực
mật khẩu (mức 2) hoặc TLS kèm mật khẩu (mức 3). Viết điều kiện ra bây giờ để lần sau không phải
cân lại từ đầu.

## 10. Nối lại Superset

Superset 4.1.4 trên LXC 205 **chưa có driver Trino** (đã kiểm `pip list` ngày 2026-09-06:
không có `trino` lẫn `sqlalchemy-trino`). Cần thêm `trino[sqlalchemy]` vào venv
`/opt/superset/venv`.

Bản PyPI hiện tại là `trino` 0.339.0, yêu cầu `sqlalchemy>=1.3`, khớp với SQLAlchemy 1.4.54 mà
Superset đang chạy — **không** phải nâng SQLAlchemy, nên không đụng tới phần còn lại của
Superset.

Việc này thuộc role `superset`, không thuộc role `trino`: nó thay đổi vòng đời của LXC 205.
Ghim phiên bản `trino` python theo đúng cách `versions.yml` đang ghim các gói khác của Superset.

Chuỗi kết nối trong Superset: `trino://trino_ro@192.168.0.125:8080/gold`, một kết nối cho mỗi
catalog cần dùng.

## 11. Role ansible

Role `trino` đủ năm tệp tasks, đúng khuôn mười bốn role hiện có.

| Tệp | Việc |
|---|---|
| `preflight.yml` | Kiểm sha256 cả ba artifact trước khi chạm máy; kiểm hai cụm PostgreSQL trả lời; REFUSE nếu thiếu mật khẩu và cũng chưa có tệp catalog |
| `main.yml` | Cài JDK vào `/opt/jdk-25`, Trino vào `/opt/trino`, sinh bốn tệp cấu hình và ba tệp catalog, dựng unit `systemd`, nạp `nftables` |
| `update.yml` | Nâng phiên bản theo `versions.yml`, giữ nguyên tệp catalog và `node.id` |
| `backup.yml` | Chép cấu hình và catalog. Không có trạng thái nào khác phải giữ |
| `healthcheck.yml` | `GET /v1/info` phải báo `starting=false`, và một truy vấn thật qua `trino-cli` |

`backup.yml` mỏng là **có chủ đích**, không phải viết dở: Trino không sở hữu dữ liệu nào không
tái tạo được. Mất máy này thì dựng lại từ role, không mất gì ngoài lịch sử truy vấn trong bộ
nhớ. Ghi rõ ở đây để người đọc sau không tưởng là thiếu sót rồi thêm việc sao lưu vô nghĩa.

Thêm mục `trino` vào `ansible/inventory.yml`: `ansible_host: 192.168.0.125`, `lxc_id: 220`,
`tailscale_ip` để trống cho tới khi nút được duyệt vào tailnet. Không khai `db_lxc_id` —
Trino không sở hữu database nào; quan hệ ngược lại (nó đọc 202 và 204) thuộc về tệp catalog,
không thuộc về thông tin kết nối SSH.

## 12. Nghiệm thu

Máy phán, không phải người khai. Bảy phép, chạy hết mới tính là xong.

| # | Phép kiểm | Đạt khi |
|---|---|---|
| 1 | `trino-cli --execute "SHOW CATALOGS"` | Liệt kê `gold`, `telemetry`, `nocodb`, `system` |
| 2 | `SELECT count(*) FROM gold.public.daily_ohlcv` | Khớp số đếm chạy thẳng bằng `psql` trên LXC 202 |
| 3 | **Một câu lệnh đọc cả `gold` lẫn `telemetry`** | Trả kết quả — chứng minh truy vấn liên nguồn thật sự chạy, không phải hai kết nối rời nhau |
| 4 | `CREATE TABLE gold.public.x (i int)` | **Thất bại** — chứng minh vai chỉ đọc thật sự chỉ đọc |
| 5 | Từ LXC 217 (`openclaw`, ngoài danh sách cho phép) `curl` tới `192.168.0.125:8080` | Bị từ chối |
| 6 | `systemctl restart trino` rồi hỏi `/v1/info` | Xanh lại trong 90 giây |
| 7 | Superset chạy được một biểu đồ trên nguồn Trino | Biểu đồ hiển thị dữ liệu, không phải lỗi driver |

## 13. Đường thi công

MacBook Air không tới được LAN `192.168.0.x` (Air ở `192.168.1.0/24`), nên:

1. Sửa mã trong bản sao trên Air, `git commit` và `git push` ngay trong phiên
2. Mac mini `git pull` rồi chạy `ansible-playbook` từ đó — Mini nằm trên cả hai mạng nên là nơi
   duy nhất gọi thẳng được LXC
3. Việc tạo LXC 220 chạy trực tiếp trên promax qua Tailscale (`ssh root@100.89.161.125`)

Mọi lệnh ansible phải có tiền tố `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8` — locale `en_VN` của máy
làm công cụ Python nhạy locale dừng ngay lúc khởi động.

## 14. Rủi ro đã biết

| Rủi ro | Mức | Giảm nhẹ |
|---|---|---|
| JDK trượt sang dòng 26 làm Trino không khởi động | Cao nếu không chặn | Ghim vào kho chỉ chứa dòng 25; JDK nằm ngoài `apt` |
| Truy vấn `ticks` (12 GB) kéo cả bảng qua JDBC | Trung bình | Connector PostgreSQL đẩy được `WHERE` và `LIMIT` xuống nguồn; đặt `-Xmx8G` và theo dõi phép kiểm 3. Nếu đau thật thì đó là lý lẽ cho Iceberg ở giai đoạn 2, không phải lý do sửa vặt bây giờ |
| Không có tầng log tập trung khi Trino lỗi | Trung bình | Chấp nhận có ý thức (mục 1); chẩn đoán bằng `journalctl` trên LXC 220 |
| Cổng 8080 không xác thực trong vùng được phép | Trung bình | Lọc mạng mức 1 kèm điều kiện nâng cấp viết sẵn (mục 9) |
| Tarball 851 MB tải lại mỗi lần provision | Thấp | Tải một lần về `/mnt/hdd/artifacts/trino/` trên promax, giống khuôn đã dùng cho `vaultwarden` |

## 15. Giai đoạn 2 — Iceberg trên SeaweedFS (làm cùng ngày 2026-09-06)

### 15.1 Điều đo được làm đổi hình dạng của giai đoạn 2

Trước khi dựng, đo lại dung lượng thật của từng bucket bằng `weed shell s3.bucket.list`:

| Bucket | Dung lượng | Ghi chú |
|---|---|---|
| `lakehouse` | 24.768 B | `bronze/`, `silver/`, `gold/` chỉ có tệp `.keep` và một `test.json` |
| `stock-data` | 0 B | rỗng |
| `llm-logs` | 8,68 GB | log tác tử CLI, phân tầng sâu theo `<công cụ>/<máy>/<tháng>/<dự án>` |
| `project-assets` | 12,89 GB | tệp đính kèm, không phải dữ liệu phân tích |
| `learning-hub` | 3,27 GB | dữ liệu của một dự án khác |

Nghĩa là **hồ chưa có dữ liệu**: hai tầng Bronze và Silver rỗng, dữ liệu thật đang nằm trong
PostgreSQL Gold trên LXC 202. Nên giai đoạn 2 không thể là "mở Iceberg để đọc hồ sẵn có" — nó
chỉ có thể là **dựng đường ghi** để về sau có hồ. Điều đó đổi tiêu chí nghiệm thu: bằng chứng
phải là một bảng Iceberg do chính Trino tạo ra từ dữ liệu thật, không phải một truy vấn đọc.

### 15.2 Kiến trúc chọn

Catalog JDBC trên PostgreSQL 204, **không** dựng Hive metastore: bớt một dịch vụ phải nuôi, một
unit phải giám sát, một nguồn hỏng. Kho tệp là SeaweedFS S3 qua `fs.native-s3.enabled`.

| Thành phần | Giá trị | Vì sao |
|---|---|---|
| Kiểu catalog | `jdbc` | Không cần Hive metastore; siêu dữ liệu nằm trong CSDL đã có sẵn người trông |
| CSDL catalog | `iceberg_catalog` trên 192.168.0.119, vai `iceberg_cat` | Cùng cụm với `telemetry`; tách CSDL nên không đụng dữ liệu nghiệp vụ |
| Kho tệp | `s3://lakehouse/warehouse/` | Để riêng dưới `warehouse/`; gốc bucket đã có `bronze/`, `silver/`, `gold/` theo quy ước cũ |
| Định dạng | Parquet | Khớp quy ước Bronze/Silver đang khai trong CLAUDE.md của repo |
| Danh tính S3 | `trino`, phạm vi đúng bucket `lakehouse` | Xem 15.3 |

### 15.3 Iceberg đổi hạng của rủi ro, không đổi lớp bảo vệ

Ba catalog của giai đoạn 1 đều chỉ đọc, nên tình huống xấu nhất qua cổng 8080 là **lộ dữ liệu**.
Iceberg biến Trino thành bên **ghi**: cùng đường đó giờ `CREATE`, `INSERT` và `DROP` được. Lộ dữ
liệu và mất dữ liệu không cùng một hạng.

Vì Trino vẫn chưa có xác thực (nợ TD-43, điều kiện nâng cấp đã viết sẵn từ giai đoạn 1), phạm vi
hỏng được chặn ở **nơi dữ liệu rơi xuống**, không phải nơi truy vấn xuất phát: danh tính S3
`trino` chỉ có `Read/Write/List/Tagging` trong bucket `lakehouse`, tuyệt đối không dùng `admin`.
Tình huống xấu nhất do đó gói gọn trong một bucket và một CSDL catalog, không chạm được
`learning-hub`, `llm-logs`, `project-assets` hay bucket nào khác.

### 15.4 Một cái bẫy đã đo được

Trino **không tự tạo** hai bảng bookkeeping của Iceberg. Truy vấn đầu tiên hỏng với `Cannot check
and eventually update SQL schema`; nguyên nhân thật nằm sâu ba tầng trong chuỗi ngoại lệ:
`relation "iceberg_tables" does not exist`. Câu báo lỗi ngoài cùng không nhắc tên bảng lẫn tên
CSDL nên rất giống lỗi kết nối, mà `SHOW CATALOGS` thì vẫn liệt kê `iceberg` bình thường và
healthcheck vẫn xanh.

Lược đồ áp bằng tay từ `OPS01-homelab/data-infra/iceberg/catalog-schema.sql`. Role không tạo,
không kiểm — nợ kỹ thuật TD-44, kèm lý do vì sao chưa gộp vào role.

### 15.5 Nghiệm thu giai đoạn 2 — sáu phép, chạy thật

| # | Phép | Kết quả đo được |
|---|---|---|
| 1 | `CREATE SCHEMA iceberg.silver` | `CREATE SCHEMA` |
| 2 | `CREATE TABLE ... AS SELECT * FROM gold.public.daily_ohlcv` | `CREATE TABLE: 47024 rows` |
| 3 | Đọc lại từ Iceberg | `47024` — khớp nguồn PostgreSQL |
| 4 | Tệp thật trên SeaweedFS | `data/` một Parquet 494.706 B; `metadata/` đủ `metadata.json`, manifest `.avro`, snapshot `.avro`, `.stats`. Bucket `lakehouse` từ 24.768 B lên 663.704 B |
| 5 | Bản ghi trong catalog PG 204 | một dòng trong `iceberg_tables`: catalog `iceberg`, namespace `silver`, bảng `daily_ohlcv`, trỏ `s3://lakehouse/warehouse/silver/daily_ohlcv-81262b3e...` |
| 6 | Câu đọc Iceberg (S3) nối telemetry (PG 204) | gold 27.561 + 19.463 = 47.024 đọc **từ S3**, telemetry trả số của chính nó — một câu chạm hai tầng lưu trữ khác nhau |

Thêm hai phép phụ: `SELECT snapshot_id, operation FROM iceberg.silver."daily_ohlcv$snapshots"`
trả đúng một ảnh chụp `append`; và Superset chạy được `SELECT count(*)` qua nguồn
`Trino - iceberg` bằng chính engine của nó, trả `47024`.

## Related

- `docs/2026-08-05-lakehouse-upgrade-framework__ai1.md`
- `docs/2026-08-05-catalog-metadata-probe__ai1.md`
- `docs/architecture.md`
- `docs/superset-setup.md`
