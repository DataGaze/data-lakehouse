# Security Model — DataGaze Data Lakehouse

| Field | Value |
|-------|-------|
| Owner | @hoangnguyen (Platform Lead) |
| Last Updated | 2026-08-05 |
| Version | 0.2.0 |
| Status | Draft |
| Applies to | `data-lakehouse` (infra), `data-pipeline` (runtime), `ssi-connection` (producer) |

> Tài liệu này mô tả mô hình bảo mật cho data platform ở giai đoạn **solo-dev / home-lab → early SaaS**. Không claim compliance với SOC2/ISO27001/PCI-DSS. Mục tiêu: đạt mức *reasonable security hygiene* trước khi có user thật, và sẵn sàng siết chặt khi scale.

> **Bề mặt Prefect đã biến mất (2026-08-05).** `prefect-server` (LXC 201) và `prefect-worker`
> (LXC 202) stopped + disabled; xem [ADR 2026-08-05](./adr/2026-08-05-retire-prefect-adopt-dagster.md).
> Hệ quả về an ninh, đã phản ánh trong tài liệu:
>
> - `PREFECT_API_KEY` (S-11) không còn tồn tại — bỏ khỏi lịch rotate.
> - Cổng 4200 trên LXC 201 không còn service lắng nghe; ACL Tailscale `tag:prefect` giờ trỏ vào chỗ trống, nên **thu hồi được** khi rà soát ACL lần tới.
> - Các mục §1.4, §4 (pattern Secret block), §5.4, §7.4 và mọi ràng buộc gắn với Prefect
>   **không còn áp dụng**; giữ lại làm bản ghi cho tới khi Dagster dựng xong rồi viết lại
>   theo bề mặt thật của nó (webserver, daemon, code location, Postgres metadata).

---

## 1. Threat Model (STRIDE — tóm tắt)

Liệt kê attack surfaces chính của platform kèm threat category STRIDE tương ứng. Mỗi surface có ≥1 mitigation đã/đang triển khai.

### 1.1 Ingestion surface — `bizfly VPS → R2`

| Threat (STRIDE) | Kịch bản | Mitigation |
|-----------------|----------|------------|
| **S**poofing | Attacker giả danh bizfly upload file độc vào R2 | R2 access key gắn với IAM policy `PutObject` only, key chỉ nằm trên bizfly (`~/.ssi-connection/.env`) |
| **T**ampering | Parquet bị sửa đổi trên đường truyền | TLS 1.2+ bắt buộc khi gọi R2 endpoint, file checksum (MD5) verify tại consumer |
| **R**epudiation | Không biết ai upload file nào | R2 access log bật (xem §7) — log mọi `PutObject` với principal + timestamp |
| **I**nformation disclosure | SSI ConsumerID/Secret leak từ bizfly | Secrets chỉ trong `.env` (mode 600), không log, không commit |
| **D**oS | Attacker flood upload khiến cron stuck | Cron có `timeout 300` wrapper, R2 bucket quota giám sát |
| **E**oP | SSH vào bizfly rồi pivot sang home lab | Bizfly SSH key-only, port 2222, không có đường outbound vào LXC — home lab là pull-based, xem §6 |

### 1.2 Storage surface — `R2 + SeaweedFS + Postgres`

| Threat | Kịch bản | Mitigation |
|--------|----------|------------|
| **S**poofing | Giả danh consumer đọc R2 | Read key tách biệt write key; SeaweedFS chỉ bind internal network |
| **T**ampering | Parquet ở Bronze bị sửa sau khi land | Bronze treat as **immutable** — không có process nào được `UPDATE` Bronze; chỉ Prefect producer có write creds |
| **I**nformation disclosure | Postgres dump leak qua backup không mã hóa | Backup encrypt với `age`/`gpg` trước khi rời LXC |
| **E**oP | Prefect worker leo quyền từ readonly → admin | Postgres roles tách biệt per schema, worker nhận credential `readwrite` không phải `admin` |

### 1.3 Query surface — `dbt runs + ad-hoc analyst access`

| Threat | Kịch bản | Mitigation |
|--------|----------|------------|
| **T**ampering | Analyst vô tình `DROP TABLE` ở prod schema | Analyst role `readonly` trên schema `prod`, chỉ `readwrite` trên `dbt_{user}_dev` |
| **I**nformation disclosure | Connection string leak qua Prefect UI logs | Prefect block `Secret` mask giá trị, log scrubber loại env var nhạy cảm |

