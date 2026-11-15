# Deployment runbook

This is the production runbook for one school on one VPS. It covers a fresh
Ubuntu server, automatic HTTPS, the first deploy, Paystack webhooks, nightly
backups, and a tested restore. It does **not** cover multi-tenancy; a second
school gets its own server, domain, database and `.env`.

The public request path is:

```text
Internet :80/:443
        │
        ▼
     Caddy  ── automatic Let's Encrypt certificate, HTTP → HTTPS
        │      HSTS + security headers
        ▼
     Nginx  ── Angular SPA at /, reverse proxy for /api/ /admin/ /static/ /media/
        │      bound only to 127.0.0.1:8080 on the host
        ▼
   Gunicorn ── Django API and admin
        │
        ▼
   PostgreSQL 16
```

Caddy is the only public container. `docker-compose.prod.yml` forces Django's
HTTPS settings on, and Nginx preserves Caddy's `X-Forwarded-Proto: https` so
`SECURE_SSL_REDIRECT` does not loop.

---

## 0. What you need before touching the server

- [ ] A domain or subdomain you control, e.g. `school.example.edu.ng`.
- [ ] A VPS with **2 vCPU / 2 GB RAM minimum** (4 GB recommended), 20 GB disk,
      Ubuntu 24.04 LTS, and your SSH public key installed.
- [ ] DNS access to create an `A` record pointing at the VPS IPv4 address.
      Add an `AAAA` record only if the VPS has working IPv6.
- [ ] Paystack **live** secret and public keys, with the business activated for
      live payments and a settlement bank account.
- [ ] Termii API token and an **approved Sender ID** for production SMS. Obtain
      WhatsApp device/template IDs only if WhatsApp will be enabled.
- [ ] The school's real name, logo, current session and term, and the
      administrator username/password you will create.
- [ ] A decision on `DEFAULT_STUDENT_PASSWORD`; students must change it at first
      login, but it still should not be a public default.
- [ ] Ports **22, 80 and 443** open. Ports 80 and 443 must be reachable from the
      public internet for certificate issuance.

> If the domain is behind Cloudflare, set the record to **DNS only** (grey cloud)
> for the first certificate issue. After Caddy has a certificate, you may enable
> proxying and use **Full (strict)**. Never use Flexible mode: Django would see
> HTTP and redirect endlessly.

---

## 1. Provision the VPS

SSH in as the initial user (`root` on most providers):

```bash
ssh root@YOUR_SERVER_IP
apt update && apt upgrade -y
timedatectl set-timezone Africa/Lagos
```

Create a non-root deploy user and copy your SSH key to it:

```bash
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

Test the new login in a **second terminal** before closing the first:

```bash
ssh deploy@YOUR_SERVER_IP
sudo whoami          # prints: root
```

Firewall (only Caddy publishes public ports; Nginx is loopback-only):

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw --force enable
sudo ufw status
```

Install Docker Engine and the Compose plugin:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
```

Log out and back in so the group applies, then verify:

```bash
docker --version
docker compose version
```

On a 2 GB server, add swap so the Angular and Python image builds do not get
OOM-killed:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

Point DNS at the server **now**, before starting Caddy:

```bash
# From your own machine, not the server:
dig +short school.example.edu.ng
```

It must print the VPS IPv4 address. Certificate issuance will fail until DNS
resolves publicly.

---

## 2. Put the code on the server

Use a read-only GitHub deploy key rather than a personal token in shell history.
Clone into `/srv`:

```bash
sudo mkdir -p /srv/academic-dashboard
sudo chown deploy:deploy /srv/academic-dashboard
git clone <YOUR_GITHUB_REPO_URL> /srv/academic-dashboard
cd /srv/academic-dashboard
git switch main
git log -1 --oneline
```

The production files you will use:

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | PostgreSQL, Gunicorn backend, Nginx SPA; Nginx host port is loopback-only |
| `docker-compose.prod.yml` | Caddy TLS entry point and forced HTTPS environment for Django |
| `deploy/Caddyfile` | Automatic certificates, HTTP → HTTPS redirect, proxy and security headers |
| `frontend/nginx.conf` | SPA fallback, gzip, cache policy and Django proxy; forwards the original HTTPS scheme |
| `scripts/backup_db.sh` | Timestamped gzipped `pg_dump`, integrity check, 14-day retention |
| `Dockerfile.prod` | Gunicorn image; migrations run from `docker-entrypoint.sh` |
| `frontend/Dockerfile.prod` | Angular production build served by Nginx |

---

## 3. Configure production `.env`

Generate URL-safe database credentials (hex avoids `@`, `:` and `/` breaking
the `DATABASE_URL` Compose builds):

```bash
openssl rand -base64 48     # copy as SECRET_KEY
openssl rand -hex 24        # copy as POSTGRES_PASSWORD
```

Create the file:

```bash
cd /srv/academic-dashboard
cp .env.example .env
chmod 600 .env
nano .env
```

Use this as the production shape. Replace every `<...>` and do not keep the
example values:

```dotenv
DEBUG=False
SECRET_KEY=<paste the base64 value>
DJANGO_ALLOWED_HOSTS=school.example.edu.ng,127.0.0.1,localhost
FRONTEND_URL=https://school.example.edu.ng
CSRF_TRUSTED_ORIGINS=https://school.example.edu.ng

