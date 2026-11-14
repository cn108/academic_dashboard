import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { Assignment, Submission } from '../../core/models';

interface Row {
  submission: Submission;
  marks: string;
  feedback: string;
}

@Component({
  selector: 'app-teacher-submissions',
  imports: [DatePipe, DecimalPipe, FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Teacher portal</p>
        <h1>Submissions</h1>
        <p class="muted small">Mark what your class has uploaded and send back a comment.</p>
      </div>
    </div>

    @if (message()) {
      <div class="alert alert-success">{{ message() }}</div>
    }
    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    <div class="card" style="margin-bottom: 1.25rem">
      <div class="grid grid-3">
        <div class="field">
          <label for="assignment">Assignment</label>
          <select id="assignment" [ngModel]="assignmentId()" (ngModelChange)="select($event)">
            @for (assignment of assignments(); track assignment.id) {
              <option [ngValue]="assignment.id">
                {{ assignment.title }} ({{ assignment.submissions_count }})
              </option>
            }
          </select>
        </div>
        <div class="field">
          <label>Due</label>
          <input [value]="selected() ? (selected()!.due_date | date: 'mediumDate') : '—'" readonly />
        </div>
        <div class="field">
          <label>Total marks</label>
          <input [value]="selected()?.marks_total | number" readonly />
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2 style="font-size: 1rem">Uploads</h2>
        <div class="row-actions">
          <span class="badge badge-info">{{ rows().length }} submitted</span>
          <span class="badge" [class]="graded() === rows().length && rows().length ? 'badge-success' : 'badge-warning'">
            {{ graded() }} / {{ rows().length }} marked
          </span>
        </div>
      </div>

      @if (rows().length) {
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Student</th>
                <th>Submitted</th>
                <th>File</th>
                <th>Marks</th>
                <th>Feedback</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (row of rows(); track row.submission.id) {
                <tr>
                  <td style="font-weight: 600">{{ row.submission.student_name }}</td>
                  <td class="muted small">{{ row.submission.submitted_at | date: 'medium' }}</td>
                  <td>
                    <a class="small" [href]="row.submission.file" target="_blank" rel="noopener">Open</a>
                    @if (row.submission.note) {
                      <p class="small muted" style="margin-top: 0.25rem">“{{ row.submission.note }}”</p>
                    }
                  </td>
                  <td>
                    <input
                      type="number"
                      min="0"
                      [max]="selected()?.marks_total ?? 0"
                      step="0.5"
                      [(ngModel)]="row.marks"
                      style="width: 78px"
                    />
                  </td>
                  <td>
                    <input [(ngModel)]="row.feedback" placeholder="Optional comment" style="min-width: 200px" />
                  </td>
                  <td>
                    @if (row.submission.is_graded) {
                      <span class="badge badge-success">marked</span>
                    } @else {
                      <span class="badge badge-warning">pending</span>
                    }
                  </td>
                  <td>
                    <button class="btn btn-sm" type="button" (click)="save(row)">Save mark</button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="empty">
          {{ assignments().length ? 'Nobody has uploaded work for this assignment yet.' : 'Set an assignment first.' }}
        </p>
      }
    </div>
  `,
})
export class TeacherSubmissions {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);

  readonly assignments = signal<Assignment[]>([]);
  readonly assignmentId = signal<number | null>(null);
  readonly submissions = signal<Submission[]>([]);
  readonly rows = signal<Row[]>([]);
  readonly message = signal('');
  readonly error = signal('');
  readonly selected = computed(
    () => this.assignments().find((row) => row.id === this.assignmentId()) ?? null,
  );
  readonly graded = computed(() => this.rows().filter((row) => row.submission.is_graded).length);

  constructor() {
    this.api.list<Assignment>('assignments').subscribe((rows) => {
      this.assignments.set(rows);
      this.pickAssignment();
    });
    // Links from the assignments table select their assignment by query param.
    this.route.queryParamMap.subscribe(() => this.pickAssignment());
    // The endpoint has no assignment filter, so fetch the class's uploads once.
    this.api.list<Submission>('submissions').subscribe((rows) => {
      this.submissions.set(rows);
      this.buildRows();
    });
  }

  private pickAssignment(): void {
    const rows = this.assignments();
    if (!rows.length) {
      return;
    }
    const requested = Number(this.route.snapshot.queryParamMap.get('assignment'));
    const match = rows.find((row) => row.id === requested);
    const next = match ?? rows.find((row) => row.submissions_count > 0) ?? rows[0];
    if (next.id !== this.assignmentId()) {
      this.assignmentId.set(next.id);
      this.message.set('');
      this.error.set('');
    }
    this.buildRows();
  }

  select(id: number): void {
    this.assignmentId.set(id);
    this.message.set('');
    this.error.set('');
    this.buildRows();
  }

  private buildRows(): void {
    const assignmentId = this.assignmentId();
    const fresh = new Map(
      this.submissions()
        .filter((row) => row.assignment === assignmentId)
        .map((row) => [row.id, row] as const),
    );

    this.rows.update((current) =>
      [...fresh.values()].map((submission) => {
        const edited = current.find((row) => row.submission.id === submission.id);
        return {
          submission,
          marks: edited
            ? edited.marks
            : submission.marks === null
              ? ''
              : String(Number(submission.marks)),
          feedback: edited ? edited.feedback : (submission.feedback ?? ''),
        };
      }),
    );
  }

  save(row: Row): void {
    const total = Number(this.selected()?.marks_total ?? 0);
    if (row.marks !== '' && (Number(row.marks) < 0 || Number(row.marks) > total)) {
      this.error.set(`Marks must be between 0 and ${total}.`);
      return;
    }

    const payload: { marks: number | null; feedback: string } = {
      marks: row.marks === '' ? null : Number(row.marks),
      feedback: row.feedback,
    };

    this.error.set('');
    this.api.update<Submission>(`submissions/${row.submission.id}/grade`, payload).subscribe({
      next: (submission) => {
        this.message.set(`Saved ${submission.student_name}'s mark.`);
        this.submissions.update((rows) =>
          rows.map((row) => (row.id === submission.id ? submission : row)),
        );
        this.rows.update((rows) =>
          rows.map((row) => (row.submission.id === submission.id ? { ...row, submission } : row)),
        );
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
    return 'Could not save that mark.';
  }
}
