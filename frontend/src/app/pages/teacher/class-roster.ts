import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { SchoolClass, StudentImportResult, Subject } from '../../core/models';

interface PasswordResetResponse {
  student_id: number;
  student_name: string;
  temporary_password: string;
  must_change_password: boolean;
  detail: string;
}

@Component({
  selector: 'app-class-roster',
  imports: [FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Teacher portal</p>
        <h1>{{ schoolClass()?.name || 'My class' }}</h1>
        <p class="muted small">
          {{ schoolClass()?.level }} · {{ schoolClass()?.student_count || 0 }} of
          {{ schoolClass()?.capacity || 50 }} places used
        </p>
      </div>
      @if (schoolClass(); as room) {
        <span class="badge" [class]="room.student_count >= room.capacity ? 'badge-danger' : 'badge-success'">
          {{ room.capacity - room.student_count }} places left
        </span>
      }
    </div>

    @if (message()) {
      <div class="alert alert-success">{{ message() }}</div>
    }
    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    @if (resetResult(); as reset) {
      <div class="card" role="dialog" aria-labelledby="reset-title" style="margin-bottom: 1rem">
        <div class="card-head">
          <h2 id="reset-title" style="font-size: 1rem">Temporary password for {{ reset.student_name }}</h2>
          <button class="btn btn-ghost btn-sm" type="button" (click)="closeReset()">Close</button>
        </div>
        <div class="alert alert-error">
          This password is displayed only once. Write it down and hand it directly to the student;
          they must change it at their next sign-in.
        </div>
        <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap">
          <code style="font-size: 1.1rem; user-select: all">{{ reset.temporary_password }}</code>
          <button class="btn btn-ghost btn-sm" type="button" (click)="copyPassword()">
            {{ copied() ? 'Copied' : 'Copy password' }}
          </button>
        </div>
      </div>
    }

    <div class="split">
      <div class="card">
        <div class="card-head"><h2 style="font-size: 1rem">Add students from CSV</h2></div>
        <p class="muted small" style="margin-bottom: 0.9rem">
          Columns: <strong>Full Name, Admission Number, Gender</strong>. Each student gets the
          admission number as their username and a default password they must change on first login.
        </p>
        <div class="field">
          <label for="csv">CSV file</label>
          <input id="csv" type="file" accept=".csv,text/csv" (change)="onFile($event)" />
        </div>
        <button class="btn" type="button" [disabled]="!file || busy()" (click)="upload()">
          {{ busy() ? 'Importing…' : 'Import students' }}
        </button>

        @if (result(); as report) {
          <div style="margin-top: 1rem">
            <p class="small">
              <strong>{{ report.created_count }}</strong> added · roster now
              <strong>{{ report.class.student_count }}</strong>
            </p>
            <p class="small muted">Default password: {{ report.default_password }}</p>
            @if (report.skipped.length) {
              <div class="alert alert-error" style="margin-top: 0.6rem">
                @for (row of report.skipped; track row.admission_number) {
                  <p class="small">{{ row.admission_number || 'row' }} — {{ row.reason }}</p>
                }
              </div>
            }
          </div>
        }

        <div style="margin-top: 1.25rem">
          <p class="nav-label">Subjects</p>
          @for (subject of subjects(); track subject.id) {
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.35rem">
              <span class="small">{{ subject.name }}</span>
              <span class="small muted">{{ subject.teacher_name }}</span>
            </div>
          } @empty {
            <p class="small muted">No subjects set up for this class.</p>
          }
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2 style="font-size: 1rem">Roster</h2>
          <span class="badge badge-info">{{ roster().length }}</span>
        </div>
        @if (roster().length) {
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Name</th>
                  <th>Admission no.</th>
                  <th>Gender</th>
                  <th>Account</th>
                </tr>
              </thead>
              <tbody>
                @for (student of roster(); track student.id; let i = $index) {
                  <tr>
                    <td class="muted">{{ i + 1 }}</td>
                    <td style="font-weight: 600">{{ student.full_name }}</td>
                    <td class="muted">{{ student.admission_number }}</td>
                    <td class="muted">{{ student.gender || '—' }}</td>
                    <td>
                      <button class="btn btn-ghost btn-sm" type="button" [disabled]="resetBusy()"
                        (click)="resetPassword(student.id)">
                        {{ resetBusy() ? 'Resetting…' : 'Reset password' }}
                      </button>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="empty">No students yet — import a CSV to get started.</p>
        }
      </div>
    </div>
  `,
})
export class ClassRoster {
  private readonly api = inject(ApiService);

  readonly schoolClass = signal<SchoolClass | null>(null);
  readonly subjects = signal<Subject[]>([]);
  readonly result = signal<StudentImportResult | null>(null);
  readonly resetResult = signal<PasswordResetResponse | null>(null);
  readonly copied = signal(false);
  readonly resetBusy = signal(false);
  readonly message = signal('');
  readonly error = signal('');
  readonly busy = signal(false);

  file: File | null = null;

  constructor() {
    this.load();
  }

  readonly roster = computed(() => this.schoolClass()?.students_detail ?? []);

  load(): void {
    this.api.list<SchoolClass>('classes').subscribe((rows) => this.schoolClass.set(rows[0] ?? null));
    this.api.list<Subject>('subjects').subscribe((rows) => this.subjects.set(rows));
  }

  onFile(event: Event): void {
    this.file = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  upload(): void {
    const room = this.schoolClass();
    if (!room || !this.file) {
      return;
    }
    const form = new FormData();
    form.append('file', this.file);

    this.busy.set(true);
    this.error.set('');
    this.message.set('');
    this.api.upload<StudentImportResult>(`classes/${room.id}/import-students`, form).subscribe({
      next: (report) => {
        this.busy.set(false);
        this.result.set(report);
        this.message.set(`${report.created_count} student(s) added to ${report.class.name}.`);
        this.file = null;
        this.load();
      },
      error: (error) => {
        this.busy.set(false);
        const body = (error as { error?: Record<string, unknown> }).error;
        const detail = body && typeof body === 'object' ? body['detail'] : null;
        this.error.set(
          typeof detail === 'string'
            ? detail
            : 'Import failed. Check the CSV columns and try again.',
        );
      },
    });
  }

  resetPassword(studentId: number): void {
    this.resetBusy.set(true);
    this.resetResult.set(null);
    this.copied.set(false);
    this.error.set('');
    this.api.action<PasswordResetResponse>(`students/${studentId}/reset-password`).subscribe({
      next: (response) => {
        this.resetBusy.set(false);
        this.resetResult.set(response);
      },
      error: () => {
        this.resetBusy.set(false);
        this.error.set('Could not reset that password. Check your class access and try again.');
      },
    });
  }

  async copyPassword(): Promise<void> {
    const password = this.resetResult()?.temporary_password;
    if (!password) {
      return;
    }
    try {
      await navigator.clipboard.writeText(password);
      this.copied.set(true);
    } catch {
      this.error.set('Clipboard access was blocked. Select and copy the temporary password manually.');
    }
  }

  closeReset(): void {
    this.resetResult.set(null);
    this.copied.set(false);
  }
}
