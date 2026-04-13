# SLA / SLO Definition — Data Lakehouse

| Field | Value |
|-------|-------|
| **Owner** | Hoàng Nguyễn (solo ops) |
| **Last Updated** | 2026-04-13 |
| **Version** | 0.1 |
| **Status** | Draft |
| **Scope** | Lakehouse platform (Bronze/Silver/Gold) phục vụ MarketPulse + future dashboards |
| **Review cadence** | Monthly (first Monday) |

---

## 1. Overview

### 1.1 Tại sao cần SLO ở home lab?

Home lab scale nhỏ, solo dev, 50 MB/day — nhưng vẫn cần SLO vì:

1. **Consumer contract rõ ràng**: MarketPulse gửi brief 17:45 hàng ngày. Nếu Gold trễ > 30 phút, user mất trust. Cần con số để biết "bao giờ alert, bao giờ ignore".
2. **Error budget chống over-engineering**: Không chạy theo 99.99% — biết được "99% là đủ" giúp tiết kiệm effort cho feature thay vì infra perfection.
3. **Burn rate alerting chống alert fatigue**: Khi nào Telegram ping, khi nào để mai fix — định lượng được.
4. **Post-mortem objective**: Có số để so sánh tháng này vs tháng trước, track debt thật sự.

### 1.2 SLI / SLO / SLA — phân biệt

| Thuật ngữ | Nghĩa | Ví dụ |
|-----------|-------|-------|
| **SLI** (Indicator) | Metric đo lường một thuộc tính dịch vụ | "% request < 2s" |
| **SLO** (Objective) | Target nội bộ của team cho SLI | "95% request < 2s trong 30 ngày" |
| **SLA** (Agreement) | Cam kết với consumer + consequence nếu vi phạm | "Nếu Gold trễ > 1h, escalate Telegram + post-mortem" |

**Nguyên tắc**: SLI ≤ SLO ≤ SLA (SLA lỏng hơn SLO để có buffer).

### 1.3 Triết lý realistic

- **Không** claim 99.99% uptime — solo ops, không có on-call rotation, Proxmox đơn node, không HA.
- **Có** claim đủ để MarketPulse dùng được hàng ngày, và đủ để chính mình không bị wake lên lúc 2 giờ sáng.
- Baseline: **99% uptime ≈ 7.2h downtime/month** — chấp nhận được cho use case "phân tích T+1", không chấp nhận được cho "realtime trading signal" (out of scope phase hiện tại).

---

## 2. Service Level Indicators (SLIs)

### 2.1 Freshness (data newness)

| SLI | Định nghĩa | Đo ở đâu |
|-----|-----------|----------|
| `bronze_lag_min` | `now() - max(bronze_file_mtime)` sau market close (15:00 ICT) | R2 object list timestamp |
| `silver_lag_min` | `now() - max(silver_partition_ts)` | SeaweedFS list + metadata |
| `gold_lag_min` | `now() - max(gold_table.loaded_at)` | Postgres `loaded_at` column |

### 2.2 Completeness

| SLI | Định nghĩa | Source |
|-----|-----------|--------|
| `bronze_completeness_pct` | `count(bronze_events) / count(expected_events_from_ssi_wal)` | So sánh R2 vs bizfly WAL counter |
| `silver_row_delta_pct` | `abs(silver_rows - bronze_rows) / bronze_rows` | Post-transform check |
| `gold_join_coverage_pct` | `count(gold_rows_with_non_null_fk) / count(gold_rows)` | dbt test |

### 2.3 Correctness

| SLI | Định nghĩa | Source |
|-----|-----------|--------|
| `dbt_test_pass_pct` | `passed / (passed + failed + error)` per run | dbt `run_results.json` |
| `schema_drift_events` | Count of Polars schema mismatch / ngày | Prefect log |
| `duplicate_rate_pct` | `dup_rows / total_rows` per Silver partition | Polars dedup counter |

### 2.4 Availability (uptime)

| SLI | Định nghĩa | Probe |
|-----|-----------|-------|
| `r2_availability_pct` | Successful HEAD / total HEAD per 5-min window | Prefect cron probe → R2 |
| `postgres_availability_pct` | Successful `SELECT 1` / total probes | Prefect cron probe |
| `prefect_api_availability_pct` | Prefect API `/api/health` 200 / total | External probe từ Mac mini |

### 2.5 Latency (query)

| SLI | Định nghĩa | Source |
|-----|-----------|--------|
| `gold_query_latency_p50/p95/p99` | Execution time của top 10 query patterns | Postgres `pg_stat_statements` |
| `flow_duration_p95` | End-to-end Prefect flow (R2 → Gold) duration | Prefect flow_run logs |

---

## 3. Service Level Objectives (SLOs)

Rolling window: **30 ngày trailing**. Tất cả số dưới đây là target nội bộ, được review monthly.

### 3.1 Freshness SLO

