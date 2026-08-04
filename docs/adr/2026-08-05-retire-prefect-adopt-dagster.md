# ADR — Gỡ Prefect, chuyển orchestration sang Dagster (2026-08-05)

## Status

Accepted. Thay thế phần orchestration của [D4 trong ADR 2026-04-13](./2026-04-13-platform-decisions.md#d4-orchestration--transform-stack).
Các quyết định còn lại của D4 (Polars cho Bronze → Silver, dbt cho Silver → Gold) giữ nguyên.

## Context

D4 chốt Prefect 3 làm tầng điều phối và hạ tầng đã dựng theo đúng quyết định đó:
`prefect-server` trên LXC 201 (SQLite metadata) và `prefect-worker` trên LXC 202,
pool `stock-pool`. Cả hai chạy từ 2026-04-02.

Kiểm tra ngày 2026-08-05 cho thấy tầng này chưa bao giờ đi vào vận hành:

| Chỉ số | Giá trị đo được |
|---|---|
| Deployment đăng ký trên server | 0 |
| Flow run từ khi dựng | 0 |
| CPU worker tiêu thụ trong 2,5 tuần | 6 phút 49 giây (chỉ poll pool rỗng) |
| Cron/timer gọi ETL trên LXC 202 | không có |

Nguyên nhân: `serve.py` trong `stock-data-pipeline` — thứ tạo ra hai deployment
`daily-stock-etl` và `stock-healthcheck` — chưa từng được chạy. Pipeline vẫn chạy
bằng tay qua CLI khi cần.

Đồng thời phạm vi 6–12 tháng tới đã rõ hơn so với lúc ra D4: lakehouse phục vụ
nhiều nguồn (stock, BĐS, nguồn mới), cần backfill theo ngày cho từng nguồn và
theo dõi được chất lượng ở từng tầng medallion.

## Decision

Gỡ Prefect. Chuyển tầng điều phối sang **Dagster**, mô hình hóa theo asset.

Lý do chọn Dagster thay vì giữ Prefect hoặc dùng systemd timer:

| Phương án | Vì sao không / vì sao có |
|---|---|
| Giữ Prefect | Công cụ không phải vấn đề kỹ thuật, nhưng đã có 4 tháng để chứng minh và không được dùng; giữ lại là giữ một tầng không ai chạm |
| systemd timer + CLI | Gọn nhất, nhưng backfill từng ngày cho từng nguồn phải tự viết script, và không có chỗ nào nhìn được tầng nào của medallion đã có dữ liệu ngày nào |
| **Dagster** | Partition theo ngày và backfill là tính năng sẵn có; asset graph khớp trực tiếp với Bronze → Silver → Gold; asset check gắn quality check vào đúng bảng nó kiểm |

Ghi rõ để không nhầm về sau: **Dagster không nhẹ hơn Prefect về vận hành** — nó cần
webserver, daemon và Postgres metadata. Chọn nó vì lineage và backfill theo partition,
không vì gọn.

## Consequences

Đã thực hiện trong ngày ra quyết định:

- `prefect-server` (LXC 201) và `prefect-worker` (LXC 202): stopped + disabled.
  Container 201 giữ lại để tái dùng IP/tài nguyên; `prefect.db` còn trên đĩa.
- `stock-data-pipeline`: gỡ dependency `prefect`, bỏ decorator `@flow`/`@task`,
  xóa `serve.py`, bỏ `PREFECT_API_URL`. Mỗi bước pipeline giờ là hàm Python thuần
  gọi được qua CLI (101/101 test pass sau khi gỡ).
- Toolkit `agentsmith`: gỡ `prefect-run.sh` cùng test và tài liệu của nó.

Hệ quả cần chấp nhận trong giai đoạn chuyển tiếp:

- **Không có scheduler nào đang chạy.** ETL chỉ chạy khi gọi tay. Trạng thái này
  đúng với thực tế trước đây, chỉ là giờ được ghi ra thay vì ẩn sau một service rỗng.
- **Retry biến mất khỏi code.** Trước đây khai trong tham số decorator
  (`retries=2, retry_delay_seconds=15`) nhưng chưa từng có hiệu lực vì không qua
  Prefect runtime. Sẽ khai lại ở tầng Dagster.
- Tài liệu vận hành mô tả Prefect (runbook, security, sla, sequences) không còn
  hiệu lực. Được đánh dấu tại chỗ thay vì viết lại ngay: viết lại khi Dagster đã
  chạy thật thì mới mô tả đúng, tránh thay một tập tài liệu hư cấu bằng tập khác.

## Tiêu chí nghiệm thu

Việc chuyển đổi chỉ được coi là xong khi **một chu kỳ ETL thật chạy xanh qua Dagster**
(Bronze → Silver → Gold cho một ngày giao dịch, quality check pass, alert gửi được),
không phải khi Dagster cài xong.

## Related

- `docs/adr/2026-04-13-platform-decisions.md`
- `docs/architecture.md`
- `docs/runbook.md`
