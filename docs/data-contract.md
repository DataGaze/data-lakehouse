# Data Contract — DataGaze Lakehouse

| Field | Giá trị |
|---|---|
| **Owner** | DataGaze Platform Team (`@hoangnguyen`) |
| **Last Updated** | 2026-04-13 |
| **Version** | 1.0.0 |
| **Status** | Draft |
| **Scope** | Bronze / Silver / Gold cho domain `stock` (VN equity market) |
| **Upstream SoT** | `ssi-connection` Parquet trên Cloudflare R2 (`vn-stock-lake`) |
| **Downstream consumers** | MarketPulse (dashboard), Signal/Bot services, ad-hoc analytics (DuckDB) |

---

## 1. Overview — Data Contract là gì

Trong DataGaze, **data contract** là cam kết đọc–ghi giữa **producer** và **consumer** về:

1. **Schema** — tên cột, kiểu dữ liệu, nullable, encoding.
2. **Semantic** — ý nghĩa từng trường (đơn vị, timezone, precision).
3. **Quality** — các ràng buộc bắt buộc (not-null, unique, referential).
4. **Delivery** — path, format, cadence, idempotency.
5. **Versioning & Change Management** — ai được thay đổi, thông báo trước bao lâu, rollback ra sao.

Contract này là **single source of truth** cho 3 producer ↔ consumer pair:

```
ssi-connection (producer)
        │  Parquet on R2 (vn-stock-lake)
        ▼
data-pipeline ingestion (consumer R2 / producer Bronze)
        │  Parquet on SeaweedFS (lakehouse/bronze/stock/...)
        ▼
data-pipeline transform (consumer Bronze / producer Silver)
        │  Parquet on SeaweedFS (lakehouse/silver/stock/...)
        ▼
data-pipeline dbt (consumer Silver / producer Gold)
        │  Postgres datagaze.{prod,dbt_*_dev}
        ▼
MarketPulse + Signal services (consumer Gold)
```

Mọi thay đổi vi phạm contract (đổi tên cột, đổi kiểu, siết nullable) được coi là **breaking** và phải đi qua quy trình ở §9.

---

## 2. Layer Specifications

### 2.1 Bronze Layer — Raw Parquet trên SeaweedFS

**Mục tiêu:** giữ nguyên 1:1 schema do `ssi-connection` phát hành. Không transform, không rename, không cast.

**Storage:** SeaweedFS S3 (`S3_ENDPOINT=http://192.168.0.102:30333`), bucket `lakehouse`.

**Path convention:**

```
lakehouse/bronze/stock/{YYYY-MM-DD}/{channel}/{exchange}.parquet
lakehouse/bronze/stock/{YYYY-MM-DD}/metadata/daily_summary.parquet
lakehouse/bronze/stock/{YYYY-MM-DD}/backfill/{exchange}_1min.parquet
```

- `{channel}` ∈ `ticks | orderbook | index | misc`
- `{exchange}` ∈ `HOSE | HNX | UPCOM`
- Compression: `ZSTD` level 3 (kế thừa từ ssi-connection).
- Row group: 128MB. Dictionary encoding bật cho các string cardinality thấp.

**Event types (đúng với kênh SSI SignalR, không invent thêm):**

| Channel SSI | File type | Mô tả |
|---|---|---|
| `X` | `ticks` | Trade executions (khớp lệnh) |
| `R` | `orderbook` | Bid/ask snapshot L2 (3 mức HOSE, 10 mức HNX/UPCOM/Derivatives) |
| `MI` | `index` | Market index (VNINDEX, VN30, HNX-Index, …) |
| `F`, `FR`, `OL` | `misc` | Foreign room (F/FR) + Odd lot (OL) payload JSON |
| REST daily | `metadata/daily_summary` | End-of-day OHLCV + foreign flow (ground truth) |
| REST 1-min | `backfill/{exchange}_1min` | OHLC 1 phút, chỉ tạo khi reconciliation phát hiện gap |

> Ghi chú: SSI legacy SignalR 1.5 **không có** stream "foreign flow" tick-level riêng; dữ liệu foreign nằm trong `daily_summary` (EOD) và kênh `F`/`FR` (payload JSON). Không document event type không tồn tại.

