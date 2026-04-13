# Cost Model & Projection — DataGaze Data Lakehouse

| Field         | Value                          |
|---------------|--------------------------------|
| Owner         | trongnq (Platform / Data Eng)  |
| Last Updated  | 2026-04-13                     |
| Version       | 0.1.0                          |
| Status        | Draft                          |
| Review cadence| Monthly (ngày 01 hàng tháng)   |
| Scope         | data-lakehouse + data-pipeline (Bronze→Silver→Gold), không bao gồm MarketPulse SaaS phase B6-B7 |

> Tỷ giá tham chiếu (2026-04-13): **1 USD ≈ 25,400 VND**. Số liệu USD được quy đổi để so sánh, chi phí thực tế hầu hết thanh toán VND (trừ R2, API).

---

## 1. Cost Summary Dashboard

| Hạng mục                        | USD/tháng | VND/tháng    | % tổng | Ghi chú                          |
|---------------------------------|-----------|--------------|--------|----------------------------------|
| Bizfly VPS (ingestion)          | ~23.62    | ~600,000     | 50.6%  | estimate, verify invoice         |
| Home Lab điện (LXC 201+202)     | ~7.87     | ~200,000     | 16.9%  | 65W avg × 30d × 3,000đ/kWh       |
| Cloudflare R2 storage + ops     | ~0.05     | ~1,270       | 0.1%   | <2GB stored, egress free         |
| Gemini API (ad-hoc, pre-SaaS)   | ~3.00     | ~76,200      | 6.4%   | estimate, verify                 |
| Claude Code Pro (shared)        | ~20.00    | ~508,000     | 21.4%  | attributed 100% (subjective)     |
| Domain / DNS / Tailscale        | 0         | 0            | 0%     | free tier                        |
| GitHub                          | 0         | 0            | 0%     | free tier, private repo          |
| Telegram Bot                    | 0         | 0            | 0%     | free                             |
| **TỔNG**                        | **~54.54**| **~1,385,470**| 100%  | ±15% variance                    |

> **Disclaimer**: Mac mini (host MarketPulse) share với personal use → chưa allocate cost. Khi MarketPulse deploy SaaS sẽ re-allocate (xem §8).

---

## 2. Infrastructure Cost Breakdown

### 2.1 Bizfly VPS — Ingestion producer
- **Host**: `trongnq@14.225.0.201:2222`
- **Spec**: 4 vCPU / 8GB RAM / 60GB SSD
- **Workload**: `ssi-connection` crontab — SSI SignalR ingestion, WAL writer, R2 uploader (17:03), telegram monitor, status reporter, WAL cleanup (giữ 3 ngày)
- **Cost**: ~600,000 VND/tháng (~$23.62) — **estimate, verify invoice gần nhất**
- **Tại sao giữ**: SSI SignalR cần static IP VN; không chạy được trên home lab (NAT, dynamic IP)
- **Risk**: nếu Bizfly tăng giá → xem xét Vultr VN / FPT Cloud

### 2.2 Cloudflare R2 — Source of Truth (per ADR D3)
Pricing công khai Cloudflare (2026 standard tier):

| Metric        | Rate              | Volume tháng (est.) | Cost USD |
|---------------|-------------------|---------------------|----------|
| Storage       | $0.015/GB/month   | 2 GB cumulative     | $0.030   |
| Class A (PUT) | $4.50 / 1M req    | ~10,000 req         | $0.045   |
| Class B (GET) | $0.36 / 1M req    | ~50,000 req         | $0.018   |
| Egress        | **FREE**          | ~5 GB/tháng         | $0.000   |
| **Subtotal**  |                   |                     | **~$0.05** (~1,270 VND) |

**Volume notes**:
- PUT: bizfly upload 5 jobs/ngày × ~50 file Parquet/job × 22 trading days ≈ 5,500 + overhead → round 10k
- GET: lakehouse-gold pull mỗi 17:30 + dbt refresh + ad-hoc debug
- Egress free là lợi thế cốt lõi so với S3 (~$0.09/GB) — tiết kiệm ~$0.45/tháng ở scale hiện tại, scale tuyến tính khi data grow

### 2.3 Home Lab — Proxmox LXC (consumer layer)

| LXC    | Role             | vCPU | RAM  | Disk   | Ước TDP share |
|--------|------------------|------|------|--------|---------------|
| 201    | prefect-server   | 0.5  | 1GB  | 20GB   | ~5W           |
| 202    | lakehouse-gold   | 8    | 8GB  | 200GB  | ~40W          |
| other  | Proxmox overhead | —    | —    | —      | ~20W          |
| **Total** |               |      |      |        | **~65W avg**  |

