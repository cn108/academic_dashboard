import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { AttendanceRecord, AttendanceSummary, SchoolClass } from '../../core/models';

const STATUSES = ['present', 'late', 'absent'] as const;
type Status = (typeof STATUSES)[number];

@Component({
  selector: 'app-teacher-attendance',
  imports: [FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Teacher portal</p>
        <h1>Attendance</h1>
        <p class="muted small">Pick a date, mark the class list, then save the register.</p>
      </div>
    </div>

    @if (message()) {
      <div class="alert alert-success">{{ message() }}</div>
    }
    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    <div class="grid grid-3" style="margin-bottom: 1.25rem">
      @for (row of summary(); track row.school_class) {
        <div class="stat">
          <p class="muted small">{{ row.class_name }}</p>
          <p class="value">{{ rate(row) }}%</p>
          <p class="small muted">
            {{ row.present }} present · {{ row.late }} late · {{ row.absent }} absent
          </p>
        </div>
      }
    </div>

    <div class="card" style="margin-bottom: 1.25rem">
      <div class="grid grid-3">
        <div class="field">
          <label for="class">Class</label>
          <select id="class" [ngModel]="classId()" (ngModelChange)="selectClass($event)">
            @for (room of classes(); track room.id) {
              <option [ngValue]="room.id">{{ room.name }}</option>
            }
          </select>
        </div>
        <div class="field">
          <label for="date">Date</label>
          <input id="date" type="date" [ngModel]="date()" (ngModelChange)="selectDate($event)" />
        </div>
        <div class="field">
          <label>&nbsp;</label>
          <button class="btn" type="button" [disabled]="!roster().length || busy()" (click)="save()">
            {{ busy() ? 'Saving…' : 'Save register' }}
          </button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2 style="font-size: 1rem">Class list</h2>
        <span class="badge badge-info">{{ roster().length }} students</span>
      </div>
      @if (roster().length) {
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Student</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              @for (student of roster(); track student.id) {
                <tr>
                  <td style="font-weight: 600">{{ student.full_name }}</td>
                  <td>
                    <div class="row-actions">
                      @for (status of statuses; track status) {
                        <button
                          class="btn btn-sm status-toggle"
                          [class.btn-ghost]="statusFor(student.id) !== status"
                          [attr.aria-pressed]="statusFor(student.id) === status"
                          [attr.aria-label]="status + ' for ' + student.full_name"
                          type="button"
                          (click)="mark(student.id, status)"
                        >
                          {{ status }}
                        </button>
                      }
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="empty">No students in this class yet.</p>
      }
    </div>
  `,
})
export class TeacherAttendance {
  private readonly api = inject(ApiService);

  readonly statuses = STATUSES;
  readonly classes = signal<SchoolClass[]>([]);
  readonly summary = signal<AttendanceSummary[]>([]);
  readonly classId = signal<number | null>(null);
  readonly date = signal<string>(new Date().toISOString().slice(0, 10));
  readonly marks = signal<Record<number, Status>>({});
  readonly message = signal('');
  readonly error = signal('');
  readonly busy = signal(false);

  readonly roster = computed(() => {
    const room = this.classes().find((row) => row.id === this.classId());
    return room?.students_detail ?? [];
  });

  constructor() {
    this.api.list<SchoolClass>('classes').subscribe((rows) => {
      this.classes.set(rows);
      if (rows.length) {
        this.classId.set(rows[0].id);
        this.loadRegister();
      }
    });
    this.api
      .list<AttendanceSummary>('attendance/summary')
      .subscribe((rows) => this.summary.set(rows));
  }

  rate(row: AttendanceSummary): number {
    const total = row.present + row.late + row.absent;
    return total ? Math.round((row.present / total) * 100) : 0;
  }

  selectClass(id: number): void {
    this.classId.set(id);
    this.loadRegister();
  }

  selectDate(value: string): void {
    this.date.set(value);
    this.loadRegister();
  }

  statusFor(studentId: number): Status {
    return this.marks()[studentId] ?? 'present';
  }

  mark(studentId: number, status: Status): void {
    this.marks.update((current) => ({ ...current, [studentId]: status }));
  }

  loadRegister(): void {
    const classId = this.classId();
    if (!classId) {
      return;
    }
    this.api
      .list<AttendanceRecord>('attendance', { class: classId, date: this.date() })
      .subscribe((rows) => {
        const marks: Record<number, Status> = {};
        for (const row of rows) {
          marks[row.student] = row.status;
        }
        this.marks.set(marks);
      });
  }

  save(): void {
    const classId = this.classId();
    if (!classId) {
      return;
    }
    const payload = {
      class: classId,
      date: this.date(),
      records: this.roster().map((student) => ({
        student: student.id,
        status: this.statusFor(student.id),
      })),
    };

    this.busy.set(true);
    this.error.set('');
    this.api.create<AttendanceRecord[]>('attendance/bulk', payload).subscribe({
      next: () => {
        this.busy.set(false);
        this.message.set('Register saved.');
        this.loadRegister();
        this.api
          .list<AttendanceSummary>('attendance/summary')
          .subscribe((rows) => this.summary.set(rows));
      },
      error: () => {
        this.busy.set(false);
        this.error.set('Could not save the register. Check the date and try again.');
      },
    });
  }
}