| Layer | SLO | Justify |
|-------|-----|---------|
| **Bronze** | `bronze_lag_min` < **30 min** sau market close (15:00 ICT), 95% ngày giao dịch | Bizfly cron upload 17:03 → R2 pull 17:30 → Bronze ready ~17:35. Buffer 30min cho network flakiness. |
| **Silver** | `silver_lag_min` < **45 min** sau market close, 95% ngày | Polars transform ~5-10min sau Bronze. |
| **Gold** | `gold_lag_min` < **60 min** sau market close, 95% ngày | dbt run ~10min sau Silver. MarketPulse brief 17:45 cần Gold ready. |
| **Backfill** | Không SLO (best-effort) | Chạy ngoài giờ, không block consumer. |

### 3.2 Completeness SLO

| SLI | SLO | Justify |
|-----|-----|---------|
| `bronze_completeness_pct` | **≥ 99.5%** events/day | Cho phép 0.5% loss do SSI SignalR disconnect — không thể kiểm soát từ phía client. |
| `silver_row_delta_pct` | **< 5%** so với Bronze | Dedup + filter invalid rows — 5% là guardrail, bình thường < 1%. |
| `gold_join_coverage_pct` | **≥ 99%** | FK join rate (stock vs index) phải cao. |

### 3.3 Correctness SLO

| SLI | SLO | Justify |
|-----|-----|---------|
| `dbt_test_pass_pct` | **≥ 99%** per run | dbt tests gồm `not_null`, `unique`, `accepted_values`. 1% grace cho flaky test. |
| `schema_drift_events` | **0** / tuần | Schema đổi → phải PR + migration có chủ đích. |
| `duplicate_rate_pct` | **< 0.1%** | Post-dedup, phải gần 0. |

### 3.4 Availability SLO

| Component | SLO | Monthly downtime budget | Justify |
|-----------|-----|------------------------|---------|
| **R2** | **99.9%** | 43 min | CF quản lý, tin tưởng external SLA của họ. |
| **Postgres (Gold)** | **99%** | 7.2h | Proxmox LXC 202, single node, không HA. Backup nightly. |
| **Prefect API** | **99%** | 7.2h | LXC 201, single node. |
| **SeaweedFS** | **98%** | 14.4h | Home lab, ISP + điện có thể cúp. Có backup R2 làm fallback cho Bronze. |

**Vì sao không 99.9% cho stack tự quản?** Solo ops, không có redundancy layer, ISP ở VN không SLA cho home. 99% = 7.2h/tháng ≈ một buổi tối debug/upgrade, thực tế đạt được.

### 3.5 Latency SLO

| SLI | SLO | Justify |
|-----|-----|---------|
| `gold_query_latency_p50` | < **500 ms** | Query dashboard + MarketPulse cần snappy. |
| `gold_query_latency_p95` | < **2 s** | Heavy aggregation query. |
| `gold_query_latency_p99` | < **5 s** | Tail latency acceptable cho ad-hoc. |
| `flow_duration_p95` | < **20 min** (E2E R2→Gold) | 50 MB/day nhỏ, không nên chậm hơn 20 phút. |

---

## 4. Service Level Agreements (SLAs) — per consumer

SLA là cam kết với **consumer cụ thể**, nới hơn SLO để có buffer. Home lab nên SLA chỉ mang tính "expectation contract" — không có credit model (nội bộ mà).

### 4.1 Consumer: MarketPulse (primary)

| Item | Agreement |
|------|-----------|
| **Data available time** | Gold table `daily_ohlc`, `daily_index` sẵn sàng trước **17:45 ICT** các ngày giao dịch, 95% tháng |
| **Data freshness** | Trễ nhất T+0 cho end-of-day data |
| **Availability** | 98% monthly (SLA < SLO 99% để có buffer) |
| **Breach consequence** | (a) Telegram alert immediately → (b) Post-mortem writeup trong 48h → (c) MarketPulse fallback về brief T-1 nếu Gold miss |

### 4.2 Consumer: Future dashboard / API

Chưa active. Khi onboard consumer mới, tạo **SLA appendix** riêng, không modify file này.

### 4.3 Consumer: Self (dev workflow)

| Item | Agreement |
|------|-----------|
| **dbt_dev_schema availability** | Best-effort. Không SLO. |
| **Backfill correctness** | Reconcile với production trong 24h sau backfill. |

---

## 5. Error Budget

Công thức: `budget = 1 - SLO`. Budget **được phép "đốt"** cho experiment, deploy, maintenance.

### 5.1 Ví dụ Gold availability

- SLO: 99% monthly → Budget: **7.2 giờ downtime / tháng**
- Nếu hết budget → **freeze deploy** đến cuối tháng, chỉ fix bug.
- Nếu còn nhiều budget (> 50% chưa tiêu) → thoải mái merge feature, thử schema migration mới.

### 5.2 Ví dụ Freshness

