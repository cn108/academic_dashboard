import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import {
  Announcement,
  Assignment,
  AttendanceSummary,
  LessonNote,
  Result,
  SchoolClass,
  Subject,
} from '../../core/models';

@Component({
  selector: 'app-teacher-dashboard',
  imports: [RouterLink],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">{{ schoolClass()?.name || 'Teacher portal' }}</p>
        <h1>Welcome, {{ firstName() }}</h1>
        <p class="muted small">
          {{ schoolClass()?.student_count || 0 }} students · capacity {{ schoolClass()?.capacity || 50 }}
        </p>
      </div>
      <div class="row-actions">
        <a class="btn btn-ghost" routerLink="/teacher/attendance">Take attendance</a>
        <a class="btn" routerLink="/teacher/results">Enter results</a>
      </div>
    </div>

    <div class="grid grid-4" style="margin-bottom: 1.25rem">
      <div class="stat">
        <p class="muted small">Students</p>
        <p class="value">{{ schoolClass()?.student_count || 0 }}</p>
      </div>
      <div class="stat">
        <p class="muted small">Drafts waiting</p>
        <p class="value">{{ draftCount() }}</p>
      </div>
      <div class="stat">
        <p class="muted small">Published results</p>
        <p class="value">{{ publishedResults() }}</p>
      </div>
      <div class="stat">
        <p class="muted small">Attendance</p>
        <p class="value">{{ attendanceRate() }}%</p>
      </div>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-head">
          <h2 style="font-size: 1rem">My subjects</h2>
          <a class="small" routerLink="/teacher/class">Class roster</a>
        </div>
        @if (subjects().length) {
          <div class="grid">
            @for (subject of subjects(); track subject.id) {
              <div style="display: flex; justify-content: space-between; gap: 0.75rem">
                <span>{{ subject.name }}</span>
                <span class="small muted">{{ subject.class_name }}</span>
              </div>
            }
          </div>
        } @else {
          <p class="empty">No subjects assigned yet. Ask the school office.</p>
        }
      </div>

      <div class="grid">
        <div class="card">
          <div class="card-head">
            <h2 style="font-size: 1rem">Drafts not yet published</h2>
          </div>
          @if (drafts().length) {
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Type</th>
                  </tr>
                </thead>
                <tbody>
                  @for (draft of drafts(); track draft.label + draft.id) {
                    <tr>
                      <td>{{ draft.label }}</td>
                      <td class="muted">{{ draft.type }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          } @else {
            <p class="empty">Everything you own is published.</p>
          }
        </div>

        <div class="card">
          <div class="card-head">
            <h2 style="font-size: 1rem">Recent activity</h2>
          </div>
          <div class="grid">
            <div style="display: flex; justify-content: space-between">
              <span>Lesson notes</span><span class="badge badge-info">{{ notes().length }}</span>
            </div>
            <div style="display: flex; justify-content: space-between">
              <span>Assignments</span><span class="badge badge-info">{{ assignments().length }}</span>
            </div>
            <div style="display: flex; justify-content: space-between">
              <span>Announcements</span><span class="badge badge-info">{{ announcements().length }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
})
export class TeacherDashboard {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);

  readonly user = this.auth.user;
  readonly schoolClass = signal<SchoolClass | null>(null);
  readonly subjects = signal<Subject[]>([]);
  readonly results = signal<Result[]>([]);
  readonly notes = signal<LessonNote[]>([]);
  readonly assignments = signal<Assignment[]>([]);
  readonly announcements = signal<Announcement[]>([]);
  readonly attendance = signal<AttendanceSummary[]>([]);

  readonly firstName = computed(() => (this.user()?.name ?? 'teacher').split(' ')[0]);
  readonly publishedResults = computed(
    () => this.results().filter((row) => row.status === 'published').length,
  );
  readonly drafts = computed(() => {
    const rows: { id: number; label: string; type: string }[] = [];
    for (const result of this.results()) {
      if (result.status === 'draft') {
        rows.push({
          id: result.id,
          label: `${result.student_name} · ${result.subject_name}`,
          type: 'Result',
        });
      }
    }
    for (const note of this.notes()) {
      if (note.status === 'draft') {
        rows.push({ id: note.id, label: `Week ${note.week_number}: ${note.topic}`, type: 'Lesson note' });
      }
    }
    for (const assignment of this.assignments()) {
      if (assignment.status === 'draft') {
        rows.push({ id: assignment.id, label: assignment.title, type: 'Assignment' });
      }
    }
    return rows.slice(0, 8);
  });
  readonly draftCount = computed(
    () =>
      this.results().filter((row) => row.status === 'draft').length +
      this.notes().filter((row) => row.status === 'draft').length +
      this.assignments().filter((row) => row.status === 'draft').length +
      this.announcements().filter((row) => row.status === 'draft').length,
  );
  readonly attendanceRate = computed(() => {
    const totals = this.attendance().reduce(
      (acc, row) => {
        acc.present += row.present;
        acc.total += row.present + row.late + row.absent;
        return acc;
      },
      { present: 0, total: 0 },
    );
    return totals.total ? Math.round((totals.present / totals.total) * 100) : 0;
  });

  constructor() {
    this.api.list<SchoolClass>('classes').subscribe((rows) => this.schoolClass.set(rows[0] ?? null));
    this.api.list<Subject>('subjects').subscribe((rows) => this.subjects.set(rows));
    this.api.list<Result>('results').subscribe((rows) => this.results.set(rows));
    this.api.list<LessonNote>('lesson-notes').subscribe((rows) => this.notes.set(rows));
    this.api.list<Assignment>('assignments').subscribe((rows) => this.assignments.set(rows));
    this.api.list<Announcement>('announcements').subscribe((rows) => this.announcements.set(rows));
    this.api
      .list<AttendanceSummary>('attendance/summary')
      .subscribe((rows) => this.attendance.set(rows));
  }
}