### 1.4 Monitoring surface — `Telegram bot + Prefect alerts` [PHẦN PREFECT KHÔNG CÒN ÁP DỤNG]

| Threat | Kịch bản | Mitigation |
|--------|----------|------------|
| **S**poofing | Attacker biết bot token → gửi fake alert lừa operator | Bot token rotate 90 ngày (§4.2); chat_id cố định whitelist |
| **I**nformation disclosure | Alert rò rỉ row counts / schema → attacker map dữ liệu | Alert content giới hạn: flow_name + status + error class, không dump row data |

---

## 2. Data Classification

| Tier | Định nghĩa | Ví dụ trong platform | Storage rule |
|------|------------|----------------------|--------------|
| **Public** | Thông tin đã công bố công khai | VN-Index values, close price niêm yết, mã cổ phiếu | Có thể cache bất cứ đâu, không cần encrypt at rest |
| **Internal** | Derived / aggregated — không có IP nghiêm ngặt nhưng không nên publish | Silver daily aggregates, dbt gold models, custom signals | Postgres `prod` schema, access qua role `readonly`; backup encrypt |
| **Confidential** | Credentials + secrets, leak = breach | SSI **ConsumerID**, SSI **ConsumerSecret**, R2 **access_key_id** + **secret_access_key**, Postgres **password** (prod + dev), **Telegram bot token**, Tailscale auth key | SOPS-encrypted hoặc env var tại runtime, KHÔNG bao giờ trong git plaintext, rotate 90 ngày |
| **PII** | Personally Identifiable Information | **Không có.** Stock market data không chứa PII. | N/A (giữ nguyên note này để reviewer biết đã xét) |

> **Lưu ý future SaaS:** Khi thêm user accounts (email, billing), promote sang tier mới "PII-Regulated" với GDPR-like handling (§9).

---

## 3. Secrets Inventory (concrete list)

Liệt kê đầy đủ secrets hiện đang dùng — audit cần biết **cái gì phải rotate**.

| ID | Secret | Nơi phát sinh | Nơi tiêu thụ | Rotation cadence |
|----|--------|---------------|--------------|------------------|
| S-01 | `SSI_CONSUMER_ID` | iboard.ssi.com.vn portal | bizfly `ssi-connection` | 90 ngày |
| S-02 | `SSI_CONSUMER_SECRET` | iboard.ssi.com.vn portal | bizfly `ssi-connection` | 90 ngày |
| S-03 | `R2_ACCESS_KEY_ID` (producer) | Cloudflare R2 dashboard | bizfly `ssi-connection` uploader | 90 ngày |
| S-04 | `R2_SECRET_ACCESS_KEY` (producer) | Cloudflare R2 dashboard | bizfly | 90 ngày |
| S-05 | `R2_ACCESS_KEY_ID` (consumer) | Cloudflare R2 dashboard | LXC 202 `lakehouse-gold` (ETL run) | 90 ngày |
| S-06 | `R2_SECRET_ACCESS_KEY` (consumer) | Cloudflare R2 dashboard | LXC 202 | 90 ngày |
| S-07 | `PG_PASSWORD_ADMIN` | Postgres `CREATE ROLE` | DBA only, migrations | 90 ngày |
| S-08 | `PG_PASSWORD_READWRITE` | Postgres | ETL run (Bronze → Silver → Gold) | 90 ngày |
| S-09 | `PG_PASSWORD_READONLY` | Postgres | Analyst dbt dev, dashboard read | 180 ngày |
| S-10 | `TELEGRAM_BOT_TOKEN` | @BotFather | `MarketPulse`, ETL alert | 90 ngày |
| ~~S-11~~ | ~~`PREFECT_API_KEY`~~ | — | **Đã bỏ 2026-08-05** cùng Prefect; không còn gì phải rotate. Secret của Dagster sẽ thêm khi dựng | — |
| S-12 | `TAILSCALE_AUTHKEY` | admin console | node bootstrap only (one-shot) | Per-use, ephemeral |
| S-13 | `SEAWEEDFS_S3_ACCESS/SECRET` | SeaweedFS `weed.toml` | ETL workloads | 90 ngày |