---

#### 2.1.1 Bronze — `ticks` (channel X)

Path: `bronze/stock/{date}/ticks/{exchange}.parquet`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `server_ts` | `timestamp[ms, UTC]` | No | Thời điểm server SSI-connection nhận event |
| `exchange_time` | `string` | No | Thời gian từ SSI, format `HH:MM:SS` (Asia/Ho_Chi_Minh, chưa parse) |
| `trading_date` | `date` | No | Ngày giao dịch (YYYY-MM-DD) |
| `symbol` | `string` (dict) | No | Mã cổ phiếu, viết hoa (ví dụ `FPT`, `VIC`) |
| `exchange` | `string` (dict) | No | `HOSE` \| `HNX` \| `UPCOM` |
| `last_price` | `int32` | Yes | Giá khớp gần nhất, đơn vị **VND** (không decimal) |
| `last_vol` | `int32` | Yes | Khối lượng khớp của lệnh này |
| `total_vol` | `int64` | Yes | Running total volume trong ngày |
| `total_val` | `int64` | Yes | Running total value trong ngày (VND) |
| `change` | `int32` | Yes | Chênh giá so với tham chiếu (VND) |
| `ratio_change` | `float32` | Yes | % thay đổi — **đơn vị phần trăm** (ví dụ `-1.90`) |
| `session` | `string` (dict) | Yes | `ATO` \| `LO` \| `ATC` \| `PT` |
| `notify_id` | `int32` | No | SSI sequence ID, reset 0 lúc 00:00 VN daily |
| `source` | `string` (dict) | No | `streaming` \| `backfill_1min` |

#### 2.1.2 Bronze — `orderbook` (channel R)

Path: `bronze/stock/{date}/orderbook/{exchange}.parquet`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `server_ts` | `timestamp[ms, UTC]` | No | |
| `exchange_time` | `string` | No | `HH:MM:SS` |
| `trading_date` | `date` | No | |
| `symbol` | `string` (dict) | No | |
| `exchange` | `string` (dict) | No | |
| `ceiling` | `int32` | Yes | Giá trần (VND) |
| `floor` | `int32` | Yes | Giá sàn (VND) |
| `ref_price` | `int32` | Yes | Giá tham chiếu (VND) |
| `bid_p1` … `bid_p3` | `int32` | Yes | Bid price level 1–3 (VND) |
| `bid_v1` … `bid_v3` | `int32` | Yes | Bid volume level 1–3 |
| `ask_p1` … `ask_p3` | `int32` | Yes | Ask price level 1–3 (VND) |
| `ask_v1` … `ask_v3` | `int32` | Yes | Ask volume level 1–3 |
| `notify_id` | `int32` | No | |

> HNX/UPCOM/Derivatives có thể mở rộng `bid_p4..bid_p10` / `ask_p4..ask_p10`. Với HOSE các cột L4–L10 sẽ là `NULL`. Khi mở rộng schema → **minor version bump** (§6).

#### 2.1.3 Bronze — `index` (channel MI)

Path: `bronze/stock/{date}/index/{exchange}.parquet`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `server_ts` | `timestamp[ms, UTC]` | No | |
| `exchange_time` | `string` | No | |
| `trading_date` | `date` | No | |
| `index_id` | `string` (dict) | No | `VNINDEX` \| `VN30` \| `HNXINDEX` \| `HNX30` … |
| `index_value` | `float64` | Yes | Giá trị index hiện tại (điểm) |
| `prior_index_value` | `float64` | Yes | Đóng cửa phiên trước |
| `change` | `float64` | Yes | Thay đổi điểm |
| `ratio_change` | `float64` | Yes | % thay đổi (đơn vị phần trăm) |
| `total_qtty` | `int64` | Yes | Tổng khối lượng khớp |
| `total_value` | `int64` | Yes | Tổng giá trị khớp (VND) |
| `advances` | `int16` | Yes | Số mã tăng |
| `declines` | `int16` | Yes | Số mã giảm |
| `no_changes` | `int16` | Yes | Số mã tham chiếu |
| `exchange` | `string` (dict) | No | |
| `notify_id` | `int32` | No | |