**Điện**:
- 65W × 24h × 30d = 46.8 kWh/tháng
- 46.8 × 3,000 VND/kWh (giá bậc 4 dân dụng) ≈ **140,000 VND**
- Thêm cooling overhead mùa hè (+30%) → ước **~150,000-200,000 VND/tháng** → lấy **200,000 VND** làm conservative

**Hardware amortization**: chưa allocate (Proxmox host đã có sẵn, share với homelab khác). Khi nào cần dedicated → tính separately.

### 2.4 Domain, DNS, VPN
- **Cloudflare DNS**: free tier (unlimited records)
- **Tailscale**: free tier (< 100 devices, hiện <5 node: bizfly, mac-mini, proxmox, LXC 201, 202)
- **Domain**: chưa register domain riêng cho platform → $0

### 2.5 Mac mini (MarketPulse host)
- Chạy 24/7 share với personal use
- **Chưa allocate cost** ở current phase (B5 Building, local-only)
- Khi deploy SaaS → allocate theo % CPU-hours workload DataGaze

---

## 3. Software & SaaS

| Service               | Tier           | USD/tháng | VND/tháng | Ghi chú                              |
|-----------------------|----------------|-----------|-----------|--------------------------------------|
| Gemini API            | pay-as-you-go  | ~3.00     | ~76,200   | **estimate** — MarketPulse report daily ×22 trading days × ~5k tokens input + 2k output. Verify Google Cloud invoice |
| Claude Code           | Pro/Max        | 20.00     | 508,000   | Shared across all DataGaze work; attribute 100% ở đây (conservative). Max plan thì dùng chung không tăng cost |
| GitHub                | Free           | 0         | 0         | Private repo OK, Actions chưa dùng (ADR D7) |
| Telegram Bot          | Free           | 0         | 0         | Alert channel                        |
| Postgres (self-host)  | —              | 0         | 0         | Chạy trên LXC 202, đã tính điện      |

---

## 4. Data Volume Growth Projection

### 4.1 Current baseline (2026-04)
- **Parquet sinh/ngày**: ~50MB (5 channels × 3 exchanges × ~3MB avg ZSTD compressed)
- **Monthly**: 50MB × 22 trading days ≈ **1.1GB/tháng** net growth (Bronze)
- **Silver + Gold**: ~30% expansion (indexed, denormalized) → **~1.5GB/tháng total**
- **Cumulative R2 current**: ~2GB (mới 2 tháng history)

### 4.2 Year 1 projection (linear, single domain = stock)

| Tháng | Cumulative R2 (GB) | R2 storage cost USD | Postgres (GB) | Ghi chú                    |
|-------|--------------------|--------------------:|---------------|----------------------------|
| M+3   | 6.5                | $0.10               | 2             | baseline hold              |
| M+6   | 11.0               | $0.17               | 3.5           |                            |
| M+9   | 15.5               | $0.23               | 5             |                            |
| M+12  | 20.0               | $0.30               | 6.5           | vẫn trong free headroom    |

### 4.3 Khi nào cần upgrade

| Trigger                        | Action                                           | Cost delta                |
|--------------------------------|--------------------------------------------------|---------------------------|
| R2 > 50GB                      | Xem xét Infrequent Access tier ($0.01/GB)       | Save ~$0.25/GB/mo         |
| Postgres disk > 150GB (LXC)    | Expand LXC 202 disk trên Proxmox (free nếu còn pool) | $0 (hardware có sẵn)      |
| LXC 202 RAM > 7GB avg          | Bump 8→16GB (Proxmox)                           | $0 ops, +10W điện (~30k VND) |
| Thêm domain (BĐS)              | +1.5GB/tháng, R2 cost +$0.02/tháng              | negligible                |
| Bronze > 100GB                 | R2 lifecycle rule archive (xem §7)              | Save ~40%                 |

---

## 5. Cost per Unit Metrics

### 5.1 Cost per GB stored (lakehouse total)
- Total monthly: $54.54 / 2GB cumulative = **$27.27/GB** (current, front-loaded bởi fixed cost)
- Tại 20GB (M+12): $54.54 / 20 = **$2.73/GB** — giảm 10× khi amortize
- **Insight**: fixed-cost dominant, marginal storage cost gần $0 → scale data aggressively trong Bronze, không tối ưu sớm

### 5.2 Cost per report delivered (MarketPulse, hiện tại)
- Daily reports: 22 trading days/tháng × 1 report = 22 reports
- Cost allocable = Gemini ($3) + % Mac mini (bỏ qua) + % Claude Code ($5 guess) ≈ **$8/tháng**
- **$0.36/report** (~9,100 VND) — chấp nhận được cho personal use

### 5.3 Cost per query (Gold Postgres)
- Query volume: ~500 queries/tháng (dev + ad-hoc + dashboard) [estimate]
- Gold cost: điện LXC 202 share = ~120,000 VND/tháng × 50% attributed Gold = 60,000 VND
- **~120 VND/query** (~$0.005) — negligible

