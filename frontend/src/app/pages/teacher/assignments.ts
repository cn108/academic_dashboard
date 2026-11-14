import { Component, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import {
  Assignment,
  CurrentTerm,
  KIND_LABELS,
  statusTone,
  Subject,
} from '../../core/models';

@Component({
  selector: 'app-teacher-assignments',
  imports: [DatePipe, DecimalPipe, FormsModule, RouterLink],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Teacher portal</p>
        <h1>Assignments</h1>
        <p class="muted small">Set work for your class; students see it only once published.</p>
      </div>
    </div>

    @if (message()) {
      <div class="alert alert-success">{{ message() }}</div>
    }
    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    <div class="split">
      <div class="card">
        <div class="card-head"><h2 style="font-size: 1rem">Set new work</h2></div>
        <div class="field">
          <label for="title">Title</label>
          <input id="title" [(ngModel)]="draft.title" />
        </div>
        <div class="field">
          <label for="subject">Subject</label>
          <select id="subject" [(ngModel)]="draft.subject">
            @for (subject of subjects(); track subject.id) {
              <option [ngValue]="subject.id">{{ subject.name }}</option>
            }
          </select>
        </div>
        <div class="field">
          <label for="kind">Type</label>
          <select id="kind" [(ngModel)]="draft.kind">
            <option value="assignment">Assignment</option>
            <option value="coursework">Coursework</option>
            <option value="group_project">Group project</option>
          </select>
        </div>
        <div class="field">
          <label for="due">Due date</label>
          <input id="due" type="date" [(ngModel)]="draft.due_date" />
        </div>
        <div class="field">
          <label for="marks">Total marks</label>
          <input id="marks" type="number" min="1" [(ngModel)]="draft.marks_total" />
        </div>
        <div class="field">
          <label for="status">Visibility</label>
          <select id="status" [(ngModel)]="draft.status">
            <option value="draft">Save as draft</option>
            <option value="published">Publish to students</option>
          </select>
        </div>
        <button class="btn" type="button" [disabled]="busy()" (click)="create()">
          {{ busy() ? 'Saving…' : 'Save assignment' }}
        </button>
      </div>

      <div class="card">
        <div class="card-head"><h2 style="font-size: 1rem">Your assignments</h2></div>
        @if (assignments().length) {
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Subject</th>
                  <th>Due</th>
                  <th>Marks</th>
                  <th>Submitted</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                @for (assignment of assignments(); track assignment.id) {
                  <tr>
                    <td style="font-weight: 600">{{ assignment.title }}</td>
                    <td class="muted">{{ assignment.subject_name || '—' }}</td>
                    <td>{{ assignment.due_date | date: 'mediumDate' }}</td>
                    <td>{{ assignment.marks_total | number }}</td>
                    <td>{{ assignment.submissions_count }}</td>
                    <td>
                      <span class="badge" [class]="tone(assignment.status)">{{ assignment.status }}</span>
                    </td>
                    <td>
                      <div class="row-actions">
                        @if (assignment.status !== 'published') {
                          <button class="btn btn-sm" type="button" (click)="publish(assignment)">Publish</button>
                        }
                        <a
                          class="btn btn-ghost btn-sm"
                          routerLink="/teacher/submissions"
                          [queryParams]="{ assignment: assignment.id }"
                        >
                          Mark ({{ assignment.submissions_count }})
                        </a>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="empty">No assignments set yet.</p>
        }
      </div>
    </div>
  `,
})
export class TeacherAssignments {
  private readonly api = inject(ApiService);

  readonly subjects = signal<Subject[]>([]);
  readonly assignments = signal<Assignment[]>([]);
  readonly current = signal<CurrentTerm | null>(null);
  readonly message = signal('');
  readonly error = signal('');
  readonly busy = signal(false);

  draft = {
    title: '',
    subject: null as number | null,
    kind: 'assignment',
    due_date: '',
    marks_total: 20,
    status: 'draft',
  };

  constructor() {
    this.api.get<CurrentTerm>('terms/current').subscribe((payload) => this.current.set(payload));
    this.api.list<Subject>('subjects').subscribe((rows) => {
      this.subjects.set(rows);
      if (rows.length && this.draft.subject === null) {
        this.draft.subject = rows[0].id;
      }
    });
    this.load();
  }

  load(): void {
    this.api.list<Assignment>('assignments').subscribe((rows) => this.assignments.set(rows));
  }

  kindLabel(kind: string): string {
    return KIND_LABELS[kind] ?? kind;
  }

  tone(status: string): string {
    return statusTone(status as never);
  }

  create(): void {
    if (!this.draft.title.trim() || !this.draft.subject || !this.draft.due_date) {
      this.error.set('A title, subject and due date are required.');
      return;
    }
    const payload = { ...this.draft, term: this.current()?.term.id ?? null };

    this.busy.set(true);
    this.error.set('');
    this.api.create<Assignment>('assignments', payload).subscribe({
      next: () => {
        this.busy.set(false);
        this.message.set('Assignment saved.');
        this.draft = { ...this.draft, title: '' };
        this.load();
      },
      error: (error) => {
        this.busy.set(false);
        this.error.set(this.describe(error));
      },
    });
  }

  publish(assignment: Assignment): void {
    this.api.action<Assignment>(`assignments/${assignment.id}/publish`).subscribe({
      next: () => {
        this.message.set(`Published “${assignment.title}”.`);
        this.load();
      },
      error: (error) => this.error.set(this.describe(error)),
    });
  }

  private describe(error: unknown): string {
    const body = (error as { error?: Record<string, string[]> }).error;
    if (body && typeof body === 'object') {
      const messages = Object.values(body).flat();
      if (messages.length) {
        return messages.join(' ');
      }
    }
    return 'Could not save that assignment.';
  }
}