#### 2.1.4 Bronze — `misc` (channels F, FR, OL)

Path: `bronze/stock/{date}/misc/{exchange}.parquet`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `server_ts` | `timestamp[ms, UTC]` | No | |
| `exchange_time` | `string` | No | |
| `trading_date` | `date` | No | |
| `channel` | `string` (dict) | No | `F` \| `FR` \| `OL` |
| `symbol` | `string` (dict) | Yes | Có thể null với kênh index-wide |
| `exchange` | `string` (dict) | No | |
| `payload` | `string (JSON)` | No | Nội dung event nguyên gốc dạng JSON string |
| `notify_id` | `int32` | No | |

#### 2.1.5 Bronze — `metadata/daily_summary` (REST ground-truth)

Path: `bronze/stock/{date}/metadata/daily_summary.parquet`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `trading_date` | `date` | No | |
| `symbol` | `string` (dict) | No | |
| `exchange` | `string` (dict) | No | |
| `open_price` | `int32` | Yes | VND |
| `high_price` | `int32` | Yes | VND |
| `low_price` | `int32` | Yes | VND |
| `close_price` | `int32` | Yes | VND |
| `total_match_vol` | `int64` | Yes | Khối lượng khớp (reconciliation target) |
| `total_match_val` | `int64` | Yes | Giá trị khớp (VND) |
| `total_deal_vol` | `int64` | Yes | Khối lượng thỏa thuận |
| `total_deal_val` | `int64` | Yes | Giá trị thỏa thuận (VND) |
| `foreign_buy_vol` | `int64` | Yes | KL nước ngoài mua |
| `foreign_sell_vol` | `int64` | Yes | KL nước ngoài bán |
| `foreign_room` | `int64` | Yes | Room còn lại cho NĐTNN |

#### 2.1.6 Bronze — `backfill/{exchange}_1min`

Path: `bronze/stock/{date}/backfill/{exchange}_1min.parquet` (chỉ tồn tại khi reconciliation fail)

| Column | Type | Nullable | Description |
|---|---|---|---|
| `trading_date` | `date` | No | |
| `exchange_time` | `string` | No | `HH:MM` (1-min candle) |
| `symbol` | `string` (dict) | No | |
| `exchange` | `string` (dict) | No | |
| `open` | `int32` | Yes | VND |
| `high` | `int32` | Yes | VND |
| `low` | `int32` | Yes | VND |
| `close` | `int32` | Yes | VND |
| `volume` | `int64` | Yes | |
| `source` | `string` | No | Luôn là `rest_api_intraday_1min` |
| `backfill_reason` | `string` | No | Ví dụ `reconciliation_mismatch_2.3pct` |

---

### 2.2 Silver Layer — Cleaned Parquet

**Mục tiêu:** schema đã enforce, dedup, validated, loại outlier hiển nhiên. Consumer downstream (dbt) có thể trust trực tiếp.

**Storage:** SeaweedFS S3, bucket `lakehouse`, prefix `silver/stock/...` (tương đồng Bronze).

**Transformations áp dụng (Polars):**

1. Cast timezone `server_ts` → `timestamp[us, UTC]` (chuẩn hóa precision).
2. Parse `exchange_time` (HH:MM:SS) + `trading_date` → cột mới `event_ts_vn` (`timestamp[us, Asia/Ho_Chi_Minh]`).
3. Uppercase `symbol`, `exchange`, `index_id`.
4. Enforce enum cho `session` ∈ {ATO, LO, ATC, PT}; giá trị lạ → reject row, count vào `dq_reject_count`.
5. Drop row có `symbol IS NULL` hoặc `last_price < 0`.
6. **Dedup key** (xem bảng dưới).

**Dedup keys (unique constraint trong Silver):**

| Silver table | Dedup key |
|---|---|
| `silver.ticks` | `(exchange, symbol, notify_id)` |
| `silver.orderbook` | `(exchange, symbol, server_ts, notify_id)` |
| `silver.index` | `(exchange, index_id, notify_id)` |
| `silver.daily_summary` | `(trading_date, exchange, symbol)` |
| `silver.backfill_1min` | `(trading_date, exchange, symbol, exchange_time)` |

