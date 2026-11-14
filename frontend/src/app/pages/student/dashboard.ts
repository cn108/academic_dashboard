import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import {
  Announcement,
  Assignment,
  gradeTone,
  LessonNote,
  Result,
  statusTone,
} from '../../core/models';

@Component({
  selector: 'app-student-dashboard',
  imports: [RouterLink, DatePipe],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">{{ user()?.class_name || 'Student' }}</p>
        <h1>Hello, {{ firstName() }}</h1>
        <p class="muted small">{{ termLabel() || 'Your published school work shows up here.' }}</p>
      </div>
      <a class="btn btn-ghost" routerLink="/student/results">View results</a>
    </div>

    <div class="grid grid-4" style="margin-bottom: 1.25rem">
      <div class="stat">
        <p class="muted small">Subjects with results</p>
        <p class="value">{{ results().length }}</p>
      </div>
      <div class="stat">
        <p class="muted small">Average</p>
        <p class="value">{{ average() }}</p>
      </div>
      <div class="stat">
        <p class="muted small">Lesson notes</p>
        <p class="value">{{ notes().length }}</p>
      </div>
      <div class="stat">
        <p class="muted small">Open assignments</p>
        <p class="value">{{ assignments().length }}</p>
      </div>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-head">
          <h2 style="font-size: 1rem">Latest results</h2>
          <a class="small" routerLink="/student/results">All results</a>
        </div>
        @if (results().length) {
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Subject</th>
                  <th>Total</th>
                  <th>Grade</th>
                </tr>
              </thead>
              <tbody>
                @for (result of results().slice(0, 4); track result.id) {
                  <tr>
                    <td>{{ result.subject_name }}</td>
                    <td>{{ result.total }}</td>
                    <td><span class="badge" [class]="tone(result.grade)">{{ result.grade }}</span></td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="empty">No results published yet.</p>
        }
      </div>

      <div class="grid">
        <div class="card">
          <div class="card-head">
            <h2 style="font-size: 1rem">Newest lesson note</h2>
            <a class="small" routerLink="/student/notes">All notes</a>
          </div>
          @if (notes().length) {
            <p style="font-weight: 600">{{ notes()[0].topic }}</p>
            <p class="muted small">
              Week {{ notes()[0].week_number }} · {{ notes()[0].subject_name }}
            </p>
            <p class="small" style="margin-top: 0.5rem">{{ notes()[0].content || 'Open the note for details.' }}</p>
          } @else {
            <p class="empty">No lesson notes published yet.</p>
          }
        </div>

        <div class="card">
          <div class="card-head">
            <h2 style="font-size: 1rem">Notice board</h2>
            <a class="small" routerLink="/student/announcements">All notices</a>
          </div>
          @if (announcements().length) {
            @for (item of announcements().slice(0, 2); track item.id) {
              <div style="margin-bottom: 0.7rem">
                <p style="font-weight: 600">{{ item.title }}</p>
                <p class="muted small">{{ item.body }}</p>
              </div>
            }
          } @else {
            <p class="empty">Nothing posted yet.</p>
          }
        </div>

        <div class="card">
          <div class="card-head">
            <h2 style="font-size: 1rem">Work due</h2>
            <a class="small" routerLink="/student/assignments">Submit work</a>
          </div>
          @if (assignments().length) {
            @for (assignment of assignments().slice(0, 3); track assignment.id) {
              <div style="display: flex; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.5rem">
                <span>
                  {{ assignment.title }}
                  <span class="muted small">· {{ assignment.subject_name }}</span>
                </span>
                <span class="badge" [class]="assignment.is_overdue ? 'badge-danger' : 'badge-info'">
                  {{ assignment.due_date | date: 'mediumDate' }}
                </span>
              </div>
            }
          } @else {
            <p class="empty">Nothing due right now.</p>
          }
        </div>
      </div>
    </div>
  `,
})
export class StudentDashboard {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);

  readonly user = this.auth.user;
  readonly results = signal<Result[]>([]);
  readonly notes = signal<LessonNote[]>([]);
  readonly assignments = signal<Assignment[]>([]);
  readonly announcements = signal<Announcement[]>([]);

  readonly firstName = computed(() => (this.user()?.name ?? 'student').split(' ')[0]);
  readonly termLabel = computed(() => {
    const result = this.results()[0];
    return result ? `${result.session_name} · ${result.term_name}` : '';
  });
  readonly average = computed(() => {
    const rows = this.results();
    if (!rows.length) {
      return '—';
    }
    const total = rows.reduce((sum, row) => sum + row.total, 0);
    return (total / rows.length).toFixed(1);
  });

  constructor() {
    this.api.list<Result>('results').subscribe((rows) => this.results.set(rows));
    this.api
      .list<LessonNote>('lesson-notes')
      .subscribe((rows) => this.notes.set(rows.slice().reverse()));
    this.api.list<Assignment>('assignments').subscribe((rows) => this.assignments.set(rows));
    this.api
      .list<Announcement>('announcements')
      .subscribe((rows) => this.announcements.set(rows));
  }

  tone(grade: string): string {
    return gradeTone(grade);
  }

  statusTone(status: string): string {
    return statusTone(status as never);
  }
}
