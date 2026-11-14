# Roadmap

Where the project stands and what comes next. Check items off as they land; keep the ordering — the
top section is the agreed next work.

## Done

Backend (school pivot, headless JSON API)

- [x] `AcademicSession` / `Term` with current flags, `Term.current()`
- [x] `SchoolClass` (capacity 10–50, `can_manage`), `Subject`, `Profile` extensions
- [x] `Result` with CA1+CA2+CA3+Exam = /100, WAEC grades and remarks computed on save
- [x] `LessonNote`, `Announcement`, `Assignment`/`Submission`, `Attendance`, `Schedule`
- [x] `Publishable` draft/published/archived on all four content types
- [x] Queryset-level visibility: students only see published rows for their own class
- [x] JWT auth, `/api/me/`, forced first-login password change
- [x] CSV student onboarding with capacity checks and default password
- [x] Headless cleanup: templates, forms, chat, static assets and channels removed
- [x] Django admin as the school-office control panel
- [x] Migrations 0017 (pivot) and 0018 (legacy rows)
- [x] `seed_demo` (teacher, class, students, two terms of results, notes, work, register)
- [x] 79-test pytest suite, ruff + mypy clean
- [x] JWT authentication ordered ahead of session auth so an admin cookie cannot override a token

Frontend (Angular 22 SPA)

- [x] Core: typed models, auth service, API service with pagination unwrapping, guards, lazy routes
- [x] Auth screens: admission-number login, forced password change
- [x] Student portal: dashboard, results (term selector), notes, assignments (upload), attendance, notices
- [x] Teacher portal: dashboard, roster + CSV import, results entry with term/subject and publishing,
      notes, assignments with per-row marking link, submissions grading, notices, attendance
- [x] Broadsheet page, announcements editing, lesson-note attachments, upload validation
- [x] Role-aware shell, budgeted low-bandwidth build (~304 kB initial / ~85 kB transfer)

Version 1.4 — school branding, Excel exports and the bursar's dashboard

- [x] `School` profile (name, motto, address, contacts, logo, current session/term), editable in admin
- [x] Report-card masthead, login page and portal sidebar render the school's name, logo and motto
- [x] `?format=xlsx` broadsheet export: subjects, totals, averages, positions and class-average row
- [x] Fee ledger export and JSON view for every student, including classes with no fee configured
- [x] Staff-only finance summary and paginated debtors list with guardian phone contacts
- [x] Finance dashboard in the SPA (summary cards, searchable debtors, ledger download)
- [x] 23 tests for finance maths, debtors, Excel workbooks and branding

Version 1.3 — real Termii delivery and password recovery

- [x] Termii transactional SMS adapter (`api.ng.termii.com/api/sms/send`, `channel=dnd`, 10s timeout)
- [x] Nigerian phone normalization and pre-send validation, error details retained in notification log
- [x] WhatsApp remains off by default; device and approved template ID are required before send
- [x] Teacher-class / staff student password reset and staff-only ward reset route
- [x] One-time temporary password display and copy control in teacher class roster
- [x] Termii payload, phone format, timeout, failure and reset permission tests
- [ ] Sender ID approval, account DND enablement and real-device SMS delivery check

Version 1.2 — automated parent notifications

- [x] `NotificationLog` (recipient, channel, event, payload, status, external id) and `Profile.phone_number`
- [x] Provider-agnostic service with a console `MockProvider`; Termii/Twilio is a one-function swap
- [x] Signal triggers: absent attendance, successful payment receipt, published result (once per term)
- [x] Dedupe so a re-saved register or replayed webhook does not spam parents
- [x] Missing phone/email and provider outages are skipped or recorded, never raised to the caller
- [x] `GET /api/notifications/logs/` delivery dashboard for staff, plus admin history
- [x] 19 new tests for the service, triggers, dedupe and delivery rates

Version 1.1 — parent portal and school fees

- [x] `parent` role on `Profile`, `ParentStudentLink` for one parent → many wards
- [x] `Fee` per class level/session/term, `StudentFee` with derived balance and paid/partial/unpaid status
- [x] `Payment` records with Paystack reference, amount, status and paid time
- [x] `POST /api/payments/initialize/` → Paystack checkout URL (part payments allowed, balance enforced)
- [x] `POST /api/webhooks/paystack/` with HMAC SHA512 signature check, CSRF-exempt, idempotent replay
- [x] Parent portal routes: dashboard with ward averages/attendance, ward report cards, fees and history
- [x] Report cards opened to linked parents, not just students, teachers and staff
- [x] Admin screens for links, fees, student fees and payments; demo parent in `seed_demo`
- [x] 30 tests covering ward scoping, fee maths, initialisation and webhook signatures

Version 1.0 wrap-up

