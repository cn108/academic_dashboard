import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { gradeTone, Result, Term } from '../../core/models';

@Component({
  selector: 'app-student-results',
  imports: [FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Student portal</p>
        <h1>My results</h1>
        <p class="muted small">
          Only results your teacher has published are shown here.
        </p>
      </div>
    </div>

    <div class="card" style="margin-bottom: 1.25rem">
      <div class="grid grid-2">
        <div class="field" style="margin-bottom: 0">
          <label for="term">Term</label>
          <select id="term" [ngModel]="termId()" (ngModelChange)="selectTerm($event)">
            @for (term of terms(); track term.id) {
              <option [ngValue]="term.id">{{ label(term) }}</option>
            }
          </select>
        </div>
        <div class="field" style="margin-bottom: 0">
          <label>Showing</label>
          <input [value]="termLabel() || '—'" readonly />
        </div>
      </div>
    </div>

    @if (results().length) {
      <div class="grid grid-3" style="margin-bottom: 1.25rem">
        <div class="stat">
          <p class="muted small">Subjects</p>
          <p class="value">{{ results().length }}</p>
        </div>
        <div class="stat">
          <p class="muted small">Average total</p>
          <p class="value">{{ average() }}</p>
        </div>
        <div class="stat">
          <p class="muted small">Term</p>
          <p class="value" style="font-size: 1.1rem">{{ termLabel() }}</p>
        </div>
      </div>
    }

    <div class="card">
      <div class="card-head">
        <h2 style="font-size: 1rem">Assessment breakdown</h2>
        <span class="badge badge-info">CA 40 · Exam 60</span>
      </div>

      @if (results().length) {
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Subject</th>
                <th>CA1</th>
                <th>CA2</th>
                <th>CA3</th>
                <th>CA total</th>
                <th>Exam</th>
                <th>Total</th>
                <th>Grade</th>
                <th>Remark</th>
              </tr>
            </thead>
            <tbody>
              @for (result of results(); track result.id) {
                <tr>
                  <td style="font-weight: 600">{{ result.subject_name }}</td>
                  <td class="muted">{{ result.ca1 }}</td>
                  <td class="muted">{{ result.ca2 }}</td>
                  <td class="muted">{{ result.ca3 }}</td>
                  <td>{{ result.ca_total }}</td>
                  <td>{{ result.exam }}</td>
                  <td style="font-weight: 600">{{ result.total }}</td>
                  <td>
                    <span class="badge" [class]="tone(result.grade)">{{ result.grade }}</span>
                  </td>
                  <td class="muted">{{ result.remarks }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="empty">
          No results published for {{ termLabel() || 'this term' }} yet. Try another term above.
        </p>
      }
    </div>
  `,
})
export class StudentResults {
  private readonly api = inject(ApiService);

  readonly terms = signal<Term[]>([]);
  readonly termId = signal<number | null>(null);
  readonly results = signal<Result[]>([]);

  readonly selectedTerm = computed(
    () => this.terms().find((term) => term.id === this.termId()) ?? null,
  );
  readonly termLabel = computed(() => {
    const term = this.selectedTerm();
    return term ? this.label(term) : '';
  });
  readonly average = computed(() => {
    const rows = this.results();
    if (!rows.length) {
      return '—';
    }
    return (rows.reduce((sum, row) => sum + row.total, 0) / rows.length).toFixed(1);
  });

  constructor() {
    this.api.list<Term>('terms').subscribe((rows) => {
      // Newest session first, then Third → First Term inside a session.
      const ordered = rows
        .slice()
        .sort((a, b) => b.session_name.localeCompare(a.session_name) || b.name.localeCompare(a.name));
      this.terms.set(ordered);
      if (ordered.length) {
        const current = ordered.find((term) => term.is_current) ?? ordered[0];
        this.termId.set(current.id);
        this.load();
      }
    });
  }

  label(term: Term): string {
    return `${term.session_name} · ${term.name}`;
  }

  selectTerm(id: number): void {
    this.termId.set(id);
    this.load();
  }

  load(): void {
    const termId = this.termId();
    if (!termId) {
      return;
    }
    this.api.list<Result>('results', { term: termId }).subscribe((rows) => this.results.set(rows));
  }

  tone(grade: string): string {
    return gradeTone(grade);
  }
}
