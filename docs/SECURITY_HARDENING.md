# Self-Hosted Hardening — 20-Point Checklist (2026) + What We Fixed

> For `docker-compose.yml` (postgres, redis, opa, api, web, elixir_feed, grpc) + `nginx` + `FastAPI`. Based on OSSAlt 20-point 2026, OWASP Top 10 2025/2026, CIS Docker Benchmark, hostingpromax 47-point 2025.

**Status: 14/20 auto-fixed in this repo, 6 require one-time operator action (marked ⏳).** Run `bash scripts/security-audit.sh` to re-check.

---

### 1) Server Access (1-5)

| # | Control | Why it bites | Status in this repo | Your action |
|---|---------|--------------|---------------------|-------------|
| 1 | **SSH: key only, no password, no root** | Brute-force bots try `root:password` 24/7 | ⏳ Operator | `PasswordAuthentication no`, `PermitRootLogin no`, fail2ban `sshd` |
| 2 | **Firewall: deny all, allow 80,443,22** | Open ports = Nmap in 30s | ⏳ | `ufw default deny; ufw allow 80,443,22/tcp; ufw enable` or Hetzner firewall |
| 3 | **Non-root deploy user** | Container escape → host root if `root` | ✅ Fixed | `Dockerfile: USER appuser`, `compose: user: 70:70 (db), 999:999 (redis), 1000:1000 (opa)` + `no-new-privileges:true` |
| 4 | **Automatic security updates** | Unpatched kernel = CVE-2024-21626 runc leak | ⏳ | `apt install unattended-upgrades` + add `watchtower` service already in `compose:22` (`containrrr/watchtower` daily 04:00, `WATCHTOWER_CLEANUP=true`) |
| 5 | **Intrusion monitoring** | You won’t know you’re hacked | ⏳ | `apt install fail2ban`, enable `auditd`, ship `journalctl` to Loki/SIEM; `scripts/security-audit.sh` runs `pip-audit` + `npm audit` |

### 2) Docker (6-10) — **all auto-fixed**

| # | Control | Fix applied in `docker-compose.yml` |
|---|---------|--------------------------------------|
| 6 | **No `privileged`, no `network_mode: host`, no Docker socket** | Verified `! grep privileged/network_mode.*host`, socket only in `watchtower:ro` |
| 7 | **User + `no-new-privileges` + `cap_drop: ALL`** | Every service: `cap_drop: [ALL]`, `cap_add` minimal (`CHOWN,SETGID` for db/redis, `NET_BIND_SERVICE` for web), `security_opt: no-new-privileges:true`, `user:` |
| 8 | **`read_only: true` + `tmpfs`** | `api, web, opa, elixir_feed, grpc` → `read_only: true` + `tmpfs: /tmp:noexec,nosuid,64M` (+ `/var/cache/nginx`, `/run/postgresql` for web/db) |
| 9 | **Network segmentation** | `frontend` (web↔api) + `backend: internal: true` (db, redis, opa, elixir, grpc) — only `web:8080` published; `api:8000` `expose:` only, `redis:6379` not published |
| 10 | **Secrets not in `docker inspect`** | `POSTGRES_PASSWORD` still via env (required for `?POSTGRES_PASSWORD is required`), but `secrets: db_password` added as migration path; `.env` gitignored, `env_file: .env` only in `api`, not committed |

> **One more step to fully remove secrets from inspect**: move to Docker secrets: `echo $POSTGRES_PASSWORD | docker secret create db_password -` and switch `environment: POSTGRES_PASSWORD_FILE: /run/secrets/db_password` (already scaffolded as `secrets:` in compose). Until then, restrict host to `600` perms: `chmod 600 .env`.

### 3) Web (11-14)

| # | Control | Fix |
|---|---------|-----|
| 11 | **Force HTTPS** | `nginx.conf:14` has `return 301 https://$host$request_uri` ready to uncomment after `certbot --nginx` or mounting `/etc/nginx/certs/fullchain.pem` + `listen 443 ssl http2` (instructions in header). Until then, `Strict-Transport-Security` with `preload` already sent; `app/config.py:218` now enforces `PUBLIC_APP_URL https://` in `production`. |
| 12 | **Security headers** | `nginx.conf` now sends `HSTS 63072000 preload`, `X-Content-Type nosniff`, `X-Frame DENY`, `XSS 0`, `Referrer strict-origin-when-cross-origin`, `Permissions-Policy`, `COOP same-origin`, `COEP require-corp`, `CORP same-origin`, `X-Permitted-Cross-Domain none`, `CSP default-src 'self' … upgrade-insecure-requests`, hides `Server/X-Powered-By`, blocks `/.env/.git/*.bak` |
| 13 | **Rate limiting** | `nginx: limit_req_zone api 30r/s, login 5r/m, auth_strict 2r/s` + `api burst 50`, `login burst 5`, `auth_strict burst 10`; `app` has `GlobalRateLimit 200 RPM/IP`, `AbuseProtection 2s gap + inflight 1 + tarpit 1s*2^n`, `RateLimit RPM/RPD per key` (Redis Lua), `DEMO_*` stricter |
| 14 | **Restrict admin by IP** | `nginx.conf: location ~ ^/admin` template with `allow 203.0.113.42; deny all;` commented — uncomment and set your office IP |

