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

### A. End-of-term report cards (PDF)

The printable document parents expect at the end of term.

- [ ] `GET /api/reports/report-card/?student=&session=&term=` (or `/api/results/report-card/`) returning
      student name, admission number, class, session, term, per-subject CA1/CA2/CA3/CA total/exam/total/
      grade/remark, and per-subject class average.
- [ ] Overall total, overall average, and **position in class** ("3rd of 45") computed from the ranked
      averages of every student with published results in that class, session and term. Ties share a
      position; ranking only counts published rows.
- [ ] Server-rendered PDF generated on the backend (no client-side PDF library) and downloadable by the
      student for themselves; teachers/prinicpals can fetch any student in their class.
- [ ] Frontend: "Report card" button on the student results page and a per-student action on the teacher
      roster/broadsheet; downloads the PDF.
- [ ] Tests: position ordering, tie handling, excluded drafts, class average maths, permission scoping.

### B. Broadsheet (teacher analytics view)

- [ ] `GET /api/reports/broadsheet/?class=&session=&term=` returning students × subjects totals, each
      student's average, position, and per-subject class average (plus subject order).
- [ ] Frontend page `/teacher/broadsheet`: class/term selectors, sticky first column, colour-coded totals,
      average and position columns, CSV export of the same grid.
- [ ] Only published results feed the broadsheet in the same way report cards do.
- [ ] Tests: grid shape, averages, positions, empty class/term behaviour.

### C. Bulk result upload (CSV/Excel)

- [ ] `GET /api/results/template/?class=&subject=&session=&term=` returning a CSV with the roster
      (admission number, name) and CA1/CA2/CA3/Exam columns plus a header row documenting the caps.
- [ ] `POST /api/results/import/` accepting that CSV for a class/subject/session/term: per-row validation
      (known admission number, caps per column), create-or-update, and a report of created/updated/skipped
      rows with reasons. Capacity and ownership checked like every other write.
- [ ] Frontend: "Download template" and "Upload CSV" on the results page, showing the import report.
- [ ] Tests: happy path, over-cap rows, unknown students, duplicate rows, other class rejected.

### D. UI/UX gaps to close

- [ ] Teacher announcement editing (edit title, body, audience, then save) — publishing and archiving exist.
- [ ] Lesson-note attachment upload in the teacher UI (backend already accepts `attachment`).
- [ ] File validation end to end: allowed types (PDF, DOC/DOCX, images) and a size ceiling enforced in
      the serializers as well as the browser, with a readable error message.
- [ ] Confirm student submission upload and note attachment work in a browser, not just the API.

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
