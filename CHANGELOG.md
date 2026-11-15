# Changelog

All notable changes to AcademicHub are recorded here. The project follows
[Semantic Versioning](https://semver.org/) for customer-facing releases.

## [1.0.0] - 2026-11-15 - Initial Release

### Added

- Multi-portal school management for teachers, students, parents and school
  office staff, with role-scoped navigation and APIs.
- Academic sessions, terms, classes, subjects, student rosters and CSV student
  onboarding, including forced first-login password changes.
- WAEC-style result entry and computation: CA1, CA2, CA3, Exam, A–F grades,
  positions with tie handling, class averages and publish/archive controls.
- Broadsheets with Excel export, CSV result templates, bulk result import with
  row-level validation, and print-ready branded report cards.
- Fee setup by class level, Paystack checkout, signature-verified payment
  webhooks, automatic receipts, balances and a staff-only debtor/ledger view.
- Termii SMS and optional WhatsApp notifications for absences, successful
  payments and published results, with delivery logs.
- Attendance register, lesson notes, assignments and submissions, announcements,
  learning resources, student progress, and timed CBT quizzes.
- Installable Angular PWA with read-only offline access to cached content.
- Mobile-first UI polish: 375 px layouts, sticky table headers and columns,
  44 px touch targets, numeric score-entry keypads, focus rings and non-colour
  status markers.
- Production stack with PostgreSQL, Gunicorn, Nginx, Docker Compose and Caddy
  automatic HTTPS, plus HTTP → HTTPS redirect and secure-cookie/HSTS hardening.
- Nightly verified PostgreSQL backups with 14-day retention, cron example,
  off-site copy guidance and a rehearsed restore procedure.
- CI quality gates for Ruff, mypy, Django checks, migrations, pytest and the
  Angular production bundle.
- Commercial deployment runbook, environment templates, screenshot placeholders
  and this changelog.

### Security

- Removed fallback application and database secrets from settings and Compose;
  production values must now be supplied through the environment.
- CI and image builds generate ephemeral secrets instead of embedding fixed
  values.
- Paystack webhooks are authenticated with HMAC SHA-512 over the raw body and
  are idempotent per reference.
- Login throttling, JWT authentication, role-scoped querysets and HTTPS-only
  cookies are enabled in production.

[1.0.0]: https://github.com/cn108/academic_dashboard/releases/tag/v1.0.0