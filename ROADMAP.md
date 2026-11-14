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
- [x] Role-aware shell, budgeted low-bandwidth build (~297 kB initial / ~83 kB transfer)

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
- [ ] PWA/offline caching for low-bandwidth users
- [ ] Frontend CI job (build already wired) plus a smoke test of login and one portal page
- [ ] Deployment runbook (Daphne + PostgreSQL + static/media storage)

## Ground rules

- The publishing rule stays in the queryset, not the client: students never receive drafts.
- Every new endpoint ships with tests; `pytest`, `ruff check`, `mypy` and `ng build` stay green.
- Keep the initial bundle under the 320 kB warning budget (currently ~297 kB).
- New teacher pages follow the existing inline-template + `styles.scss` design system.
