# SeaweedFS — Operations & Configuration

> **Owner:** DataGaze Platform Team
> **Last updated:** 2026-04-14
> **Classification:** Internal — Infrastructure
> **Review cycle:** After every change (mandatory git commit)

## Table of Contents

- [1. Overview](#1-overview)
- [2. Architecture](#2-architecture)
- [3. Service Configuration](#3-service-configuration)
- [4. Storage Tiers](#4-storage-tiers)
- [5. Buckets](#5-buckets)
- [6. Disk Routing Rules](#6-disk-routing-rules)
- [7. Access Control (S3 Identities)](#7-access-control-s3-identities)
- [8. Operational Runbook](#8-operational-runbook)
- [9. Monitoring & Health Checks](#9-monitoring--health-checks)
- [10. Disaster Recovery](#10-disaster-recovery)
- [11. Capacity Planning](#11-capacity-planning)
- [12. SOP: Standard Operating Procedures](#12-sop-standard-operating-procedures)
- [13. Changelog](#13-changelog)

---

## 1. Overview

| Property | Value |
|----------|-------|
| **Purpose** | S3-compatible object storage for DataGaze data lakehouse (Bronze/Silver layers) |
| **Host** | Proxmox `promax` — 100.89.161.125 (Tailscale) / 192.168.0.200 (LAN) |
| **Version** | SeaweedFS 3.71 |
| **Data model** | Bucket-per-domain, path-based disk tiering (HDD for Bronze, SSD for Silver) |
| **Access** | S3 API (:8333), Filer HTTP (:8888), Master API (:9333) |
| **Upstream docs** | https://github.com/seaweedfs/seaweedfs/wiki |

## 2. Architecture

```
                   ┌──────────────────────────────┐
                   │  SeaweedFS Master (:9333)     │
                   │  mdir: /mnt/hdd/.../m9333     │
                   │  Topology, volume assignment   │
                   └──────────┬───────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│  Volume Server HDD       │   │  Volume Server SSD       │
│  Port: 8080              │   │  Port: 8081              │
│  Dir: /mnt/hdd/seaweedfs │   │  Dir: /data/seaweedfs-ssd│
│  Disk tag: hdd           │   │  Disk tag: ssd           │
│  DC: dc1, Rack: hdd      │   │  DC: dc1, Rack: ssd      │
│  Max volumes: 100        │   │  Max volumes: 50         │
│                          │   │                          │
│  Hardware:               │   │  Hardware:               │
│  Seagate ST2000DM008     │   │  HP SSD FX900 Plus M.2   │
│  2TB, 7200rpm            │   │  2TB NVMe                │
│  Seq: ~150 MB/s          │   │  Seq: ~2-3 GB/s          │
│  Random 4K: ~200 IOPS    │   │  Random 4K: ~500K IOPS   │
└──────────────────────────┘   └──────────────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
                   ┌──────────────────────────────┐
                   │  Filer (:8888) + S3 (:8333)   │
                   │  Metadata: LevelDB2           │
                   │  Dir: /mnt/hdd/.../filerldb2  │
                   │  S3 config: /etc/.../config.json│
                   └──────────────────────────────┘
```

**Design decisions:**
- Bronze (raw, write-heavy, large) → HDD: cost-efficient, sequential write sufficient
- Silver (transformed, read for query) → SSD: fast random IO for Polars/analytics
- Gold → PostgreSQL on NVMe (LXC 202), not SeaweedFS
- Disk routing via `fs.configure` path prefix rules — automatic, no client-side logic needed

## 3. Service Configuration

### Systemd Units

| Unit | ExecStart | Dependencies |
|------|-----------|-------------|
| `seaweedfs-master.service` | `weed master -port=9333 -mdir=/mnt/hdd/seaweedfs/m9333 -defaultReplication=000` | `network.target` |
| `seaweedfs-volume-hdd.service` | `weed volume -port=8080 -mserver=localhost:9333 -dir=/mnt/hdd/seaweedfs -max=100 -disk=hdd -dataCenter=dc1 -rack=hdd` | `seaweedfs-master` |
| `seaweedfs-volume-ssd.service` | `weed volume -port=8081 -mserver=localhost:9333 -dir=/data/seaweedfs-ssd -max=50 -disk=ssd -dataCenter=dc1 -rack=ssd` | `seaweedfs-master` |
| `seaweedfs-filer.service` | `weed filer -ip=192.168.0.200 -master=localhost:9333 -port=8888 -s3 -s3.port=8333 -s3.config=/etc/seaweedfs/config.json` | `seaweedfs-master` |

**Boot order:** master → volume-hdd + volume-ssd → filer (systemd `Requires` + `After`)

All units: `Restart=always`, `RestartSec=5`, `LimitNOFILE=65536`

`-ip=192.168.0.200` on the filer is mandatory (added 2026-09-03): without it `weed` picks the first non-loopback
address at start, and after one restart it bound filer and S3 to the Tailscale IP `100.89.161.125` instead of the LAN
IP, so every LAN client got TCP RST on `:8333`. Master and volume servers already advertise `192.168.0.200`.

### Config Files

| File | Purpose |
|------|---------|
| `/etc/seaweedfs/filer.toml` | Filer metadata backend (LevelDB2 at `/mnt/hdd/seaweedfs/filerldb2`) |
| `/etc/seaweedfs/config.json` | S3 identity & access control |

### Firewall (iptables, persisted by `netfilter-persistent` in `/etc/iptables/rules.v4`)

| Port | Allowed sources | Note |
|------|-----------------|------|
| 8333 (S3) | `127.0.0.1`, `192.168.0.200`, `192.168.0.0/24` | LAN subnet added 2026-09-03 for Mac mini rclone (`learning-hub`); S3 API is credentialed |
| 8888 (filer HTTP), 9333 (master) | `127.0.0.1`, `192.168.0.200` | Unauthenticated, keep host-only |
| 8080, 8081 (volume) | `127.0.0.1`, `192.168.0.200` | Host-only |
| Any port via `tailscale0` | Tailscale peers | Accepted by the `ts-input` chain before the rules above |

Change a rule with `iptables -I INPUT <n> ...` then `iptables-save > /etc/iptables/rules.v4`; PVE firewall is disabled.

### Deprecated

| Unit | Status | Note |
|------|--------|------|
| `seaweedfs.service` | Disabled (2026-04-14) | Old all-in-one, replaced by 4 services above |

## 4. Storage Tiers

| Tier | Disk | Volume Server | Use Case | IO Pattern |
|------|------|---------------|----------|------------|
| **HDD** | Seagate ST2000DM008 (2TB, 7200rpm) | `:8080` | Bronze — raw crawled data, batch JSONL/Parquet | Sequential write, sequential read |
| **SSD** | HP SSD FX900 Plus M.2 (2TB NVMe) | `:8081` | Silver — cleaned/transformed data, analytics | Random read, moderate write |

### Volume Allocation

| Volume IDs | Server | Disk | Collection | Note |
|------------|--------|------|------------|------|
| 1-14 | :8080 | HDD | `lakehouse` + general | Legacy, pre-migration |
| 15-21+ | :8081 | SSD | (dynamic) | Created after migration |
| 22+ | :8080 | HDD | (dynamic) | New HDD writes post-migration |

## 5. Buckets

| Bucket | Domain | Owner | Created | Status | Description |
|--------|--------|-------|---------|--------|-------------|
| `lakehouse` | Legacy | — | 2026-03-23 | **Deprecated** | Old unified bucket. ~25KB data. Migrate to `stock-data`, then delete. |
| `stock-data` | Stock market pipeline | stock-data-pipeline | 2026-04-14 | Active | OHLCV, market index, ticks from SSI |
| `crawl-news` | News crawling | crawl pipeline | 2026-04-14 | Active | Vietnamese news (cafef, vnexpress, vietnamnet...) |
| `crawl-gov` | Government & corporate | crawl pipeline | 2026-04-14 | Active | chinhphu.vn, sbv.gov.vn, HOSE/HNX announcements, IR pages |
| `crawl-bds` | Real estate | bds-data | 2026-04-14 | Active | batdongsan, chotot, alonhadat listings |
| `marketpulse` | Analytics & reports | MarketPulse | 2026-04-14 | Active | Aggregated reports, analysis output |
| `learning-hub` | Learning Hub (BIZ03-edtech-vn) | learning-hub | 2026-09-03 | Active | TOEIC source (`toeic-pred/`), R2 media mirror (`media/`), `toeic-listening-pack/`, D1 exports (`backups/`). Own layout, no bronze/silver; whole bucket on HDD |

### Bucket Internal Structure

```
{bucket}/
├── bronze/          → auto HDD (fs.configure)
│   ├── {source}/
│   │   ├── {YYYY-MM-DD}.jsonl      # batch per day
│   │   └── {YYYY-MM-DD}.parquet    # or parquet
│   └── ...
└── silver/          → auto SSD (fs.configure)
    ├── {source}/
    │   └── {YYYY-MM-DD}.parquet    # cleaned, validated
    └── ...
```

## 6. Disk Routing Rules

Configured via `fs.configure`. Rules are persisted in filer metadata — survive restarts.

| # | locationPrefix | diskType | Applied |
|---|----------------|----------|---------|
| 1 | `/buckets/stock-data/bronze` | hdd | 2026-04-14 |
| 2 | `/buckets/stock-data/silver` | ssd | 2026-04-14 |
| 3 | `/buckets/crawl-news/bronze` | hdd | 2026-04-14 |
| 4 | `/buckets/crawl-news/silver` | ssd | 2026-04-14 |
| 5 | `/buckets/crawl-gov/bronze` | hdd | 2026-04-14 |
| 6 | `/buckets/crawl-gov/silver` | ssd | 2026-04-14 |
| 7 | `/buckets/crawl-bds/bronze` | hdd | 2026-04-14 |
| 8 | `/buckets/crawl-bds/silver` | ssd | 2026-04-14 |
| 9 | `/buckets/marketpulse/bronze` | hdd | 2026-04-14 |
| 10 | `/buckets/marketpulse/silver` | ssd | 2026-04-14 |
| 11 | `/buckets/learning-hub` | hdd | 2026-09-03 |

**Verification:** Write to `crawl-news/bronze/test.txt` → volume 22 (HDD :8080). Write to `crawl-news/silver/test.txt` → volume 33 (SSD :8081). Confirmed 2026-04-14.

## 7. Access Control (S3 Identities)

Defined in `/etc/seaweedfs/config.json`.

| # | Identity | Access Scope | Actions | Purpose |
|---|----------|-------------|---------|---------|
| 1 | `admin` | All buckets | Admin, Read, Write, List, Tagging | Super admin — ops only, do not share |
| 2 | `learning-hub` | `learning-hub` only | Read, Write, List, Tagging (bucket-scoped) | rclone remote `lh` on Mac mini (`~/.config/rclone/rclone.conf`, `no_check_bucket = true` because HeadBucket is denied for scoped identities). Added 2026-09-03; Vault entry `infra/seaweedfs/learning-hub` pending (Vault sealed that day) |
| 3 | `llm-logs` | `llm-logs` only | Read, Write, List, Tagging (bucket-scoped) | CLI agent telemetry pipeline |
| 4 | `tuyen-dung` | `tuyen-dung` only | Read, Write, List, Tagging (bucket-scoped) | Recruitment workflow attachments |
| 5 | `trino` | `lakehouse` only | Read, Write, List, Tagging (bucket-scoped) | Trino Iceberg catalog on LXC 220 writes table data and metadata under `lakehouse/warehouse/`. Scoped deliberately: Trino has no authentication (`OPS01-homelab/docs/tech-debt.md` TD-43), so this identity is what keeps a destructive query inside one bucket. Added 2026-09-06; Vault entry pending (Vault still sealed) |

Rows 3 and 4 existed before this table was last written and were missing from it; they are listed
here from a live read of `/etc/seaweedfs/config.json` on 2026-09-06.

Adding an identity means editing that file and restarting the filer (`systemctl restart
seaweedfs-filer`), which interrupts S3 for **every** bucket for roughly two seconds — the running
S3 server reads the file once at startup and does not reload it.

> **TODO:** Create per-project identities with scoped permissions:
> - `stock-pipeline` → Read/Write `stock-data` only
> - `crawl-worker` → Write `crawl-*` bronze, Read `crawl-*` silver
> - `marketpulse` → Read/Write `marketpulse` only
> - Credentials stored in Vault (LXC 200, `infra/seaweedfs/*`)

## 8. Operational Runbook

### Start / Stop / Restart

```bash
ssh root@100.89.161.125

# Start all (respect boot order)
systemctl start seaweedfs-master
sleep 2
systemctl start seaweedfs-volume-hdd seaweedfs-volume-ssd
sleep 2
systemctl start seaweedfs-filer

# Stop all (reverse order)
systemctl stop seaweedfs-filer
systemctl stop seaweedfs-volume-hdd seaweedfs-volume-ssd
systemctl stop seaweedfs-master

# Restart single service (safe — master auto-reconnects)
systemctl restart seaweedfs-volume-hdd
```

### Add New Bucket

```bash
weed shell -master=localhost:9333 -filer=localhost:8888 <<'EOF'
s3.bucket.create -name=NEW_BUCKET
fs.mkdir /buckets/NEW_BUCKET/bronze
fs.mkdir /buckets/NEW_BUCKET/silver
fs.configure -locationPrefix=/buckets/NEW_BUCKET/bronze -disk=hdd -apply
fs.configure -locationPrefix=/buckets/NEW_BUCKET/silver -disk=ssd -apply
EOF

# MANDATORY: Update this doc → commit → push
```

### Delete Bucket

```bash
weed shell -master=localhost:9333 -filer=localhost:8888 <<'EOF'
s3.bucket.delete -name=BUCKET_NAME
fs.configure -locationPrefix=/buckets/BUCKET_NAME/bronze -delete -apply
fs.configure -locationPrefix=/buckets/BUCKET_NAME/silver -delete -apply
EOF

# MANDATORY: Update this doc → commit → push
```

### Add S3 Identity

Edit `/etc/seaweedfs/config.json`, add identity block, restart filer:
```bash
systemctl restart seaweedfs-filer

# MANDATORY: Update section 7 of this doc → commit → push
```

### Set Bucket Quota

```bash
weed shell -master=localhost:9333 -filer=localhost:8888 <<'EOF'
s3.bucket.quota -name=BUCKET_NAME -sizeMB=102400
EOF
```

## 9. Monitoring & Health Checks

### Service Health

```bash
# All services active?
systemctl is-active seaweedfs-master seaweedfs-volume-hdd seaweedfs-volume-ssd seaweedfs-filer

# Expected output: 4x "active"
```

### Cluster Status

```bash
# Master cluster
curl -s http://localhost:9333/cluster/status | python3 -m json.tool

# Volume topology (check both HDD and SSD nodes registered)
curl -s http://localhost:9333/vol/status | python3 -m json.tool

# Bucket list + sizes
weed shell -master=localhost:9333 -filer=localhost:8888 -shell='s3.bucket.list'

# Disk usage per bucket
weed shell -master=localhost:9333 -filer=localhost:8888 -shell='fs.du /buckets/crawl-news'

# Current fs.configure rules
weed shell -master=localhost:9333 -filer=localhost:8888 -shell='fs.configure'
```

### Disk Space

```bash
# HDD
df -h /mnt/hdd

# SSD (NVMe root)
df -h /

# Per-tier volume usage
du -sh /mnt/hdd/seaweedfs/     # HDD volumes
du -sh /data/seaweedfs-ssd/    # SSD volumes
```

### Alerts (manual check, automate later)

| Check | Command | Threshold |
|-------|---------|-----------|
| HDD usage | `df -h /mnt/hdd` | >80% → expand or archive |
| SSD usage | `df -h /` | >70% → expand or move Silver to HDD |
| Volume count | `curl localhost:9333/vol/status` | HDD >80/100 or SSD >40/50 → increase max |
| Filer DB size | `du -sh /mnt/hdd/seaweedfs/filerldb2/` | >1GB → consider external DB (MySQL/Postgres) |
| Service down | `systemctl is-active ...` | Any inactive → restart + investigate |

## 10. Disaster Recovery

### Backup Strategy

| Component | What | How | Frequency |
|-----------|------|-----|-----------|
| Filer metadata | `/mnt/hdd/seaweedfs/filerldb2/` | `weed shell fs.meta.save` → backup file | Daily |
| Master metadata | `/mnt/hdd/seaweedfs/m9333/` | rsync to backup host | Daily |
| Volume data (HDD) | `/mnt/hdd/seaweedfs/*.dat` | rsync to backup host | Weekly (large) |
| Volume data (SSD) | `/data/seaweedfs-ssd/*.dat` | rsync to backup host | Weekly |
| S3 config | `/etc/seaweedfs/config.json` | This git repo | Every change |
| fs.configure rules | In filer metadata | `weed shell fs.configure` output in this doc | Every change |

### Recovery Steps

```bash
# 1. Restore metadata
weed shell -master=localhost:9333 -filer=localhost:8888 <<'EOF'
fs.meta.load /path/to/backup.meta
EOF

# 2. Restore volume data
rsync -av backup:/seaweedfs/ /mnt/hdd/seaweedfs/
rsync -av backup:/seaweedfs-ssd/ /data/seaweedfs-ssd/

# 3. Restart all services
systemctl restart seaweedfs-master
sleep 2 && systemctl restart seaweedfs-volume-hdd seaweedfs-volume-ssd
sleep 2 && systemctl restart seaweedfs-filer

# 4. Verify
weed shell -master=localhost:9333 -filer=localhost:8888 -shell='s3.bucket.list'
```

## 11. Capacity Planning

### Current Usage (2026-04-14)

| Tier | Capacity | Used | Free | Volumes |
|------|----------|------|------|---------|
| HDD | 1.8 TB | 169 GB (all /mnt/hdd) | 1.6 TB | 14 active / 100 max |
| SSD | 84 GB (root) | ~6 GB (OS) | ~78 GB | 7 active / 50 max |

### Projected Usage

| Workload | Daily Ingest | Monthly | Tier |
|----------|-------------|---------|------|
| Stock data (Bronze) | ~50 MB | ~1.5 GB | HDD |
| News crawl (Bronze) | ~600 MB (12K pages × 50KB) | ~18 GB | HDD |
| Gov crawl (Bronze) | ~50 MB | ~1.5 GB | HDD |
| BDS crawl (Bronze) | ~200 MB (Phase 2) | ~6 GB | HDD |
| Silver (all) | ~20% of Bronze (after dedup + compression) | ~5 GB | SSD |

**HDD runway:** >5 years at current projection
**SSD runway:** ~12 months before needing expansion (78GB free, ~5GB/month Silver)

### Expansion Path

1. SSD full → add second NVMe or move cold Silver to HDD tier
2. HDD full → add second HDD to Proxmox, add new volume server
3. Volume count full → increase `-max` parameter and restart

## 12. SOP: Standard Operating Procedures

### SOP-001: Any Admin Change

1. SSH vào Proxmox: `ssh root@100.89.161.125`
2. Thực hiện thay đổi (xem runbook section 8)
3. Verify thay đổi thành công (xem monitoring section 9)
4. **Cập nhật file này** — update Current State sections
5. **Git commit:**
   ```bash
   cd ~/All_projects/DATA02-lakehouse
   git add docs/seaweedfs-ops.md
   git commit -m "ops(seaweedfs): <mô tả thay đổi> [M#.#]"
   ```
6. Nếu credentials thay đổi → update Vault (`infra/seaweedfs`)

### SOP-002: Monthly Review

1. Check disk usage (section 11)
2. Review bucket sizes: `s3.bucket.list`
3. Review failed volumes: `weed shell volume.check.disk`
4. Update capacity planning projections
5. Commit updated doc

---

## 13. Changelog

Format: `YYYY-MM-DD — Title`
- **Operator:** ai thực hiện
- **Ticket/Context:** lý do thay đổi
- **Changes:** liệt kê thay đổi
- **Verification:** kết quả verify
- **Rollback:** cách rollback nếu cần

---

### 2026-09-03 — Bucket `learning-hub`, identity giới hạn, mở S3 cho LAN, pin `-ip` filer

**Operator:** Claude Code + hoangnguyen
**Ticket/Context:** Learning Hub (BIZ03-edtech-vn) chuyển dữ liệu đề TOEIC, media và sao lưu D1 từ SSD ngoài của Mac mini
lên promax để dùng chung nhiều máy; đẩy qua LAN bằng rclone (quyết định #31 trong repo learning-hub).

**Changes:**

1. Identity `learning-hub` thêm vào `/etc/seaweedfs/config.json` (backup `config.json.bak-2026-09-03`), quyền
   `Read/Write/List/Tagging:learning-hub`; restart filer.
2. Sau restart filer bind sang `100.89.161.125` (Tailscale) vì unit không pin `-ip`; sửa unit thêm
   `-ip=192.168.0.200` (backup `seaweedfs-filer.service.bak-2026-09-03`), `daemon-reload`, restart.
3. iptables: chèn `ACCEPT -s 192.168.0.0/24 --dport 8333` trước rule DROP, `iptables-save` vào `rules.v4`.
4. `s3.bucket.create -name=learning-hub`; `fs.configure -locationPrefix=/buckets/learning-hub -disk=hdd -apply`.
5. Upload từ Mac mini (`192.168.0.107`) bằng `rclone copy` với `--transfers 8`: `media/` 169 object 220,8 MiB,
   `toeic-listening-pack/`, `toeic-pred/` (khoảng 2,8 GB).

**Verification:** từ promax `curl http://192.168.0.200:8333/` trả 403; từ Mac mini `rclone lsd lh:` liệt kê bucket,
`copyto` + `cat` + `deletefile` một file thử thành công; `tcpdump` trước khi sửa cho thấy SYN tới rồi RST.

**Rollback:** khôi phục hai file `.bak-2026-09-03`, `systemctl daemon-reload && systemctl restart seaweedfs-filer`;
xoá rule bằng `iptables -D INPUT -s 192.168.0.0/24 -p tcp --dport 8333 -j ACCEPT` rồi `iptables-save`;
bucket xoá theo mục 8 khi dữ liệu đã có nơi khác.

---

### 2026-04-14 — Migration: all-in-one → 4 services + multi-bucket setup

**Operator:** Claude Code + hoangnguyen
**Ticket/Context:** Chuẩn bị infra cho crawl pipeline news + BDS + gov. Cần phân biệt HDD/SSD cho Bronze/Silver tiers.

**Changes:**

1. **Topology migration** — tách `weed server` all-in-one thành 4 systemd services
   - Before: 1 process (`seaweedfs.service`) → single HDD only
   - After: master + volume-hdd + volume-ssd + filer (4 independent services)
   - Rationale: disk tiering, independent scaling, granular restart

2. **SSD volume server added** — NVMe volume server on port 8081
   - Dir: `/data/seaweedfs-ssd` (NVMe root partition)
   - 7 new volumes allocated (id 15-21)
   - Purpose: Silver layer storage (fast read for analytics)

3. **5 domain buckets created**
   - `stock-data`, `crawl-news`, `crawl-gov`, `crawl-bds`, `marketpulse`
   - Each with `bronze/` and `silver/` subdirectories
   - Bucket-per-domain strategy for isolated access control, quota, lifecycle

4. **10 fs.configure rules applied**
   - `{bucket}/bronze` → diskType=hdd (automatic routing)
   - `{bucket}/silver` → diskType=ssd (automatic routing)
   - Clients do NOT need `?disk=` parameter — server-enforced

5. **Old service deprecated**
   - `seaweedfs.service` stopped and disabled
   - Replaced by 4 new systemd units

**Verification:**
- All 4 services: `active`
- Write to `crawl-news/bronze/test.txt` → volume 22 (HDD :8080) ✓
- Write to `crawl-news/silver/test.txt` → volume 33 (SSD :8081) ✓
- All existing data in `lakehouse` bucket preserved (14 volumes, ~25KB) ✓
- Test files cleaned up after verification ✓

**Data impact:** None — existing `lakehouse` bucket data untouched

**Rollback:**
```bash
systemctl stop seaweedfs-filer seaweedfs-volume-ssd seaweedfs-volume-hdd seaweedfs-master
systemctl enable seaweedfs.service
systemctl start seaweedfs.service
# Note: new buckets + fs.configure rules persist in filer DB, would need manual cleanup
```