**Silver `ticks` schema (đại diện — các bảng khác tương tự với bổ sung cột chuẩn hóa):**

| Column | Type | Nullable | Description |
|---|---|---|---|
| `server_ts` | `timestamp[us, UTC]` | No | Chuẩn hóa từ Bronze ms → us |
| `event_ts_vn` | `timestamp[us, Asia/Ho_Chi_Minh]` | No | Parse từ `trading_date` + `exchange_time` |
| `trading_date` | `date` | No | |
| `symbol` | `string` | No | Uppercase, validated against `_meta/securities_list.json` |
| `exchange` | `string` | No | Enum `HOSE|HNX|UPCOM` |
| `last_price_vnd` | `int32` | No | Rename `last_price` → `last_price_vnd`, NOT NULL |
| `last_vol` | `int32` | No | |
| `total_vol` | `int64` | Yes | |
| `total_val_vnd` | `int64` | Yes | |
| `change_vnd` | `int32` | Yes | |
| `ratio_change_pct` | `decimal(7,2)` | Yes | Chuẩn hóa float32 → decimal để ổn định downstream |
| `session` | `string` | No | Enum ATO/LO/ATC/PT |
| `notify_id` | `int32` | No | |
| `source` | `string` | No | streaming/backfill_1min |
| `ingested_at` | `timestamp[us, UTC]` | No | Thời điểm Silver job ghi row |

**Validation rules (hard fail):**

- `last_price_vnd` ∈ `[floor, ceiling]` (cross-check với cùng `(symbol, trading_date)` từ orderbook hoặc securities list).
- `server_ts` thuộc giờ giao dịch VN (`09:00`–`15:00` UTC+7, Mon–Fri, exclude holidays từ `_meta/holidays.json`).
- Row count delta so với Bronze `< 5%` (trừ trường hợp có dedup — log explicit).

---

### 2.3 Gold Layer — PostgreSQL

**Database:** `datagaze` (đổi từ `stock_market`, theo ADR §D6).
**Schema:** `prod` (production), `dbt_{user}_dev` (developer local).
**Host:** LXC 202 `lakehouse-gold`.

**Charset:** `UTF8`. **Timezone:** server `UTC`; column timestamp luôn là `TIMESTAMPTZ`.

#### 2.3.1 Gold — `ticks`

Bảng tick-level (partition theo ngày, retention 90 ngày online; archive về Parquet `silver/ticks/`).

| Column | Type | Nullable | Constraint | Description |
|---|---|---|---|---|
| `trading_date` | `DATE` | No | PK | Partition key |
| `exchange` | `VARCHAR(10)` | No | PK, CHECK IN ('HOSE','HNX','UPCOM') | |
| `symbol` | `VARCHAR(20)` | No | PK | |
| `notify_id` | `INTEGER` | No | PK | SSI sequence |
| `server_ts` | `TIMESTAMPTZ` | No | | UTC |
| `event_ts_vn` | `TIMESTAMPTZ` | No | | Asia/Ho_Chi_Minh |
| `last_price_vnd` | `INTEGER` | No | CHECK >= 0 | |
| `last_vol` | `INTEGER` | No | CHECK >= 0 | |
| `total_vol` | `BIGINT` | Yes | | |
| `total_val_vnd` | `BIGINT` | Yes | | |
| `change_vnd` | `INTEGER` | Yes | | |
| `ratio_change_pct` | `NUMERIC(7,2)` | Yes | | % |
| `session` | `VARCHAR(4)` | No | CHECK IN ('ATO','LO','ATC','PT') | |
| `source` | `VARCHAR(16)` | No | | |
| `created_at` | `TIMESTAMPTZ` | No | DEFAULT `NOW()` | |

- **PK:** `(trading_date, exchange, symbol, notify_id)`
- **Partitioning:** `PARTITION BY RANGE (trading_date)` — 1 partition / tháng.
- **Indexes:**
  - `idx_ticks_symbol_date` (`symbol`, `trading_date` DESC)
  - `idx_ticks_server_ts` BRIN on `server_ts`

#### 2.3.2 Gold — `daily_ohlcv`

Ground truth EOD (nguồn: `bronze metadata/daily_summary.parquet`).

