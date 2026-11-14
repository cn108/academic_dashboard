import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';

import { ApiService } from '../../core/api.service';
import { AttendanceRecord, AttendanceSummary } from '../../core/models';

@Component({
  selector: 'app-student-attendance',
  imports: [DatePipe],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Student portal</p>
        <h1>My attendance</h1>
        <p class="muted small">Every day your teacher marked you present, late or absent.</p>
      </div>
    </div>

    <div class="grid grid-4" style="margin-bottom: 1.25rem">
      <div class="stat">
        <p class="muted small">Present</p>
        <p class="value">{{ totals().present }}</p>
      </div>
      <div class="stat">
        <p class="muted small">Late</p>
        <p class="value">{{ totals().late }}</p>
      </div>
      <div class="stat">
        <p class="muted small">Absent</p>
        <p class="value">{{ totals().absent }}</p>
      </div>
      <div class="stat">
        <p class="muted small">Attendance rate</p>
        <p class="value">{{ rate() }}%</p>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2 style="font-size: 1rem">Register</h2>
        <span class="badge badge-info">{{ records().length }} days</span>
      </div>

      @if (records().length) {
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              @for (record of records(); track record.id) {
                <tr>
                  <td>{{ record.date | date: 'fullDate' }}</td>
                  <td>
                    <span class="badge" [class]="tone(record.status)">{{ record.status }}</span>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="empty">Your teacher has not marked a register for you yet.</p>
      }
    </div>
  `,
})
export class StudentAttendance {
  private readonly api = inject(ApiService);

  readonly records = signal<AttendanceRecord[]>([]);
  readonly summary = signal<AttendanceSummary[]>([]);

  readonly totals = computed(() => {
    const rows = this.summary();
    return rows.reduce(
      (acc, row) => ({
        present: acc.present + row.present,
        late: acc.late + row.late,
        absent: acc.absent + row.absent,
      }),
      { present: 0, late: 0, absent: 0 },
    );
  });

  readonly rate = computed(() => {
    const { present, late, absent } = this.totals();
    const total = present + late + absent;
    return total ? Math.round((present / total) * 100) : 0;
  });

  constructor() {
    this.api.list<AttendanceRecord>('attendance').subscribe((rows) => this.records.set(rows));
    this.api
      .list<AttendanceSummary>('attendance/summary')
      .subscribe((rows) => this.summary.set(rows));
  }

  tone(status: string): string {
    if (status === 'present') {
      return 'badge-success';
    }
    return status === 'late' ? 'badge-warning' : 'badge-danger';
  }
}
