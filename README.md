# AcademicHub - Complete School Management System for Nigerian Schools

[![Build Status](https://github.com/cn108/academic_dashboard/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/cn108/academic_dashboard/actions/workflows/ci.yml)
[![264 Tests](https://img.shields.io/badge/tests-264%20passing-brightgreen)](https://github.com/cn108/academic_dashboard/actions/workflows/ci.yml)
[![Deploy Ready](https://img.shields.io/badge/deploy-ready-brightgreen)](DEPLOYMENT.md)

**One connected school system that turns WAEC grading, Paystack fee collection and Termii SMS/WhatsApp parent alerts into a mobile-first workflow Nigerian schools can run on a modest server.**

AcademicHub is built around the realities of a Nigerian school: end-of-term positions, report cards, fee reconciliation, unreliable mobile data, and parents who need to hear from the school without downloading another app.

---

## Why Schools Choose Us (Business Value)

- 📊 **Automated Result Computation** — WAEC-style CA1, CA2, CA3 and Exam totals, A–F grades, class positions with correct tie handling, whole-class broadsheets and one-click Excel export. Teachers stop rebuilding result sheets in spreadsheets.
- 💰 **Integrated Fee Collection** — Paystack checkout, verified webhook crediting, automatic receipts, outstanding balances, class-level fees, debtor tracking and a staff-only ledger. The office sees one source of truth instead of several notebooks.
- 📱 **Mobile-First & Offline PWA** — designed for 375 px screens and low-bandwidth connections. The production initial bundle transfers at about 88 kB gzipped, and published content remains readable offline. No app-store download is required.
- 👥 **Multi-Portal System** — separate, permission-scoped experiences for teachers, students and parents, plus a finance view for school office staff. Everyone sees only what their role allows.
- 🔔 **Automated Communication** — Termii SMS/WhatsApp alerts for absences, successful fee payments and published results, with delivery logs staff can inspect. Parents hear from the school without a teacher typing every message.
- 📄 **Professional Report Cards** — print-ready A4 report cards with the school's name and branding, subject averages, overall position, affective and psychomotor domains, teacher remarks and next-term details. Browsers can save them as PDF without a server-side PDF toolchain.
- 📚 **Learning Management** — lesson notes and resources, assignment submission and grading, video/resource completion tracking, timed CBT quizzes and a student progress dashboard. Teaching continues between lessons.

One deployment serves one school. Schools do not share a database, domain or administrator account.

## Screenshots

Replace these placeholders with production screenshots using the exact filenames below. Capture clean demo data only; never include real student names, phone numbers or payment details. See [`docs/screenshots/README.md`](docs/screenshots/README.md) for capture guidance.

| Screen | File | What it should show |
| --- | --- | --- |
| Student dashboard | `docs/screenshots/student-dashboard.png` | Published results summary, current term, upcoming work and attendance |
| Teacher dashboard | `docs/screenshots/teacher-dashboard.png` | Class overview, result/attendance actions and recent activity |
| Parent dashboard | `docs/screenshots/parent-dashboard.png` | Linked wards, fees, attendance and result access |
| Report card | `docs/screenshots/report-card.png` | Print preview with school branding, grades and position |
| Broadsheet | `docs/screenshots/broadsheet.png` | Class × subject totals, averages and positions with the Excel action |

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, Django 5, Django REST Framework, SimpleJWT, drf-spectacular |
| Database | PostgreSQL 16 in production; SQLite for local development |
| Frontend | Angular 22, TypeScript, SCSS, Angular Service Worker (PWA) |
| Infrastructure | Docker, Docker Compose, Caddy 2 (automatic HTTPS), Nginx, Gunicorn |
| Integrations | Paystack (fees and signed webhooks), Termii (SMS/WhatsApp) |
| Quality | pytest, Ruff, mypy, Angular production build and bundle budgets |

## Quick Start (Development)

### Option A: Docker Compose

Prerequisites: Docker Desktop or Docker Engine with the Compose plugin.

```bash
cp .env.example .env
# Set SECRET_KEY and POSTGRES_PASSWORD in .env before the first build.
docker compose up --build -d
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py seed_demo
```

Open <http://localhost:8080/>. The Nginx port is loopback-only; Caddy is only used by the production overlay.

`seed_demo` creates a demo class and prints the generated teacher and parent credentials. The student roster uses `DEFAULT_STUDENT_PASSWORD` from `.env`; students are forced to change it at first login. Never run `seed_demo` on a real school database.

Stop the stack with `docker compose down`. Do not use `down -v` unless you intend to delete the database and uploads.

### Option B: Manual Setup

Prerequisites: Python 3.12+, Node 22+ and npm 11+.

```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

In a second terminal:

```bash
cd frontend
npm ci
npm start
```

The SPA runs at <http://localhost:4200/> and proxies `/api/` to Django at port 8000. The manual path uses SQLite by default; set `DATABASE_URL` for PostgreSQL if needed. If you test Paystack callbacks manually, set `FRONTEND_URL=http://localhost:4200` in `.env`.

## Production Deployment

The complete, copy-pasteable runbook is **[DEPLOYMENT.md](DEPLOYMENT.md)**. It covers a fresh Ubuntu VPS, DNS, production secrets, Caddy certificate issuance, migrations, webhook verification and a rehearsed restore.

Production highlights:

- **Caddy automatic HTTPS** — Let's Encrypt certificates, automatic renewal, HTTP → HTTPS redirect and HSTS. Nginx stays on `127.0.0.1:8080`; Django trusts the forwarded HTTPS scheme.
- **One command deploy** — `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d`.
- **Nightly backups** — `scripts/backup_db.sh` writes verified, timestamped `pg_dump` archives and retains 14 days by default.
- **Off-site backup and restore drill** — documented explicitly, because a backup that cannot be restored is not a backup.

Copy [`.env.production.example`](.env.production.example) to `.env` on the server, fill it, and lock it down:

```bash
cp .env.production.example .env
chmod 600 .env
```

Example nightly cron entry (run as the deploy user):

```cron
0 2 * * * deploy cd /srv/academic-dashboard && BACKUP_DIR=/var/backups/academic-dashboard /usr/bin/flock -n /var/backups/academic-dashboard/.backup.lock ./scripts/backup_db.sh >> /var/backups/academic-dashboard/backup.log 2>&1
```

## API Documentation

- Interactive **Swagger UI**: <http://localhost:8000/api/docs/>
- OpenAPI 3 schema: `GET /api/schema/` (ReDoc- and client-generator-compatible)
- Authentication: JWT via `POST /api/token/`; send `Authorization: Bearer <access>` on API calls.

Key endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/classes/{id}/broadsheet/?session=&term=` | Whole-class results matrix with totals, averages and positions; add `&format=xlsx` for Excel |
| `POST /api/classes/{id}/results/bulk-import/` | CSV/JSON result import with row-level validation feedback |
| `GET /api/students/{id}/report-card/` | Print-ready report card for a student |
| `POST /api/payments/initialize/` | Start a Paystack checkout for a student fee balance |
| `POST /api/webhooks/paystack/` | Signature-verified, idempotent payment webhook |

## Testing

The release gate is 264 passing backend tests plus a production Angular build:

```bash
pytest
ruff check . && ruff format --check .
mypy core academic_dashboard
python manage.py check --deploy --tag security
cd frontend && npm run build     # runs ng build
```

Current production build: **318 kB raw initial / ≈88 kB transfer**, within the 400 kB warning budget. The frontend also enforces a 500 kB error ceiling.

## Project Structure

```text
academic_dashboard/        Django settings, ASGI/WSGI entry points and root URLs
core/
  models.py               Sessions, terms, classes, subjects, results, fees, quizzes, resources
  views.py                Role-scoped API viewsets, finance views and report endpoints
  serializers.py          API validation and representations
  permissions.py          Teacher/staff/student access rules
  reports.py              Broadsheet, position and report-card calculations
  exports.py              Excel workbooks for broadsheets and fee ledgers
  parents.py              Parent portal and Paystack webhook
  notifications.py        Termii SMS/WhatsApp delivery and signal triggers
  learning.py             Lesson resources and student progress
  quizzes.py              Timed CBT quiz engine
  templates/reports/      Print-ready report-card HTML
  migrations/             Versioned database schema
tests/                    Pytest suite (models, API, finance, reports, notifications, quizzes)
frontend/
  src/app/pages/          Teacher, student, parent and staff portals
  src/app/core/           Auth, API client, guards, printing and shared services
  src/styles.scss         Responsive, table, touch-target and accessibility styles
  public/                 PWA manifest and application icons
  nginx.conf              SPA fallback, caching and Django reverse proxy
  Dockerfile.prod         Angular build served by Nginx
deploy/
  Caddyfile               Automatic TLS, HTTP redirect, proxy and security headers
scripts/
  backup_db.sh            Compressed PostgreSQL dump with retention
docs/
  screenshots/            Product screenshots used by this README
docker-compose.yml        Local production-style stack (Postgres, backend, Nginx)
docker-compose.prod.yml   Public Caddy TLS overlay
.env.example              Local development template
.env.production.example   Production secrets and host template
DEPLOYMENT.md             Full VPS deployment and restore runbook
CHANGELOG.md              Release history
```

## License & Contact

**Proprietary software.** Copyright © 2026 AcademicHub. All rights reserved. No part of this repository may be copied, redistributed, sublicensed, sold or offered as a hosted service without prior written permission. Access to the source code does not grant a license to operate it for third parties.

For a guided demo, school pilot or commercial licensing:

- **Email:** `hello@academichub.example` *(replace with your sales address)*
- **Phone/WhatsApp:** `+234 XXX XXX XXXX` *(replace with your business number)*
- **Demo request:** include the school name, number of students, current term and whether the school uses Paystack or manual fee collection.