| Column | Type | Nullable | Constraint | Description |
|---|---|---|---|---|
| `trading_date` | `DATE` | No | PK | |
| `symbol` | `VARCHAR(20)` | No | PK | |
| `exchange` | `VARCHAR(10)` | No | PK, CHECK IN ('HOSE','HNX','UPCOM') | |
| `open_price` | `INTEGER` | Yes | CHECK >= 0 | VND |
| `high_price` | `INTEGER` | Yes | CHECK >= 0 | VND |
| `low_price` | `INTEGER` | Yes | CHECK >= 0 | VND |
| `close_price` | `INTEGER` | Yes | CHECK >= 0 | VND |
| `total_match_vol` | `BIGINT` | Yes | | |
| `total_match_val` | `BIGINT` | Yes | | |
| `total_deal_vol` | `BIGINT` | Yes | | |
| `total_deal_val` | `BIGINT` | Yes | | |
| `foreign_buy_vol` | `BIGINT` | Yes | | |
| `foreign_sell_vol` | `BIGINT` | Yes | | |
| `foreign_room` | `BIGINT` | Yes | | |
| `created_at` | `TIMESTAMPTZ` | No | DEFAULT `NOW()` | |

- **PK:** `(trading_date, symbol, exchange)`
- **Indexes:** `idx_ohlcv_symbol(symbol)`, `idx_ohlcv_date(trading_date)`, `idx_ohlcv_exchange(exchange)`

#### 2.3.3 Gold — `metadata` (pipeline run tracking)

| Column | Type | Nullable | Constraint | Description |
|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | PK | |
| `run_date` | `DATE` | No | | Trading date đang xử lý |
| `flow_name` | `VARCHAR(100)` | No | | Ví dụ `ingest_r2_to_bronze` |
| `layer` | `VARCHAR(16)` | No | CHECK IN ('bronze','silver','gold') | |
| `status` | `VARCHAR(20)` | No | CHECK IN ('started','success','failed','partial') | |
| `rows_in` | `BIGINT` | Yes | | |
| `rows_out` | `BIGINT` | Yes | | |
| `rows_rejected` | `BIGINT` | Yes | | |
| `duration_seconds` | `REAL` | Yes | | |
| `error_message` | `TEXT` | Yes | | |
| `git_sha` | `VARCHAR(40)` | Yes | | Commit của `data-pipeline` khi chạy |
| `created_at` | `TIMESTAMPTZ` | No | DEFAULT `NOW()` | |

- **Index:** `idx_metadata_run(run_date, flow_name)`

#### 2.3.4 Gold — `signals`

Signals AI/quant sinh ra từ Gold data.

| Column | Type | Nullable | Constraint | Description |
|---|---|---|---|---|
| `signal_id` | `BIGSERIAL` | No | PK | |
| `trading_date` | `DATE` | No | | |
| `symbol` | `VARCHAR(20)` | Yes | FK → `daily_ohlcv(symbol, trading_date)` logical | Null cho market-wide signal |
| `signal_type` | `VARCHAR(50)` | No | | Ví dụ `momentum_breakout`, `foreign_accumulation` |
| `signal_version` | `VARCHAR(20)` | No | | Ví dụ `v1.2.0` của model |
| `confidence` | `NUMERIC(5,4)` | Yes | CHECK 0 ≤ confidence ≤ 1 | |
| `reason` | `TEXT` | Yes | | |
| `metadata` | `JSONB` | Yes | | Feature values, thresholds |
| `created_at` | `TIMESTAMPTZ` | No | DEFAULT `NOW()` | |

- **Indexes:** `idx_signals_date(trading_date)`, `idx_signals_symbol_date(symbol, trading_date)`, `idx_signals_type(signal_type)`

> Logical FK (không enforce bằng DB constraint vì signals có thể tham chiếu symbol chưa có trong `daily_ohlcv` hôm đó); dbt test `relationships` enforce tại transform time.

---

## 3. Data Types Standardization