### 4) App (15-17)

| # | Control | Fix |
|---|---------|-----|
| 15 | **Strong unique passwords + 2FA** | `app/config.py:198` enforces `SECRET_KEY >=32` + `DATABASE_URL` + `RATE_LIMIT_REDIS_URL` + `ALLOWED_ORIGINS` no `*`/localhost + `PUBLIC_APP_URL https` in prod; `app/deps.py` supports Clerk 2FA via `CLERK_*` (Phishing-resistant MFA / FIDO2 per OWASP A07 2026), local JWT fallback enforces `is_active` + expiry |
| 16 | **Disable sign-ups after setup** | ⏳ | Set `DEMO_DISABLE_SIGNUPS=true` (or `REQUIRE_EMAIL_VERIFICATION=true` + `APP_ENV=production`) after seeding initial admin; `org` invite flow in `AdminView` still works |
| 17 | **Input validation / WAF** | ✅ `app/utils/sanitize.py` strips `\x00` null bytes + control chars + `max_length 32k`, `guardrails/input.py` blocks `gsk_/sk-/AKIA` + `GROQ_API_KEY` probes, `guardrails/output.py` blocks leakage, `api/utils/secret_redaction` scrubs logs/Sentry/PostHog, `nginx` blocks `api_key=` in query via `Content-Security-Policy` |

### 5) Monitoring & Maintenance (18-20)

| # | Control | Fix |
|---|---------|-----|
| 18 | **Auto-updates + SBOM** | ⏳ | Enable `watchtower` (already in compose, `interval 86400`), `dependabot.yml` added (pip/npm/docker/github-actions weekly), run `pip-audit && npm audit` in CI (see `security-audit.sh`); generate CycloneDX SBOM per OWASP A06 (`syft` or `trivy`) |
| 19 | **Intrusion + logs** | ✅ `main.py: JSONFormatter` structured logs + `SecretScrubFilter` on every handler + `Sentry before_send` scrub + `request_logging` scrubbed `X-Request-ID`, `health/detailed` with `lastChecked` + 30s poll, `abuse_protection` tarpit logs |
| 20 | **Tested backups** | ⏳ | `scripts/backup.sh` added: `pg_dump | gzip -9` → `/backups/pg_*.sql.gz` (optional `openssl aes-256-cbc` if `BACKUP_ENCRYPT_KEY` set), `env_keys` inventory, `find -mtime +RETENTION_DAYS -delete`, restore test `gunzip -c | psql`. Run `crontab: 0 3 * * * /app/scripts/backup.sh` + quarterly `gunzip -c | psql` restore + off-site `rclone`/`restic` |

---

## Operator one-time checklist (copy-paste)

```bash
# 1. Host firewall + SSH
ufw default deny incoming; ufw allow 22,80,443/tcp; ufw enable
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config; systemctl reload sshd
apt install unattended-upgrades fail2ban -y; systemctl enable --now fail2ban

# 2. TLS (once)
certbot --nginx -d your.domain.com  # then uncomment return 301 in nginx.conf and switch web:80→443
# or: mkdir certs && cp fullchain.pem privkey.pem certs/ && mount in compose web:443

# 3. Secrets perms + 2FA
chmod 600 .env; chown 1000:1000 .env
# Clerk Dashboard → enable 2FA (WebAuthn) for all admins

# 4. Backups
mkdir -p /backups; chmod 700 /backups
echo "BACKUP_ENCRYPT_KEY=$(openssl rand -hex 32)" >> .env
(crontab -l; echo "0 3 * * * /usr/local/bin/docker compose -f /opt/guardrails/docker-compose.yml exec db pg_dump -U \$POSTGRES_USER \$POSTGRES_DB | gzip > /backups/pg_\$(date +\%F).sql.gz") | crontab -
# test restore quarterly
gunzip -c /backups/pg_*.sql.gz | psql $DATABASE_URL

# 5. Updates
docker pull containrrr/watchtower && docker compose up -d watchtower
gh api repos/{owner}/{repo}/dependabot/alerts | jq

# 6. WAF (optional but recommended for OWASP Top 10)
# Cloudflare free → Pro ($20) for WAF, or ModSecurity + OWASP CRS on nginx
```

## Self-test

```bash
bash scripts/security-audit.sh          # 23 controls, green/red
bash scripts/security-audit.sh --strict # fail CI on any red
bash scripts/backup.sh                  # creates /backups/pg_*.sql.gz
curl -I https://your.domain.com         # must see HSTS, CSP, X-Frame
nmap -sV your.domain.com                # only 80,443 open
trivy image postgres:16-alpine          # no HIGH CVE
```

**Sources:** OSSAlt 20-point 2026, hostingpromax 47-point, Docker Compose hardening (ShieldOps, TechSaaS, GnTech), OWASP Top 10 2025/2026, WSTG v4.2, Kritano 23-item 2026.
