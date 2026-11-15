# Product screenshots

The README embeds three screenshots captured from the running seeded demo:

| File | Screen | Status |
| --- | --- | --- |
| `student-dashboard.png` | Student dashboard | Captured |
| `teacher-dashboard.png` | Teacher dashboard | Captured |
| `broadsheet.png` | Teacher broadsheet | Captured |
| `parent-dashboard.png` | Parent dashboard | Pending capture |
| `report-card.png` | Report-card print preview | Pending capture |

Parent dashboard and report-card images are not included yet; add them after
capturing the real views from the demo environment. Recommended filenames:
`parent-dashboard.png` and `report-card.png`. The current browser session could
render these views, but the screenshot capture surface did not draw the parent
portal and the report-card print action stalled, so those images are deliberately
not represented by mockups.

## Capture rules

- Use the demo school only. Remove real student names, guardian phone numbers,
  payment references and anything that identifies a real child.
- Use a clean browser window at 1440 × 1000, normal zoom, with no personal
  bookmarks or extensions visible.
- Keep amounts, grades and positions realistic; do not stage implausible data.
- Crop browser chrome if the screenshot is going into a pitch deck; keep the
  school branding visible in the report card.
- Export PNG (not JPEG) and optimise files to under ~600 kB each.
- Keep images under `docs/screenshots/` and update the README image links when adding new captures.

For the commercial site, a matching 375 px mobile screenshot of the student
results table is also useful; add it as `student-results-mobile.png` and link it
from the README if you want it displayed.