| Domain | Kiểu chuẩn | Lý do |
|---|---|---|
| **Giá cổ phiếu (VND)** | `int32` (Bronze/Silver), `INTEGER` (Postgres) | VN equity không có xu lẻ — tất cả price đã là VND nguyên. Dùng decimal là over-engineering |
| **Giá trị giao dịch (VND)** | `int64` / `BIGINT` | Daily value có thể vượt 10^12 |
| **% thay đổi** | `decimal(7,2)` Silver, `NUMERIC(7,2)` Gold | Ổn định hơn float; đủ chứa `-99.99` tới `99999.99` |
| **Index point** | `float64` / `DOUBLE PRECISION` | VNINDEX có decimal |
| **Confidence / probability** | `NUMERIC(5,4)` | Range [0,1], 4 chữ số sau dấu phẩy |
| **Timestamp event** | Bronze `timestamp[ms, UTC]`; Silver/Gold `timestamp[us, UTC]` = `TIMESTAMPTZ` | ms đủ cho SSI; Silver nâng lên us để thống nhất với dbt default |
| **Timestamp local VN** | `TIMESTAMPTZ` lưu UTC, hiển thị `Asia/Ho_Chi_Minh` khi query | PG luôn lưu UTC nội bộ; set session `TIMEZONE` khi hiển thị |
| **Date** | `date` / `DATE` | Không có timezone component |
| **String / symbol** | UTF-8, uppercase, `VARCHAR(20)` cho symbol, `VARCHAR(10)` cho exchange | Match SSI convention |
| **Enum** | String + CHECK constraint, **không** dùng native PG enum | Dễ thêm giá trị mới không cần `ALTER TYPE` |

**Timezone policy:**

- Storage: **luôn UTC**.
- Display/query: convert sang `Asia/Ho_Chi_Minh` ở presentation layer.
- `exchange_time` từ SSI là local VN time dạng `HH:MM:SS` — Silver tạo cột `event_ts_vn` có timezone để remove ambiguity.

---

## 4. Naming Conventions

| Đối tượng | Quy tắc | Ví dụ |
|---|---|---|
| Table, column, schema | `snake_case`, tiếng Anh | `daily_ohlcv`, `ratio_change_pct` |
| ID columns | suffix `_id` | `signal_id`, `index_id` |
| Timestamp columns | suffix `_ts` (UTC) hoặc `_ts_vn` (local) | `server_ts`, `event_ts_vn`, `ingested_at` |
| Percentage columns | suffix `_pct` | `ratio_change_pct` |
| Currency columns | suffix `_vnd` khi không rõ từ context | `last_price_vnd`, `total_val_vnd` |
| Boolean flags | prefix `is_` hoặc `has_` | `is_backfilled`, `has_atc` |
| Bronze = 1:1 với upstream | giữ nguyên tên gốc của SSI | `last_price` (không rename ở Bronze) |
| Silver = đổi tên chuẩn hóa | thêm suffix đơn vị | `last_price_vnd` |
| Gold | theo Silver | |
| dbt model file | `{layer}_{entity}.sql` | `silver_ticks.sql`, `gold_daily_ohlcv.sql` |
| Pipeline step | `{action}_{source}_to_{target}` | `ingest_r2_to_bronze`, `transform_bronze_to_silver` |

**Không dùng:** reserved words Postgres (`user`, `order`, `table`), viết tắt không chuẩn (`qty` OK, `qtty` legacy giữ lại — sẽ deprecate ở v2).

---

## 5. Contract Versioning

Contract version theo **SemVer** — `MAJOR.MINOR.PATCH`.

| Loại thay đổi | Bump | Ví dụ | Breaking? |
|---|---|---|---|
| **PATCH** | `.x.x.+1` | Sửa typo description, clarify nullable, thêm index | No |
| **MINOR** | `.x.+1.0` | Thêm cột mới nullable, thêm enum value mới, thêm bảng mới | No |
| **MAJOR** | `+1.0.0` | Đổi tên cột, đổi kiểu cột, siết nullable, đổi dedup key, xóa cột, đổi PK, đổi unit | **Yes** |

**Breaking change policy:**

1. Ít nhất **14 ngày** dual-publish (ghi cả cột cũ lẫn cột mới) trước khi xóa.
2. Consumer được thông báo qua PR description + `CHANGELOG.md` của `data-pipeline`.
3. Mỗi MAJOR phải có migration script + rollback script.
4. Không bao giờ backfill MAJOR change sang dữ liệu lịch sử — tạo version folder riêng (`bronze/stock_v2/…`).