POSTGRES_DB=dashboard
POSTGRES_USER=dashboard
POSTGRES_PASSWORD=<paste the hex value>

# Bare hostname, no https:// and no trailing slash.
DOMAIN=school.example.edu.ng
NGINX_PORT=8080
SECURE_SSL_REDIRECT=True
SERVE_MEDIA=True

SCHOOL_NAME=<the school's real name>
DEFAULT_STUDENT_PASSWORD=<a non-public first-login password>

PAYSTACK_SECRET_KEY=sk_live_<...>
PAYSTACK_PUBLIC_KEY=pk_live_<...>
TERMII_API_KEY=<...>
TERMII_SENDER_ID=<approved sender ID>
WHATSAPP_ENABLED=False
```

Important:

- `.env` must remain `600` and must never be committed. The Docker ignore file
  keeps it out of the images.
- `DOMAIN`, `DJANGO_ALLOWED_HOSTS` and `FRONTEND_URL` must name the same host.
  `127.0.0.1` stays in `DJANGO_ALLOWED_HOSTS` so the backend container's health
  check works. If you also serve `www`, redirect it at DNS/Caddy or use the
  exact `www` host consistently.
- Backup settings (`BACKUP_DIR`, `BACKUP_RETENTION_DAYS`) belong to the host
  cron environment, not this application `.env`.
- Do **not** add `DATABASE_URL` to `.env` for the Compose stack; Compose builds it
  from the three `POSTGRES_*` values.
- Keep `PAYSTACK_SECRET_KEY` server-side. It must never reach Angular or a
  frontend image.

---

## 4. First deployment

From `/srv/academic-dashboard`, run the exact production command:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

For the rest of this runbook, export the same file pair once per shell so the
commands stay short:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
```

Check containers:

```bash
docker compose ps
```

Expected: `db` healthy, `backend` healthy, `nginx` healthy, `caddy` running.
If any service is restarting, stop here and read its logs before continuing:

```bash
docker compose logs --tail=100 db backend nginx caddy
```

Caddy obtains the certificate on first start and stores it in the `caddy_data`
volume. Watch issuance:

```bash
docker compose logs -f caddy
```

Look for a certificate obtained / served message. Common failures:

| Symptom | Check |
| --- | --- |
| `no such host` / challenge fails | `dig +short DOMAIN`; DNS may not have propagated |
| Connection refused on 80/443 | `sudo ufw status`; provider firewall/security group |
| Certificate issued but browser warns | DNS points elsewhere, or Cloudflare is proxying with Flexible SSL |
| `SECURE_SSL_REDIRECT` redirect loop | Nginx must forward `X-Forwarded-Proto`; confirm `frontend/nginx.conf` is the deployed version |

Migrations run automatically in the backend entrypoint. To run them explicitly
after a deploy:

```bash
docker compose exec backend python manage.py migrate --noinput
```

Create the school administrator:

```bash
docker compose exec backend python manage.py createsuperuser
```

