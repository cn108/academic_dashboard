import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { ScrollHint } from '../../core/scroll-hint.directive';
import {
  Broadsheet,
  BroadsheetStudent,
  ResultImportReport,
  SchoolClass,
  Term,
} from '../../core/models';

@Component({
  selector: 'app-teacher-broadsheet',
  imports: [FormsModule, ScrollHint],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Teacher portal</p>
        <h1>Broadsheet</h1>
        <p class="muted small">
          Every student against every subject. Averages and positions count published results only.
        </p>
      </div>
      <div class="row-actions">
        <button class="btn btn-ghost" type="button" [disabled]="!sheet()" (click)="downloadXlsx()">
          Export Excel
        </button>
        <button class="btn btn-ghost" type="button" [disabled]="!sheet()" (click)="downloadTemplate()">
          Download CSV template
        </button>
        <label class="btn" style="cursor: pointer">
          {{ busy() ? 'Importing…' : 'Upload CSV' }}
          <input
            type="file"
            accept=".csv,text/csv"
            style="display: none"
            [disabled]="!sheet() || busy()"
            (change)="onFile($event)"
          />
        </label>
      </div>
    </div>

    @if (message()) {
      <div class="alert alert-success">{{ message() }}</div>
    }
    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }
    @if (report(); as result) {
      <div class="card" style="margin-bottom: 1.25rem">
        <div class="card-head">
          <h2 style="font-size: 1rem">Import report</h2>
          <button class="btn btn-ghost btn-sm" type="button" (click)="report.set(null)">Dismiss</button>
        </div>
        <div class="row-actions" style="gap: 0.5rem">
          <span class="badge badge-success">{{ result.created }} created</span>
          <span class="badge badge-info">{{ result.updated }} updated</span>
          <span class="badge" [class]="result.errors.length ? 'badge-danger' : 'badge-success'">
            {{ result.errors.length }} errors
          </span>
        </div>
        @if (result.errors.length) {
          <div class="table-wrap" style="margin-top: 0.75rem">
            <table>
              <thead>
                <tr>
                  <th style="width: 80px">Row</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                @for (issue of result.errors; track issue.row) {
                  <tr>
                    <td class="muted">{{ issue.row }}</td>
                    <td>{{ issue.reason }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </div>
    }

    <div class="card" style="margin-bottom: 1.25rem">
      <div class="grid grid-3">
        <div class="field" style="margin-bottom: 0">
          <label>Class</label>
          <input [value]="schoolClass()?.name || '—'" readonly />
        </div>
        <div class="field" style="margin-bottom: 0">
          <label for="term">Term</label>
          <select id="term" [ngModel]="termId()" (ngModelChange)="selectTerm($event)">
            @for (term of terms(); track term.id) {
              <option [ngValue]="term.id">{{ term.session_name }} · {{ term.name }}</option>
            }
          </select>
        </div>
        <div class="field" style="margin-bottom: 0">
          <label>Students</label>
          <input [value]="sheet()?.student_count ?? 0" readonly />
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2 style="font-size: 1rem">{{ sheet()?.class?.name || 'Class' }} result summary</h2>
        <span class="badge badge-info">{{ subjects().length }} subjects</span>
      </div>

      @if (students().length && subjects().length) {
        <div class="table-shell">
          <p class="scroll-hint">Swipe sideways to see every subject →</p>
          <div class="table-wrap" appScrollHint>
          <table>
            <thead>
              <tr>
                <th>Student</th>
                @for (subject of subjects(); track subject.id) {
                  <th>{{ subject.name }}</th>
                }
                <th>Total</th>
                <th>Average</th>
                <th>Position</th>
              </tr>
            </thead>
            <tbody>
              @for (student of students(); track student.id) {
                <tr>
                  <td style="font-weight: 600">
                    {{ student.full_name }}
                    <p class="muted small" style="font-weight: 400">
                      {{ student.admission_number || '—' }}
                    </p>
                  </td>
                  @for (subject of subjects(); track subject.id) {
                    <td [class.muted]="!scoreFor(student, subject.id)">
                      {{ scoreFor(student, subject.id) ?? '—' }}
                    </td>
                  }
                  <td style="font-weight: 600">{{ student.total }}</td>
                  <td>{{ student.average ?? '—' }}</td>
                  <td>
                    @if (student.position) {
                      <span class="badge" [class]="student.position <= 3 ? 'badge-success' : 'badge-info'">
                        {{ student.position }}
                      </span>
                    } @else {
                      <span class="muted">—</span>
                    }
                  </td>
                </tr>
              }
            </tbody>
            <tfoot>
              <tr>
                <td style="font-weight: 600">Class average</td>
                @for (subject of subjects(); track subject.id) {
                  <td>{{ subject.class_average ?? '—' }}</td>
                }
                <td colspan="3" class="muted">Published results only</td>
              </tr>
            </tfoot>
          </table>
          </div>
        </div>
      } @else if (!subjects().length) {
        <p class="empty">Set up subjects for this class first.</p>
      } @else {
        <p class="empty">No students in this class yet.</p>
      }
    </div>
  `,
})
export class TeacherBroadsheet {
  private readonly api = inject(ApiService);

  readonly classes = signal<SchoolClass[]>([]);
  readonly schoolClass = computed(() => this.classes()[0] ?? null);
  readonly terms = signal<Term[]>([]);
  readonly termId = signal<number | null>(null);
  readonly sheet = signal<Broadsheet | null>(null);
  readonly report = signal<ResultImportReport | null>(null);
  readonly message = signal('');
  readonly error = signal('');
  readonly busy = signal(false);

  readonly subjects = computed(() => this.sheet()?.subjects ?? []);
  readonly students = computed(() => this.sheet()?.students ?? []);

  constructor() {
    this.api.list<SchoolClass>('classes').subscribe((rows) => {
      this.classes.set(rows);
      this.load();
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
      this.load();
    });
  }

  selectTerm(id: number): void {
    this.termId.set(id);
    this.message.set('');
    this.error.set('');
    this.load();
  }

  load(): void {
    const schoolClass = this.schoolClass();
    const term = this.terms().find((row) => row.id === this.termId());
    if (!schoolClass || !term) {
      return;
    }
    this.api
      .get<Broadsheet>(`classes/${schoolClass.id}/broadsheet`, {
        session: term.session,
        term: term.id,
      })
      .subscribe({
        next: (sheet) => this.sheet.set(sheet),
        error: () => this.error.set('Could not load the broadsheet for that term.'),
      });
  }

  scoreFor(student: BroadsheetStudent, subjectId: number): number | null {
    return student.scores.find((score) => score.subject === subjectId)?.total ?? null;
  }

  downloadXlsx(): void {
    const schoolClass = this.schoolClass();
    const term = this.terms().find((row) => row.id === this.termId());
    if (!schoolClass || !term) {
      return;
    }
    this.api
      .download(`classes/${schoolClass.id}/broadsheet`, {
        session: term.session,
        term: term.id,
        format: 'xlsx',
      })
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = `broadsheet-${schoolClass.name}-${term.name}.xlsx`;
          anchor.click();
          URL.revokeObjectURL(url);
        },
        error: () => this.error.set('Could not export the broadsheet.'),
      });
  }

  downloadTemplate(): void {
    const schoolClass = this.schoolClass();
    const term = this.terms().find((row) => row.id === this.termId());
    if (!schoolClass || !term) {
      return;
    }
    this.api.download(`classes/${schoolClass.id}/results/template`, { term: term.id }).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = `results-template-${schoolClass.name}-${term.name}.csv`;
        anchor.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.error.set('Could not download the template.'),
    });
  }

  onFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    const schoolClass = this.schoolClass();
    const term = this.terms().find((row) => row.id === this.termId());
    if (!file || !schoolClass || !term) {
      return;
    }
    if (!file.name.toLowerCase().endsWith('.csv')) {
      this.error.set('Upload the CSV template (or a file ending in .csv).');
      return;
    }

    const form = new FormData();
    form.append('file', file);

    this.busy.set(true);
    this.error.set('');
    this.message.set('');
    this.api
      .upload<ResultImportReport>(`classes/${schoolClass.id}/results/bulk-import`, form, {
        session: term.session,
        term: term.id,
      })
      .subscribe({
        next: (result) => {
          this.busy.set(false);
          this.report.set(result);
          this.message.set(
            `${result.created} created, ${result.updated} updated, ${result.errors.length} errors.`,
          );
          this.load();
        },
        error: () => {
          this.busy.set(false);
          this.error.set('Import failed. Check the CSV columns and try again.');
        },
      });
  }
}
