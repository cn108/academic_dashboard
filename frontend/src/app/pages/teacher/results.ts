import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { gradeTone, Result, SchoolClass, StudentSummary, Subject, Term } from '../../core/models';

interface Row {
  student: StudentSummary;
  result: Result | null;
  ca1: number;
  ca2: number;
  ca3: number;
  exam: number;
}

@Component({
  selector: 'app-teacher-results',
  imports: [FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Teacher portal</p>
        <h1>Results</h1>
        <p class="muted small">
          CA1 (10) + CA2 (10) + CA3 (20) + Exam (60). Saved scores stay hidden until you publish.
        </p>
      </div>
    </div>

    @if (message()) {
      <div class="alert alert-success">{{ message() }}</div>
    }
    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    <div class="card" style="margin-bottom: 1.25rem">
      <div class="grid grid-2">
        <div class="field">
          <label for="subject">Subject</label>
          <select id="subject" [ngModel]="subjectId()" (ngModelChange)="selectSubject($event)">
            @for (subject of subjects(); track subject.id) {
              <option [ngValue]="subject.id">{{ subject.name }}</option>
            }
          </select>
        </div>
        <div class="field">
          <label for="term">Term</label>
          <select id="term" [ngModel]="termId()" (ngModelChange)="selectTerm($event)">
            @for (term of terms(); track term.id) {
              <option [ngValue]="term.id">{{ label(term) }}</option>
            }
          </select>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2 style="font-size: 1rem">Class list</h2>
        <span class="badge badge-info">{{ rows().length }} students</span>
      </div>

      @if (rows().length) {
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Student</th>
                <th>CA1</th>
                <th>CA2</th>
                <th>CA3</th>
                <th>Exam</th>
                <th>Total</th>
                <th>Grade</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (row of rows(); track row.student.id) {
                <tr>
                  <td style="font-weight: 600">{{ row.student.full_name }}</td>
                  <td><input type="number" min="0" max="10" [(ngModel)]="row.ca1" style="width: 64px" /></td>
                  <td><input type="number" min="0" max="10" [(ngModel)]="row.ca2" style="width: 64px" /></td>
                  <td><input type="number" min="0" max="20" [(ngModel)]="row.ca3" style="width: 64px" /></td>
                  <td><input type="number" min="0" max="60" [(ngModel)]="row.exam" style="width: 72px" /></td>
                  <td style="font-weight: 600">{{ previewTotal(row) }}</td>
                  <td>
                    <span class="badge" [class]="tone(previewGrade(row))">{{ previewGrade(row) }}</span>
                  </td>
                  <td>
                    @if (row.result) {
                      <span class="badge" [class]="row.result.status === 'published' ? 'badge-success' : 'badge-warning'">
                        {{ row.result.status }}
                      </span>
                    } @else {
                      <span class="muted small">not saved</span>
                    }
                  </td>
                  <td>
                    <div class="row-actions">
                      <button class="btn btn-ghost btn-sm" type="button" (click)="save(row)">Save</button>
                      @if (row.result && row.result.status !== 'published') {
                        <button class="btn btn-sm" type="button" (click)="publish(row)">Publish</button>
                      }
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="empty">Pick a subject with students in your class.</p>
      }
    </div>
  `,
})
export class TeacherResults {
  private readonly api = inject(ApiService);

  readonly schoolClass = signal<SchoolClass | null>(null);
  readonly subjects = signal<Subject[]>([]);
  readonly subjectId = signal<number | null>(null);
  readonly terms = signal<Term[]>([]);
  readonly termId = signal<number | null>(null);
  readonly selectedTerm = computed(
    () => this.terms().find((term) => term.id === this.termId()) ?? null,
  );
  readonly rows = signal<Row[]>([]);
  readonly message = signal('');
  readonly error = signal('');

  constructor() {
    this.api.list<SchoolClass>('classes').subscribe((rows) => {
      this.schoolClass.set(rows[0] ?? null);
      this.reload();
    });
    this.api.list<Term>('terms').subscribe((rows) => {
      const ordered = rows
        .slice()
        .sort((a, b) => b.session_name.localeCompare(a.session_name) || b.name.localeCompare(a.name));
      this.terms.set(ordered);
      if (ordered.length) {
        const current = ordered.find((term) => term.is_current) ?? ordered[0];
        this.termId.set(current.id);
      }
      this.reload();
    });
    this.api.list<Subject>('subjects').subscribe((rows) => {
      this.subjects.set(rows);
      if (rows.length) {
        this.subjectId.set(rows[0].id);
        this.reload();
      }
    });
  }

  termLabel(): string {
    const term = this.selectedTerm();
    return term ? this.label(term) : '—';
  }

  label(term: Term): string {
    return `${term.session_name} · ${term.name}`;
  }

  selectSubject(id: number): void {
    this.subjectId.set(id);
    this.reload();
  }

  selectTerm(id: number): void {
    this.termId.set(id);
    this.message.set('');
    this.error.set('');
    this.reload();
  }

  reload(): void {
    const subjectId = this.subjectId();
    const term = this.selectedTerm();
    const room = this.schoolClass();
    if (!subjectId || !term || !room) {
      return;
    }

    this.api
      .list<Result>('results', {
        subject: subjectId,
        session: term.session,
        term: term.id,
      })
      .subscribe((results) => {
        const byStudent = new Map(results.map((result) => [result.student, result]));
        this.rows.set(
          room.students_detail.map((student) => {
            const result = byStudent.get(student.id) ?? null;
            return {
              student,
              result,
              ca1: result?.ca1 ?? 0,
              ca2: result?.ca2 ?? 0,
              ca3: result?.ca3 ?? 0,
              exam: result?.exam ?? 0,
            };
          }),
        );
      });
  }

  previewTotal(row: Row): number {
    return Number(row.ca1) + Number(row.ca2) + Number(row.ca3) + Number(row.exam);
  }

  previewGrade(row: Row): string {
    const total = this.previewTotal(row);
    if (total >= 70) return 'A';
    if (total >= 60) return 'B';
    if (total >= 50) return 'C';
    if (total >= 45) return 'D';
    if (total >= 40) return 'E';
    return 'F';
  }

  tone(grade: string): string {
    return gradeTone(grade);
  }

  save(row: Row): void {
    const term = this.selectedTerm();
    const subjectId = this.subjectId();
    if (!term || !subjectId) {
      return;
    }

    const body = {
      student: row.student.id,
      subject: subjectId,
      session: term.session,
      term: term.id,
      ca1: Number(row.ca1),
      ca2: Number(row.ca2),
      ca3: Number(row.ca3),
      exam: Number(row.exam),
    };

    const request = row.result
      ? this.api.update<Result>(`results/${row.result.id}`, body)
      : this.api.create<Result>('results', { ...body, status: 'draft' });

    request.subscribe({
      next: () => {
        this.message.set(`Saved ${row.student.full_name}.`);
        this.error.set('');
        this.reload();
      },
      error: (error) => this.error.set(this.describe(error)),
    });
  }

  publish(row: Row): void {
    if (!row.result) {
      return;
    }
    this.api.action<Result>(`results/${row.result.id}/publish`).subscribe({
      next: () => {
        this.message.set(`Published ${row.student.full_name}'s result.`);
        this.error.set('');
        this.reload();
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
    return 'Could not save that result.';
  }
}