**Không có trong list này = không được tạo silently.** Khi thêm secret mới, update bảng này trong cùng PR.

---

## 4. Secrets Management

### 4.1 Storage — SOPS-encrypted trong git (chosen)

**Quyết định:** Dùng **[SOPS](https://github.com/getsops/sops)** với **age** backend. Lý do chọn SOPS thay vì 1Password CLI:

- Git-native (secrets version cùng code)
- Offline decrypt (không cần mạng vào 1Password)
- Per-file key → granular access
- Age key nhỏ, dễ backup, không cần account SaaS

**Layout:**

```
data-lakehouse/
├── .sops.yaml                     # quy tắc encrypt theo path
├── secrets/
│   ├── prod/
│   │   ├── postgres.enc.yaml      # S-07, S-08, S-09
│   │   ├── r2-consumer.enc.yaml   # S-05, S-06
│   │   └── telegram.enc.yaml      # S-10
│   └── dev/
│       └── postgres.enc.yaml
└── keys/
    └── .gitkeep                   # age public keys (committed), private keys KHÔNG commit
```

**`.sops.yaml` example:**

```yaml
creation_rules:
  - path_regex: secrets/prod/.*\.enc\.yaml$
    age: >-
      age1plat0rmleadpubk3yxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx,
      age1dbadminpubk3yxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  - path_regex: secrets/dev/.*\.enc\.yaml$
    age: >-
      age1devpubk3yxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Encrypt / decrypt example:**

```bash
# Encrypt lần đầu
sops --encrypt --in-place secrets/prod/postgres.enc.yaml

# Edit (auto decrypt → open $EDITOR → re-encrypt on save)
sops secrets/prod/postgres.enc.yaml

# Decrypt ra stdout (dùng trong Prefect deployment)
sops --decrypt secrets/prod/postgres.enc.yaml
```

Age private key location: `~/.config/sops/age/keys.txt` (mode 600), **KHÔNG** bao giờ commit. Backup vào 1Password personal vault (physical safety net).

### 4.2 Rotation Policy

| Tier | Cadence | Trigger ngoài cadence |
|------|---------|-----------------------|
| Confidential (S-01 → S-13, trừ S-12) | **90 ngày** | Suspected leak, dev rời team, `git log -S <secret>` match, laptop mất |
| `PG_PASSWORD_READONLY` (S-09) | 180 ngày | (đọc thuần, impact thấp hơn) |
| `TAILSCALE_AUTHKEY` (S-12) | Ephemeral | Hết ngay sau khi node join xong |

**Rotation SOP** (xem §8.1 cho emergency variant):

1. Tạo secret mới tại nguồn (SSI portal / R2 dashboard / `ALTER ROLE … PASSWORD …`)
2. Update `secrets/{env}/{file}.enc.yaml` qua `sops`
3. Commit với message `chore(secrets): rotate S-03 R2 producer key [M7.1]`
4. Trigger Prefect deployment redeploy để inject giá trị mới
5. Revoke secret cũ tại nguồn (≤ 24h)
6. Verify flow run thành công một cycle đầy đủ
7. Update calendar reminder cho lần rotate kế tiếp

### 4.3 Access Pattern — Runtime injection

- **Không bao giờ** hard-code vào source code
- **Không bao giờ** đặt trong Prefect UI "parameters" (ghi plaintext trong DB Prefect)
- Pattern chuẩn: Prefect [Secret block](https://docs.prefect.io/) load từ SOPS-decrypted file tại worker startup, expose qua `os.environ` cho flow

```python
# flows/ingest_stock.py
from prefect import flow
from prefect.blocks.system import Secret

@flow
def ingest_stock():
    r2_key = Secret.load("r2-consumer-access-key").get()
    r2_secret = Secret.load("r2-consumer-secret").get()
    # ...
```

Block được populate từ `make deploy`:

```makefile
deploy:
	sops -d secrets/prod/r2-consumer.enc.yaml | python scripts/populate_prefect_blocks.py
	prefect deployment apply deployments/ingest_stock.yaml
```

---

## 5. Authentication & Authorization

### 5.1 Postgres Roles (per schema)

Database: `datagaze` (xem ADR D6).

| Role | Grants | Thành viên |
|------|--------|-----------|
| `datagaze_admin` | ALL on DATABASE datagaze | DBA (platform lead) only |
| `datagaze_prod_rw` | USAGE + CRUD on schema `prod` | ETL run trên LXC 202 |
| `datagaze_prod_ro` | USAGE + SELECT on schema `prod` | Analyst tools, dashboard API, `MarketPulse` |
| `datagaze_dev_rw` | ALL on schema `dbt_*_dev` | Local dev per-user |
| ~~`prefect_meta_rw`~~ | ~~CRUD on schema `prefect`~~ | **Bỏ 2026-08-05** — Prefect dùng SQLite, role này chưa từng được tạo |

**Bootstrap DDL** (living reference — actual DDL trong `migrations/`):

```sql
CREATE ROLE datagaze_prod_rw LOGIN PASSWORD :'pwd_rw';
CREATE ROLE datagaze_prod_ro LOGIN PASSWORD :'pwd_ro';

GRANT USAGE ON SCHEMA prod TO datagaze_prod_rw, datagaze_prod_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA prod TO datagaze_prod_ro;
GRANT INSERT, UPDATE, DELETE, SELECT ON ALL TABLES IN SCHEMA prod TO datagaze_prod_rw;

ALTER DEFAULT PRIVILEGES IN SCHEMA prod
    GRANT SELECT ON TABLES TO datagaze_prod_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA prod
    GRANT INSERT, UPDATE, DELETE, SELECT ON TABLES TO datagaze_prod_rw;
```

Principle of least privilege: **không có role nào có `CREATE` trên schema `prod` ngoài migrations chạy bởi `datagaze_admin`**.

### 5.2 R2 Bucket Policies

Bucket `datagaze-lakehouse` có 2 API tokens:

- **Producer token (S-03, S-04):** `Object Write` only trên prefix `raw/`. Không thể list, không thể delete → minimize blast radius nếu bizfly bị compromise.
- **Consumer token (S-05, S-06):** `Object Read` + `List Bucket` trên prefix `raw/`. Không write.

Tokens scope qua Cloudflare R2 token config, không dựa trên IAM policy JSON (R2 chưa support full IAM như AWS S3 thời điểm viết).

### 5.3 SSH Access

- **Không password auth.** `PasswordAuthentication no` trong `sshd_config` mọi node.
- Auth chỉ qua **ed25519 keys** + **Tailscale SSH** (§6.1).
- Mac mini, LXC 201/202, bizfly VPS đều vào Tailnet → SSH qua `tsh` hoặc `ssh user@<tailnet-hostname>`.
- Bizfly giữ port 2222 public (legacy, dùng key auth) vì cron 24/7 không phụ thuộc Tailscale availability. Kế hoạch: chuyển hẳn sang Tailscale khi stable → đóng port 2222 ra internet.

### 5.4 Prefect UI / API [KHÔNG CÒN — service đã gỡ 2026-08-05]

- Prefect server bind `0.0.0.0` trong Tailnet, **không** expose ra public internet
- API key (S-11) required cho mọi write operation
- UI access qua `https://prefect.lakehouse.tail-scale-abcd.ts.net` (Tailscale magic DNS + auto-TLS)

---

## 6. Network Security

### 6.1 Tailscale Mesh (zero-trust)

Topology:

```
            Tailnet (100.x.x.x/32 per node)
       ┌──────────────┬──────────────┬──────────────┐
       │              │              │              │
  Mac mini         LXC 201        LXC 202         bizfly VPS
  (dev)         (prefect-srv)  (lakehouse-gold)   (producer)
  tag:dev        tag:prefect    tag:lakehouse     tag:producer
```

- Mọi inter-node traffic đi qua **Tailscale WireGuard** → mặc định encrypted, peer-authenticated
- ACL (in `tailscale-acl.json`, commit trong repo này):

```jsonc
{
  "acls": [
    // Prefect worker → Postgres
    {"action": "accept", "src": ["tag:lakehouse"], "dst": ["tag:lakehouse:5432"]},
    // Dev → Prefect UI + Postgres dev schema
    {"action": "accept", "src": ["tag:dev"], "dst": ["tag:prefect:4200", "tag:lakehouse:5432"]},
    // Producer KHÔNG có inbound từ tailnet (chỉ outbound → R2)
    {"action": "accept", "src": ["tag:producer"], "dst": ["*:*"]}
  ],
  "ssh": [
    {"action": "accept", "src": ["tag:dev"], "dst": ["tag:*"], "users": ["autogroup:nonroot"]}
  ]
}
```

### 6.2 Firewall Rules (LXC level)

`ufw` default deny inbound. Rules:

| LXC | Port | Source | Purpose |
|-----|------|--------|---------|
| 201 prefect-server | ~~4200/tcp~~ | — | **Không còn service lắng nghe** (gỡ 2026-08-05) |
| 202 lakehouse-gold | 5432/tcp | Tailnet only | Postgres |
| 202 lakehouse-gold | 30333/tcp | Tailnet only | SeaweedFS S3 |

Public internet: **zero inbound ports** trên LXC. Bizfly giữ 2222 (legacy, xem §5.3).

### 6.3 TLS Everywhere

- **Postgres:** `ssl = on` + `ssl_min_protocol_version = 'TLSv1.2'`. Client connect bắt buộc `sslmode=verify-full` với CA cert self-signed committed vào `config/postgres-ca.pem`.
- **Prefect UI/API:** Tailscale-issued LetsEncrypt cert (magic DNS) → TLS 1.3.
- **R2:** Cloudflare enforce TLS 1.2+; boto3 default verify cert chain.
- **SeaweedFS S3:** Internal only, TLS optional (Tailscale đã encrypt). Future: enable native TLS khi cross-LXC.

---

## 7. Audit & Logging

### 7.1 Postgres Audit

- `log_connections = on`, `log_disconnections = on`
- `log_statement = 'ddl'` — capture mọi DDL (CREATE/ALTER/DROP)
- `pgaudit` extension cho `ROLE, WRITE` tại schema `prod`
- Log retention: 90 ngày local, rotate via `logrotate`

### 7.2 R2 Access Log

- Enable Cloudflare R2 event notifications → log `PutObject`, `GetObject`, `DeleteObject` kèm principal (access key ID) và source IP
- Ship sang Logpush nếu volume tăng (future)

### 7.3 Git Commit Audit

- Mọi commit có phase code `[X#.#]` (CLAUDE.md convention) → trace được intent
- **Signed commits (GPG/SSH signature): optional hiện tại, required khi onboard contributor thứ 2**
- `secrets/**/*.enc.yaml` là file duy nhất chứa ciphertext → `git log --all -- secrets/` liệt kê mọi lần rotate

### 7.4 Prefect Run Audit [KHÔNG CÒN — viết lại khi Dagster chạy]

- Mọi flow run có run_id, start/end timestamp, trigger source (manual vs schedule)
- Retention 90 ngày trong Prefect DB; export JSON snapshot sang Bronze cho audit dài hạn (future)

---

## 8. Incident Response (Security-specific)

Runbook ngắn. Full IR playbook ở `docs/runbook-incident.md` (general ops).

### 8.1 Scenario A — Key Leak

Ví dụ: `SSI_CONSUMER_SECRET` lộ qua screenshot / push nhầm lên public repo.

**Checklist (hoàn thành trong ≤ 2h):**

- [ ] Confirm leak: grep GitHub, WaybackMachine, internal chat
- [ ] Revoke key ngay tại nguồn (SSI portal → regenerate)
- [ ] Tạo key mới, encrypt qua SOPS, commit `chore(secrets): emergency rotate S-02 [M#.#]`
- [ ] Redeploy Prefect flows dùng key đó: `make deploy ENV=prod`
- [ ] Kiểm tra access log 30 ngày qua cho key cũ — có signature lạ không
- [ ] Nếu repo public leak: dùng `git filter-repo` purge, force-push, cảnh báo GitHub
- [ ] Post-mortem: viết trong `docs/incidents/YYYY-MM-DD-key-leak-Sxx.md`, root cause, action items

### 8.2 Scenario B — Unauthorized Access (suspect)

Ví dụ: Postgres log xuất hiện connection từ IP ngoài Tailnet, hoặc R2 có `GetObject` với principal không quen.

**Isolation steps (≤ 30 phút):**

1. **Freeze:** Disable key nghi ngờ tại nguồn (R2 token / Postgres `ALTER ROLE … NOLOGIN`)
2. **Snapshot:** Dump Postgres log last 24h, R2 access log last 24h → save `/var/log/ir/YYYY-MM-DD/`
3. **Cut network:** Tailscale ACL tạm block tag đáng ngờ; nếu LXC compromise → `pct stop 202` trên Proxmox
4. **Forensics:** So sánh `last`, `journalctl -u postgresql`, file mtime của Bronze với baseline
5. **Scope:** Xác định dữ liệu nào có thể đã exfiltrate (Bronze immutable nên tampering khó; Gold có thể đã read)
6. **Notify:** Nếu dính user data (future SaaS) → disclosure theo §9
7. **Recover:** Rebuild LXC từ Proxmox snapshot gần nhất trước compromise window
8. **Learn:** Post-mortem trong 72h

---

## 9. Compliance Notes (forward-looking)

Hiện tại **chưa có user thật**, không thuộc phạm vi điều chỉnh compliance cụ thể. Note sẵn cho khi move sang SaaS:

- **GDPR-like (nếu có EU user):** data minimization, right-to-erasure cho user PII; stock data không bị ảnh hưởng
- **Luật An ninh mạng Việt Nam (Luật số 24/2018/QH14):** nếu lưu data người dùng VN trên server ngoài VN → cần local storage mirror hoặc MoU với cơ quan quản lý. Hiện R2 là Cloudflare (global) — khi có user VN, đánh giá lại.
- **Luật Bảo vệ dữ liệu cá nhân 2023 (Nghị định 13/2023/NĐ-CP):** áp dụng nếu xử lý dữ liệu cá nhân VN; cần DPIA (Data Protection Impact Assessment) và consent mechanism

**Không claim:** SOC2, ISO 27001, PCI-DSS, HIPAA. Sẽ update version khi audit thật.

---

## 10. Security Checklist — Pre-Production Gate

**Gate này phải tick hết 100% trước khi cho phép user thật connect (= trước chuyển phase L — Launched).**

### 10.1 Secrets hygiene
- [ ] Mọi secret trong §3 đã encrypt qua SOPS, không plaintext trong git
- [ ] Age private key backup offline (1Password personal + USB encrypted)
- [ ] `git log -p --all` grep không thấy pattern `password=`, `secret=`, `token=` plaintext
- [ ] Pre-commit hook có [gitleaks](https://github.com/gitleaks/gitleaks) / `detect-secrets` active
- [ ] `.env` files có trong `.gitignore`; `.env.example` chỉ placeholder
- [ ] Rotation calendar đặt reminder cho cả 13 secrets

### 10.2 AuthN / AuthZ
- [ ] Postgres roles theo §5.1, verify `\du+` output
- [ ] R2 producer token không có `GetObject` (least privilege)
- [ ] SSH password auth disabled trên mọi host
- [ ] Prefect API key required (check `prefect config view`)

### 10.3 Network
- [ ] Tất cả LXC trong Tailnet, ACL committed và apply
- [ ] `ufw status verbose` không có rule public inbound ngoài expected
- [ ] Postgres `ssl = on` và client test `sslmode=verify-full` thành công
- [ ] `nmap` từ public internet → zero open port trên home lab IP

### 10.4 Audit
- [ ] `pg_stat_activity` log verify có DDL entries
- [ ] R2 event notification bật, test bằng 1 upload giả
- [ ] Prefect flow log không in secret (grep giá trị test token)

### 10.5 Incident readiness
- [ ] Runbook §8 đã được tabletop exercise ≥ 1 lần
- [ ] Post-mortem template tồn tại tại `docs/incidents/_template.md`
- [ ] Contact list (Cloudflare support, SSI support, DBA on-call) current

### 10.6 Backup & recovery
- [ ] Postgres `pg_dump` hàng đêm, encrypt bằng `age`, lưu R2 bucket khác
- [ ] Test restore từ backup ≤ 30 ngày tuổi thành công
- [ ] Proxmox snapshot LXC 202 hàng tuần, retention 4 tuần

---

## Changelog

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 0.1.0 | 2026-04-13 | @hoangnguyen | Initial draft — covers bizfly → R2 → lakehouse-gold flow, SOPS + Tailscale, 13 secrets inventory, pre-prod checklist |