**Versioning metadata trong data:**

- Bronze: version folder path khi có breaking (`bronze/stock/` = v1; `bronze/stock_v2/` = v2).
- Silver/Gold: cột `contract_version` (string, ví dụ `"1.0.0"`) thêm vào bảng `pipeline_metadata`, không thêm vào bảng data để tránh bloat.
- `signals.signal_version` tracking độc lập cho model logic (không phải contract).

---

## 6. Data Quality Rules (dbt tests)

Mỗi Silver/Gold table khai báo test trong `schema.yml` (dbt):

### 6.1 Not-null tests

| Table | Columns (NOT NULL) |
|---|---|
| `silver.ticks` | `server_ts, trading_date, symbol, exchange, last_price_vnd, session, notify_id` |
| `silver.orderbook` | `server_ts, trading_date, symbol, exchange, notify_id` |
| `silver.index` | `server_ts, trading_date, index_id, exchange, notify_id` |
| `silver.daily_summary` | `trading_date, symbol, exchange` |
| `gold.daily_ohlcv` | `trading_date, symbol, exchange` |
| `gold.ticks` | `trading_date, exchange, symbol, notify_id, server_ts, last_price_vnd, session` |

### 6.2 Unique / PK tests

| Table | Unique key |
|---|---|
| `silver.ticks` | `(exchange, symbol, notify_id)` (dbt `unique_combination_of_columns`) |
| `silver.index` | `(exchange, index_id, notify_id)` |
| `silver.daily_summary` | `(trading_date, symbol, exchange)` |
| `gold.daily_ohlcv` | PK constraint |
| `gold.ticks` | PK constraint |

### 6.3 Accepted values (enum)

| Column | Accepted values |
|---|---|
| `exchange` | `['HOSE','HNX','UPCOM']` |
| `session` | `['ATO','LO','ATC','PT']` |
| `source` | `['streaming','backfill_1min']` |
| `pipeline_metadata.layer` | `['bronze','silver','gold']` |
| `pipeline_metadata.status` | `['started','success','failed','partial']` |

### 6.4 Range / sanity tests

- `last_price_vnd` ∈ `[0, 10_000_000]` (VND)
- `ratio_change_pct` ∈ `[-100.0, 10000.0]` (cover edge case penny stock)
- `confidence` ∈ `[0, 1]`
- `trading_date` ≤ `CURRENT_DATE`

### 6.5 Relationship / referential tests

- `gold.signals.symbol` (khi not null) ∈ set symbols trong `_meta/securities_list.json`
- `gold.ticks.(symbol, trading_date)` có tồn tại trong `gold.daily_ohlcv` — soft test (warn, không fail), vì tick có thể có trước EOD job.

### 6.6 Freshness

| Source | SLA |
|---|---|
| Bronze Parquet trên SeaweedFS | ≤ 30 phút sau khi R2 có file (17:30 VN) |
| Gold `daily_ohlcv` | ≤ 18:30 VN daily (T+0) |
| Gold `ticks` | ≤ 19:00 VN daily (T+0) |

dbt `source freshness` check chạy đầu flow; fail → Telegram alert, flow abort.

---

## 7. Producer ↔ Consumer Agreements

### 7.1 `ssi-connection` → Cloudflare R2 → `data-pipeline`

| Aspect | Commitment |
|---|---|
| Producer | `ssi-connection` (VPS Bizfly), cronjob `r2_uploader.py` lúc `17:03 VN` (ADR-011 ssi-connection) |
| Storage | R2 bucket `vn-stock-lake`, endpoint `https://3f28373a8c3cad95bb5dea707d262983.r2.cloudflarestorage.com` |
| Format | Parquet ZSTD-3, schema theo §2.1 |
| Path | `{YYYY}/{MM}/{DD}/{channel}/{exchange}.parquet` |
| Delivery guarantee | At-least-once. MD5 verify sau upload; `uploads/{date}.json` ghi nhận `verified: true` |
| Idempotency | Key theo path; re-upload cùng path phải trả cùng MD5 |
| Consumer | `data-pipeline` flow `ingest_r2_to_bronze` chạy `17:30 VN` (sau uploader 27 phút) |
| Consumer SLA | Pull + validate Parquet format trong ≤ 10 phút; fail → Telegram alert |
| Change notice | Thay đổi schema R2 phải thông báo ≥ 14 ngày, update `ssi-connection/docs/04-DATA-SCHEMA.md` + bump version contract |
| Failure mode | R2 miss file → consumer retry 3 lần cách nhau 5 phút; vẫn fail → escalate producer |

