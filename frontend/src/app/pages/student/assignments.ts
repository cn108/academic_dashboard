import { Component, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { Assignment, KIND_LABELS, Submission, uploadProblem } from '../../core/models';

@Component({
  selector: 'app-student-assignments',
  imports: [DatePipe, DecimalPipe, FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Student portal</p>
        <h1>Assignments</h1>
        <p class="muted small">Upload your work before the due date.</p>
      </div>
    </div>

    @if (message()) {
      <div class="alert alert-success">{{ message() }}</div>
    }
    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    @if (uploadingId(); as activeId) {
      <div class="card" style="margin-bottom: 1.25rem">
        <div class="card-head">
          <h2 style="font-size: 1rem">Submit “{{ titleFor(activeId) }}”</h2>
          <button class="btn btn-ghost btn-sm" type="button" (click)="cancel()">Cancel</button>
        </div>
        <div class="field">
          <label for="file">Your file</label>
          <input
            id="file"
            type="file"
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
            (change)="onFile($event)"
          />
          <p class="small muted" style="margin-top: 0.35rem">PDF, Word or image · up to 5 MB.</p>
        </div>
        <div class="field">
          <label for="note">Note for your teacher (optional)</label>
          <textarea id="note" rows="2" [(ngModel)]="note"></textarea>
        </div>
        <button class="btn" type="button" [disabled]="!file || busy()" (click)="submit()">
          {{ busy() ? 'Uploading…' : 'Upload submission' }}
        </button>
      </div>
    }

    <div class="grid">
      @for (assignment of assignments(); track assignment.id) {
        <div class="card">
          <div class="card-head">
            <div>
              <h2 style="font-size: 1rem">{{ assignment.title }}</h2>
              <p class="muted small">
                {{ assignment.subject_name || 'Class work' }} ·
                {{ kindLabel(assignment.kind) }} · due
                {{ assignment.due_date | date: 'mediumDate' }}
              </p>
            </div>
            <div class="row-actions">
              @if (assignment.is_overdue) {
                <span class="badge badge-danger">overdue</span>
              }
              <span class="badge badge-info">{{ assignment.marks_total | number }} marks</span>
            </div>
          </div>

          @if (submissionFor(assignment.id); as submission) {
            <p class="muted small">Submitted {{ submission.submitted_at | date: 'medium' }}</p>
            @if (submission.is_graded) {
              <p style="margin-top: 0.4rem">
                <span class="badge badge-success">
                  {{ submission.marks | number }} / {{ assignment.marks_total | number }}
                </span>
              </p>
              @if (submission.feedback) {
                <p class="small muted" style="margin-top: 0.35rem">“{{ submission.feedback }}”</p>
              }
            } @else {
              <span class="badge badge-warning" style="margin-top: 0.4rem">Awaiting marking</span>
            }
          } @else {
            <button class="btn btn-sm" type="button" (click)="start(assignment.id)">Submit work</button>
          }
        </div>
      } @empty {
        <div class="card"><p class="empty">No assignments have been published yet.</p></div>
      }
    </div>
  `,
})
export class StudentAssignments {
  private readonly api = inject(ApiService);

  readonly assignments = signal<Assignment[]>([]);
  readonly submissions = signal<Submission[]>([]);
  readonly uploadingId = signal<number | null>(null);
  readonly message = signal('');
  readonly error = signal('');
  readonly busy = signal(false);

  file: File | null = null;
  note = '';

  constructor() {
    this.load();
  }

  load(): void {
    this.api.list<Assignment>('assignments').subscribe((rows) => this.assignments.set(rows));
    this.api.list<Submission>('submissions').subscribe((rows) => this.submissions.set(rows));
  }

  submissionFor(assignmentId: number): Submission | undefined {
    return this.submissions().find((row) => row.assignment === assignmentId);
  }

  titleFor(id: number): string {
    return this.assignments().find((row) => row.id === id)?.title ?? '';
  }

  kindLabel(kind: string): string {
    return KIND_LABELS[kind] ?? kind;
  }

  start(assignmentId: number): void {
    this.uploadingId.set(assignmentId);
    this.file = null;
    this.note = '';
    this.message.set('');
    this.error.set('');
  }

  cancel(): void {
    this.uploadingId.set(null);
  }

  onFile(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0] ?? null;
    if (!file) {
      this.file = null;
      return;
    }
    const problem = uploadProblem(file);
    if (problem) {
      this.file = null;
      (event.target as HTMLInputElement).value = '';
      this.error.set(problem);
      return;
    }
    this.error.set('');
    this.file = file;
  }

  submit(): void {
    const assignmentId = this.uploadingId();
    if (!assignmentId || !this.file) {
      return;
    }

    const problem = uploadProblem(this.file);
    if (problem) {
      this.error.set(problem);
      return;
    }

    const form = new FormData();
    form.append('assignment', String(assignmentId));
    form.append('note', this.note);
    form.append('file', this.file);

    this.busy.set(true);
    this.api.upload<Submission>('submissions', form).subscribe({
      next: () => {
        this.busy.set(false);
        this.uploadingId.set(null);
        this.message.set('Submission uploaded.');
        this.load();
      },
      error: (error) => {
        this.busy.set(false);
        const body = (error as { error?: Record<string, string[]> }).error;
        const messages = body && typeof body === 'object' ? Object.values(body).flat() : [];
        this.error.set(messages[0] ?? 'Upload failed. Check the file and try again.');
      },
    });
  }
}