Open `https://school.example.edu.ng/admin/` and:

1. Set the School profile: name, logo, contacts, current session and term.
2. Create teacher accounts and classes.
3. Confirm the current session/term is correct before entering results.
4. Do not leave demo accounts in a live school.

`seed_demo` is **only** for a pilot or demonstration. It creates sample students,
teachers and records:

```bash
# Optional demo data — never on a real school database.
docker compose exec backend python manage.py seed_demo
```

If you run it, record the generated credentials and remove the demo users before
going live.

---

## 5. Verify the deployment

Set the hostname in your shell first:

```bash
DOMAIN=school.example.edu.ng
```

### HTTP → HTTPS, health and app routes

```bash
curl -sS -o /dev/null -w 'HTTP  %{http_code} -> %{redirect_url}\n' "http://$DOMAIN/"
curl -sS -o /dev/null -w 'HTTPS %{http_code}\n' "https://$DOMAIN/"
curl -sS "https://$DOMAIN/api/health/"
curl -sS -o /dev/null -w 'ADMIN %{http_code}\n' "https://$DOMAIN/admin/"
curl -sS -o /dev/null -w 'DOCS  %{http_code}\n' "https://$DOMAIN/api/docs/"
```

Expected:

- HTTP returns `301` (or `308`) with a `https://...` redirect URL.
- HTTPS app returns `200`.
- `/api/health/` returns `{"status":"ok"}`.
- `/admin/` returns `302` to the login page (or `200` if already signed in).
- `/api/docs/` returns `200`.

### Certificate and HSTS

```bash
echo | openssl s_client -connect "$DOMAIN:443" -servername "$DOMAIN" 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates

curl -sSI "https://$DOMAIN/" | grep -i '^strict-transport-security'
```