### 7.2 `data-pipeline` (Gold) → MarketPulse + Signal services

| Aspect | Commitment |
|---|---|
| Producer | `data-pipeline`, bước `transform_silver_to_gold` (dbt run + test) |
| Storage | Postgres `datagaze.prod.*` |
| Access | Read-only role `datagaze_reader` cho MarketPulse; write role chỉ dbt user dùng |
| Schema stability | Gold là public API; breaking change follow §5 (14 ngày dual-publish) |
| Freshness SLA | §6.6 |
| Query pattern | Consumer phải dùng PK/index — full scan `gold.ticks` mà không filter `trading_date` sẽ bị alert |
| Change notice | `CHANGELOG.md` + Telegram announcement 14 ngày trước |
| Failure mode | Flow fail → giữ nguyên snapshot ngày hôm trước, không partial write; `pipeline_metadata.status='failed'` |

---

## 8. Change Management

### 8.1 Approver matrix

| Thay đổi | Approver bắt buộc |
|---|---|
| PATCH (typo, docstring, index) | 1 reviewer (team DataGaze) |
| MINOR (thêm cột nullable, bảng mới) | Platform owner + 1 consumer owner (MarketPulse) |
| MAJOR (breaking) | Platform owner + **tất cả** consumer owners + ghi ADR mới |

### 8.2 Process MAJOR breaking change

```
Day 0    Mở RFC (issue trong data-lakehouse) — schema diff + migration plan
Day 3    Review meeting, chốt approve
Day 7    Merge code: producer ghi dual (cột cũ + cột mới), bump contract version
Day 7+14 Grace period — consumer migrate sang cột mới, monitor
Day 21   Xóa cột cũ, tag release contract v{N+1}.0.0
Day 21+ Deprecation notice còn giữ trong CHANGELOG.md vĩnh viễn
```

### 8.3 Deprecation timeline

- **Cột bị deprecate** phải có comment `-- DEPRECATED since v{X.Y.Z}, remove after {DATE}` trong DDL.
- `schema.yml` dbt: thêm `meta.deprecated: true` + `meta.remove_at: YYYY-MM-DD`.
- Sau `remove_at`: cột được drop, MAJOR bump.

### 8.4 Emergency break-glass

Nếu producer buộc phải breaking change đột ngột (ví dụ SSI đổi API):

1. Producer tạm ghi dual (snapshot cột cũ + cột mới) trong ≥ 3 ngày.
2. Platform owner gửi announcement `[URGENT]` kèm root cause.
3. Consumer migrate trong 7 ngày (rút ngắn từ 14).
4. Post-mortem trong 14 ngày, lưu `docs/adr/YYYY-MM-DD-emergency-{reason}.md`.

### 8.5 Non-goals của contract v1.0

- **Không** cover real-time streaming (Bronze mới là batch daily từ R2).
- **Không** cover domain BĐS (sẽ tạo contract riêng khi onboard).
- **Không** enforce PII/PCI (market data công khai).
- Schema registry tự động (Confluent, DataHub) — chưa cần ở scale hiện tại (ADR §D7).

---

## Appendix A — References

- `data-lakehouse/docs/adr/2026-04-13-platform-decisions.md` — kiến trúc platform
- `ssi-connection/docs/04-DATA-SCHEMA.md` — nguồn gốc Bronze schema
- `data-pipeline/config/schemas.py` — Polars schema hiện tại
- `data-pipeline/sql/init.sql` — Gold DDL legacy (sẽ migrate sang Alembic/dbt)
- SSI FC SignalR channels: X (tick), R (orderbook), MI (index), F/FR (foreign), B (ohlcv), OL (odd lot)