- [x] Installable PWA: `@angular/pwa`, app-shell/font/icon caching, offline fallback for deep links
- [x] Cache-first data group for `GET /api/**` (1 day, 200 entries) plus a data-cache purge on sign-out
- [x] Generated, project-branded install icons (`frontend/scripts/generate-icons.mjs`)
- [x] `Dockerfile.prod`: Gunicorn, collected static files, non-root user, healthcheck, migrations on start
- [x] Nginx service serving the compiled SPA at `/` and proxying `/api/`, `/admin/`, `/static/`, `/media/`
- [x] `docker compose` stack with PostgreSQL, media volume and production env defaults
- [x] README production runbook and environment reference

## Next: Nigerian school essentials

### A. End-of-term report cards

The printable document parents expect at the end of term.

- [x] `GET /api/students/{id}/report-card/?session=&term=` returning student name, admission number,
      class, session, term, per-subject CA1/CA2/CA3/CA total/exam/total/grade/remark (the new
      `Result.teacher_remark`, falling back to the grade remark) and the per-subject class average.
- [x] Overall total, overall average, and **position in class** ("3rd out of 45 students") computed
      from the ranked averages of every student with published results. Ties share a position; drafts
      are excluded.
- [x] Server-rendered print-optimised HTML with `@media print` and an A4 `@page` rule, so the browser
      saves it as a PDF without a server-side PDF toolchain (no Cairo/Pango/WeasyPrint). Sections for
      the affective and psychomotor domains, class teacher's remark, principal's remark, next term
      fees and resumption date.
- [x] Frontend: "Print / save PDF" on the student results page prints the card from a hidden frame
      (a popup window is blocked after an async fetch).
- [x] Tests: position ordering, tie handling, excluded drafts, class average maths, permissions.
- [ ] A per-student report card action on the teacher broadsheet roster.
- [ ] Optional: fill the affective/psychomotor ratings and remark boxes from stored values.

### B. Broadsheet (teacher analytics view)

- [x] `GET /api/classes/{id}/broadsheet/?session=&term=` returning students × subjects totals, each
      student's average and position, and per-subject class averages (plus subject order).
- [x] Frontend page `/teacher/broadsheet`: class/term selectors, student rows with subject totals,
      total/average/position columns and a class-average footer row.
- [x] Only published results feed the broadsheet, in the same way report cards do.
- [x] Tests: grid shape, averages, positions, drafts, permissions, empty class/term behaviour.
- [ ] CSV export of the grid itself, and a sticky student column on narrow screens.

### C. Bulk result upload (CSV)

- [x] `GET /api/classes/{id}/results/template/?session=&term=` returning the blank CSV
      `Admission Number, Subject, CA1, CA2, CA3, Exam` as a download.
- [x] `POST /api/classes/{id}/results/bulk-import/?session=&term=` with per-row validation (class
      membership, subject ownership, CA/exam caps, whole numbers), create-or-update, new rows kept as
      drafts, row-level error report, and class ownership checked like every other write.
- [x] Frontend: "Download CSV template" and "Upload CSV" on the broadsheet page, with the import
      report (created / updated / errors by row) displayed as an alert panel.
- [x] Tests: happy path, over-cap rows, unknown students, duplicate rows, foreign subject, other class,
      session mismatch, and updates that do not unpublish a result.

### D. UI/UX gaps to close

- [x] Teacher announcement editing (title, body, audience, status) — publishing and archiving still exist.
- [x] Lesson-note attachment upload in the teacher UI (multipart with the rest of the note fields).
- [x] Frontend file validation: PDF/DOC/DOCX/PNG/JPG only, 5 MB ceiling, with readable messages on
      assignment submissions, lesson-note attachments and CSV uploads.
- [ ] Backend file validation: the same type and size rules enforced in the serializers.
- [ ] Confirm student submission upload and note attachment work in a real browser session (file
      pickers cannot be driven from the automated preview).

## Backlog (later)

- [ ] Class analytics: subject averages, pass rate, grade distribution, weakest topics
- [ ] Student password reset by the class teacher (currently admin-only)
- [ ] Message/feedback thread between student and teacher per submission
- [ ] Submission delete/re-upload before marking
- [ ] Attendance history per student for teachers, and term attendance on the report card
- [ ] Result-sheet PDF for a whole class (broadsheet print)
- [ ] Frontend CI job (build already wired) plus a smoke test of login and one portal page
- [ ] Move uploads to object storage (S3/R2) and turn `SERVE_MEDIA` off
- [ ] Background refresh of cached data when the app comes back online
- [ ] Payment receipts by email/SMS and a printable fee receipt
- [ ] Fee reminders to parents before the term's deadline
- [ ] Whole-school finance report (billed, collected, outstanding per term)
- [ ] Parent-teacher message thread
- [ ] Termii/Twilio provider implementation and phone verification (OTP)
- [ ] Notification preferences per parent and quiet hours

## Ground rules

- The publishing rule stays in the queryset, not the client: students never receive drafts.
- Every new endpoint ships with tests; `pytest`, `ruff check`, `mypy` and `ng build` stay green.
- Keep the initial bundle under the 320 kB warning budget (currently ~304 kB).
- New teacher pages follow the existing inline-template + `styles.scss` design system.