The issuer should be a public CA (Let's Encrypt), the dates should be current,
and HSTS should be present. Caddy renews automatically; do not add certbot.

### Django production checks and secure cookies

```bash
docker compose exec backend python manage.py check --deploy --tag security
curl -sSI "https://$DOMAIN/admin/login/" | grep -i '^set-cookie'
```

The security-tagged deploy check should report no issues. The CSRF cookie should carry
`Secure`; after an admin login, the session cookie is also `Secure` and
`HttpOnly`.

### Paystack webhook over HTTPS

Set the Paystack dashboard webhook URL to:

```text
https://school.example.edu.ng/api/webhooks/paystack/
```

The endpoint must be reachable without authentication and must reject bad
signatures. This request should return **401**, not 404/502:

```bash
curl -sS -o /dev/null -w 'WEBHOOK %{http_code}\n' \
  -X POST "https://$DOMAIN/api/webhooks/paystack/" \
  -H 'Content-Type: application/json' \
  --data '{}'
```

Then make a real low-value payment through the parent/student fee flow and
confirm the ledger, payment history and receipt. A successful webhook is the
only thing that credits a fee. If it does not credit, check:

```bash
docker compose logs --tail=100 backend
```

The raw body must reach Django unchanged; Caddy and Nginx both pass it through.
Do not add a WAF rule or body parser that rewrites the Paystack payload.

**Termii:** this application sends SMS/WhatsApp outbound to Termii and has **no
inbound Termii callback endpoint**. There is therefore no Termii URL to register
for this app. Verify Termii by sending a test alert to an opted-in Nigerian
number and checking `GET /api/notifications/logs/` as a staff user.

### Real-device check

Open the site on an actual phone on mobile data (not school Wi-Fi), install the
PWA from the browser menu, sign in as a student, and check one result and one
offline reload. The 375 px table and touch-target work is only fully proven on a
real device.

---

## 6. Nightly database backups

A backup on the same disk is **not** disaster recovery. It protects against an
accidental delete or bad migration, not a lost VPS. Copy backups off the server.

Create the backup directory (owned by the deploy user, mode 700):

```bash
sudo install -d -m 700 -o deploy -g deploy /var/backups/academic-dashboard
```

Run one backup manually and inspect it:

```bash
cd /srv/academic-dashboard
BACKUP_DIR=/var/backups/academic-dashboard ./scripts/backup_db.sh
ls -lh /var/backups/academic-dashboard
latest=$(ls -1t /var/backups/academic-dashboard/academic-dashboard_*.sql.gz | head -1)
gzip -t "$latest" && echo "gzip OK: $latest"
```

The script:

- reads `POSTGRES_DB` from the running `db` container (one source of truth);
- runs `pg_dump --clean --if-exists` inside the container;
- writes to a `.partial` file first, checks the gzip stream, then renames it;
- writes a UTC timestamped `academic-dashboard_<db>_<timestamp>.sql.gz`;
- keeps files mode `600` and deletes dumps older than `BACKUP_RETENTION_DAYS`
  (default 14).

### Cron

Create `/etc/cron.d/academic-dashboard-backup`:

```bash
sudo tee /etc/cron.d/academic-dashboard-backup >/dev/null <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 2 * * * deploy cd /srv/academic-dashboard && BACKUP_DIR=/var/backups/academic-dashboard /usr/bin/flock -n /var/backups/academic-dashboard/.backup.lock ./scripts/backup_db.sh >> /var/backups/academic-dashboard/backup.log 2>&1
CRON
sudo chmod 644 /etc/cron.d/academic-dashboard-backup
```

The job runs as `deploy` (which is in the `docker` group) so the `600` dump
files and the log remain readable by the same user who performs restores.
`flock -n` prevents overlapping runs. Check the first scheduled result the next
morning:

```bash
sudo tail -n 20 /var/backups/academic-dashboard/backup.log
sudo ls -lh /var/backups/academic-dashboard
```

### Off-server copy

Install `rclone`, configure an S3/Backblaze/remote destination, and mirror the
directory after the local backup:

```bash
sudo apt install -y rclone
rclone config          # one-time interactive setup
rclone sync /var/backups/academic-dashboard remote:academic-dashboard-backups
```

Add a second cron entry for `03:00` once the manual sync works. Because `rclone
sync` mirrors the source, the 14-day local retention also applies remotely. Test
a restore from the **remote** copy, not just the local one.

Uploads live in the `academic-dashboard_media` Docker volume, not in PostgreSQL.
If assignment files matter for your school, back that volume up too:

```bash
docker run --rm \
  -v academic-dashboard_media:/data:ro \
  -v /var/backups/academic-dashboard:/backup \
  alpine tar czf "/backup/media_$(date -u +%Y%m%dT%H%M%SZ).tar.gz" -C /data .
```

### Restore procedure

A backup is only real once you have restored it. Read this entire section before
running it. The commands below **replace the live database**; take a fresh
backup first.

```bash
cd /srv/academic-dashboard
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
BACKUP=/var/backups/academic-dashboard/academic-dashboard_dashboard_YYYYMMDDTHHMMSSZ.sql.gz

# 1. Verify the archive before touching anything.
gzip -t "$BACKUP" && echo "archive OK"

# 2. Take a safety backup of the current database.
BACKUP_DIR=/var/backups/academic-dashboard ./scripts/backup_db.sh

# 3. Stop public traffic and the app, leaving PostgreSQL running.
docker compose stop caddy nginx backend

# 4. Recreate an empty database owned by the app user.
docker compose exec -T db sh -c 'dropdb --force -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'

# 5. Restore. ON_ERROR_STOP makes a partial restore fail loudly.
gunzip -c "$BACKUP" | docker compose exec -T db sh -c \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

# 6. Bring the app back.
docker compose start backend nginx caddy
docker compose ps
curl -fsS "https://school.example.edu.ng/api/health/"
```

Sign in as the administrator and spot-check a class roster, a published result
and the fee ledger. If the restore fails, do **not** keep retrying against the
live database: leave the app stopped and restore the safety backup from step 2.

### Monthly restore drill (without touching production)

Restore into a scratch database and count real rows:

```bash
cd /srv/academic-dashboard
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
BACKUP=/var/backups/academic-dashboard/academic-dashboard_dashboard_YYYYMMDDTHHMMSSZ.sql.gz

docker compose exec -T db sh -c \
  'dropdb --if-exists -U "$POSTGRES_USER" restore_check && createdb -U "$POSTGRES_USER" restore_check'
gunzip -c "$BACKUP" | docker compose exec -T db sh -c \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d restore_check'
docker compose exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d restore_check -c "select count(*) from auth_user;"'
docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" restore_check'
```

A restore drill that fails is a release blocker. Fix it before the school relies
on the system.

---

## 7. Routine operations and upgrades

```bash
cd /srv/academic-dashboard
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml

docker compose ps
docker compose logs -f --tail=100 caddy nginx backend
docker compose restart backend
df -h
```

Upgrade flow:

```bash
# Back up before every upgrade.
BACKUP_DIR=/var/backups/academic-dashboard ./scripts/backup_db.sh

git pull --ff-only
docker compose up --build -d
docker compose ps
curl -fsS https://school.example.edu.ng/api/health/
```

Migrations run automatically. If a migration needs a rollback, restore the
pre-upgrade database backup; migrations are not automatically reversible.

Never run `docker compose down -v` on production. It deletes the PostgreSQL and
media volumes. `docker compose down` without `-v` keeps data but is unnecessary
for a normal deploy.

Certificate renewal is automatic; the `caddy_data` volume must persist. Do not
delete it. To change the domain, update DNS, `DOMAIN` and `.env`, then recreate
Caddy; old certificates remain in the volume harmlessly.

---

## 8. Going-live checklist

### Server and TLS

- [ ] DNS `A`/`AAAA` records resolve to the VPS.
- [ ] Only ports 22, 80 and 443 are publicly reachable.
- [ ] `docker compose ps` shows db/backend/nginx healthy and caddy running.
- [ ] `http://DOMAIN/` redirects to `https://DOMAIN/`.
- [ ] HTTPS certificate is valid, public and not near expiry.
- [ ] HSTS header present; no redirect loop.
- [ ] `python manage.py check --deploy --tag security` reports no issues.

### Application and secrets

- [ ] `.env` is mode `600`, has a real `SECRET_KEY`, real DB password and no
      example/default values.
- [ ] `seed_demo` was not run on the real school, or all demo users/data are
      removed.
- [ ] Administrator password is strong and stored in the school's password
      manager.
- [ ] School name, logo, current session and current term are correct.
- [ ] Real classes, subjects and teacher accounts exist and are scoped
      correctly.
- [ ] `DEFAULT_STUDENT_PASSWORD` is not the example value.

### Payments and messaging

- [ ] Paystack is in **live** mode; keys start with `sk_live_`/`pk_live_`.
- [ ] Paystack webhook URL is `https://DOMAIN/api/webhooks/paystack/`.
- [ ] An unsigned webhook POST returns `401`, not 404/502.
- [ ] A real low-value fee payment credits the ledger and produces a receipt.
- [ ] Termii Sender ID is approved; a test SMS reaches an opted-in parent.
- [ ] Notification logs show the delivery result.
- [ ] WhatsApp is enabled only if its device and template are approved.

### Backups and devices

- [ ] A manual backup exists, `gzip -t` passes, and the file is mode `600`.
- [ ] Nightly cron has run at least once and the log is clean.
- [ ] A backup has been copied off the VPS.
- [ ] A monthly restore drill has succeeded, including a row count.
- [ ] Real 375 px phone test on mobile data: login, results, fee page, offline
      reload, PWA install.
- [ ] The school knows who to call and how to report an outage.

---

## 9. Owner-only actions (cannot be done from the codebase)

These require accounts, money or physical access:

1. Buy/control the domain and edit its DNS.
2. Rent/provision the VPS and install your SSH key.
3. Open ports 80/443 at the provider firewall and point DNS at the server.
4. Create the Paystack business, complete KYC, activate live mode, and obtain
   live keys; add the webhook URL in the Paystack dashboard.
5. Register the Termii account, get the Sender ID approved, and provide the API
   token; approve WhatsApp templates if used.
6. Put the real `.env` secrets on the server (never in chat, Git or a frontend
   image).
7. Decide the administrator and student first-login passwords.
8. Test on a real phone and with a real low-value payment.
9. Arrange off-site backup storage and periodically restore from it.
10. Monitor the server, renew the domain, and keep the OS/Docker patched.