- SLO: 95% ngày có Gold < 60min → Budget: **1 ngày fail / 20 ngày giao dịch** (~1/tháng)
- Chi cho: scheduled maintenance (upgrade Postgres, migrate schema) — prefer cuối tuần khi không có trading data.

### 5.3 Budget spend log

Track trong `docs/slo-budget-log.md` (tạo khi cần):
```
YYYY-MM-DD | layer | event | budget_consumed | root_cause
```

---

## 6. SLO Burn Rate Alerting

Dựa trên [Google SRE burn rate](https://sre.google/workbook/alerting-on-slos/) — adapt cho solo ops.

### 6.1 Fast burn (page ngay lập tức)

**Condition**: Trong 1h, đốt ≥ 2% budget hàng tháng (= burn rate 14.4×).

| SLI | Fast burn trigger | Alert channel |
|-----|------------------|---------------|
| Gold availability | 3 probes fail liên tiếp (15 min) | **Telegram critical** |
| Freshness | Gold > 90 min sau market close (1.5× SLO) | **Telegram critical** |
| dbt test | Pass rate < 80% trong 1 run | **Telegram critical** |

### 6.2 Slow burn (review trong 24h)

**Condition**: Trong 6h, đốt ≥ 5% budget tháng (= burn rate 6×).

| SLI | Slow burn trigger | Alert channel |
|-----|------------------|---------------|
| Postgres availability | Uptime tuần < 99.5% | **Telegram info** |
| Silver row delta | Delta > 3% 3 ngày liên tiếp | **Telegram info** |
| Flow duration P95 | > 25 min 2 ngày liên tiếp | **Telegram info** |

### 6.3 No-alert (log only)

- dbt test 1 failure, flaky — log, không page.
- Prefect worker restart lẻ tẻ — log.

---

## 7. Review Cadence

| Cadence | Hoạt động |
|---------|-----------|
| **Weekly (Mon)** | Scan Prefect flow_run + dbt run_results, update budget log nếu có incident. |
| **Monthly (1st Mon)** | Review trailing 30d SLO attainment. Nếu 2 tháng liền miss → điều chỉnh SLO hoặc đầu tư infra. Nếu 3 tháng liền thừa > 30% budget → tighten SLO. |
| **Quarterly** | Review SLA với consumer (MarketPulse owner = cùng người, self-review). Refresh version + status. |
| **Ad-hoc** | Sau mỗi incident lớn (> 2h downtime): post-mortem + revisit SLO nếu cần. |

### 7.1 SLO revision triggers

- Consumer behavior đổi (MarketPulse chuyển từ EOD sang intraday)
- Infra đổi (thêm Postgres replica, HA)
- Data volume tăng > 10× (50 MB → 500 MB/day)

---

## 8. Out of Scope (KHÔNG hứa)

| Item | Lý do |
|------|-------|
| **Realtime latency < 1 min** | Phase hiện tại B3. Ingestion cadence là EOD (17:03). Sẽ revisit ở phase tương lai. |
| **99.9%+ availability cho Postgres/SeaweedFS** | Single-node home lab, solo ops, không có on-call rotation. |
| **Multi-region DR** | R2 đã redundant bên CF; Bronze/Silver/Gold chưa có cross-region backup. RPO = 24h (nightly backup). |
| **Sub-second query latency** | Postgres không phải OLAP warehouse. Nếu cần < 100ms, cân nhắc DuckDB / ClickHouse phase sau. |
| **SLA tài chính / credit** | Nội bộ, không có hợp đồng thương mại. Breach = post-mortem, không refund. |
| **Dev environment (dbt_{user}_dev)** | Best-effort, không SLO. |
| **Historical backfill freshness** | Chạy ngoài giờ, không có SLO cho wall-clock hoàn thành. |
| **Custom consumer schema** | Consumer phải dùng Gold contract hiện có; không cam kết custom view per consumer. |

---

## Appendix A — SLO Dashboard Queries

Query mẫu để compute SLO (sẽ implement trong Prefect reporting flow phase B4):

```sql
-- Gold freshness last 30 days
SELECT
  DATE(loaded_at) AS d,
  EXTRACT(EPOCH FROM (loaded_at - (DATE(loaded_at) + TIME '15:00'))) / 60 AS lag_min,
  (EXTRACT(EPOCH FROM (loaded_at - (DATE(loaded_at) + TIME '15:00'))) / 60) < 60 AS meets_slo
FROM prod.gold_daily_ohlc_load_log
WHERE loaded_at > NOW() - INTERVAL '30 days'
ORDER BY d DESC;
```

## Appendix B — References

- ADR 2026-04-13: Platform Decisions (stack Prefect + Polars + dbt)
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [The Art of SLOs — Google](https://sre.google/resources/practices-and-processes/art-of-slos/)
- `docs/slo-budget-log.md` (TBD, phase B4)