---

## 6. Cost Optimization Opportunities

| # | Opportunity                              | Current state | Savings est. | Effort | Priority |
|---|------------------------------------------|---------------|--------------|--------|----------|
| 1 | Parquet ZSTD level 3 → 9                 | Verify (ADR im lặng) | -25% storage = -$0.01/mo nhỏ, +GB*year sau sẽ đáng | L | P3 |
| 2 | WAL cleanup giữ 3 ngày (bizfly)          | Đã có cron (CLAUDE.md)| n/a maintained | —  | done |
| 3 | R2 lifecycle: bronze > 90 ngày → IA tier | Chưa setup    | ~$0.25/GB/mo khi scale | M | P2 |
| 4 | Turn off LXC 202 ngoài giờ (22:00-08:00) | Always-on     | -30% điện ≈ -60,000 VND/mo | M | P2 (break dbt dev) |
| 5 | Gemini prompt caching                    | Chưa check    | -50% input token = -$1.50/mo | L | P1 |
| 6 | Dedup bizfly upload (skip unchanged)     | Chưa có       | -20% PUT (~$0.01) | L | P3 |
| 7 | Tailscale → WireGuard self-host          | Tailscale free| $0 savings (đã free) | — | skip |

**Quick win P1**: bật Gemini context caching khi MarketPulse report dùng cùng system prompt daily.

---

## 7. Scenario Analysis

### 7.1 Current (2026-04, single domain stock)
- **~$54.54/tháng (~1,385,000 VND)** — budget status: **under control** (<2M VND/tháng personal R&D ceiling)

### 7.2 10× volume scenario (500MB/day, thêm BĐS + intraday 1s)

| Hạng mục          | Current | 10× scenario | Delta       |
|-------------------|---------|--------------|-------------|
| Bizfly VPS        | $23.62  | $40.00 (bump 8vCPU/16GB) | +$16.38     |
| R2 storage (M+12) | $0.30   | $3.00 (200GB) | +$2.70      |
| R2 ops            | $0.05   | $0.50        | +$0.45      |
| LXC điện          | $7.87   | $12.00 (bump RAM+disk) | +$4.13 |
| Gemini API        | $3.00   | $8.00 (more domains)    | +$5.00      |
| Claude Code       | $20.00  | $20.00       | 0           |
| **Tổng**          | **$54.54** | **$83.54** | **+$29.00 (+53%)** |

**Insight**: 10× data chỉ +53% cost nhờ R2 egress free + fixed cost dominance. Economics rất favorable.

### 7.3 SaaS phase (MarketPulse B6-B7, ~100 users)
Bắt đầu commercial → cần:
- **Dedicated Mac mini hoặc VPS serving**: +$40-80/tháng (Hetzner AX41 / Vultr)
- **Telegram Bot → Bot API enterprise / webhook infra**: $0 (vẫn free) nhưng cần reliable host
- **Gemini → scale 100× calls**: ~$100-300/tháng
- **Postgres connection pooling (PgBouncer)** trên LXC 202: $0 ops
- **Monitoring (Grafana Cloud free → Pro)**: $0 → $49/tháng nếu break limits
- **Ước tổng SaaS phase**: **$200-450/tháng** (~5-11M VND) → cần revenue cover

**Break-even**: nếu charge 100k VND/user/tháng × 100 users = 10M VND → OK ở upper bound.

---

## 8. Cost Review Cadence

- **Frequency**: monthly, ngày 01
- **Owner**: trongnq
- **Checklist**:
  - [ ] Verify Bizfly invoice vs estimate (600k)
  - [ ] Pull Cloudflare R2 usage dashboard — check storage/Class A/Class B
  - [ ] Check Google Cloud billing → Gemini actual
  - [ ] Đo kWh meter home lab (nếu có smart plug)
  - [ ] Update row "current" trong §1 summary
  - [ ] Diff vs previous month, flag >20% delta
  - [ ] Update §4.2 projection nếu actual lệch >15% baseline
- **Commit convention**: `docs(cost): monthly review YYYY-MM [M5.1]`
- **Escalation**: nếu tổng > 2M VND/tháng → re-evaluate scope hoặc đàm phán optimization (§6)

---

## Items Cần User Verify

1. **Bizfly VPS invoice thực tế** (ước 600k, có thể 500k-800k tùy plan)
2. **Gemini API actual spend** (Google Cloud billing dashboard)
3. **Claude Code subscription tier** (Pro $20 hay Max $100-200?) — allocation % cho DataGaze
4. **Home lab điện giá bậc** (dân dụng bậc 4-5? lấy 3,000đ/kWh trung bình)
5. **Parquet compression codec** — ZSTD đã bật chưa, level nào (ảnh hưởng §6 item #1)
6. **R2 Class A/B actual volume** — dashboard Cloudflare cần verify estimate 10k/50k
