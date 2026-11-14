import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { printHtmlDocument } from '../../core/print';
import { ParentWardsResponse, Term, Ward } from '../../core/models';

@Component({
  selector: 'app-parent-ward-results',
  imports: [FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Parent portal</p>
        <h1>Ward results</h1>
        <p class="muted small">
          Read-only term report cards. Printing opens the same document the school gives at term end.
        </p>
      </div>
      <button
        class="btn btn-ghost"
        type="button"
        [disabled]="!selectedWard() || !selectedTerm()"
        (click)="printReportCard()"
      >
        Print / save PDF
      </button>
    </div>

    @if (printError()) {
      <div class="alert alert-error">{{ printError() }}</div>
    }

    <div class="card" style="margin-bottom: 1.25rem">
      <div class="grid grid-3">
        <div class="field" style="margin-bottom: 0">
          <label for="ward">Child</label>
          <select id="ward" [ngModel]="wardId()" (ngModelChange)="selectWard($event)">
            @for (ward of wards(); track ward.id) {
              <option [ngValue]="ward.id">{{ ward.full_name }}</option>
            }
          </select>
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
          <label>Class</label>
          <input [value]="selectedWard()?.class_name || '—'" readonly />
        </div>
      </div>
    </div>

    @if (selectedWard(); as ward) {
      <div class="grid grid-3">
        <div class="stat">
          <p class="muted small">Published subjects</p>
          <p class="value">{{ ward.subjects_count }}</p>
        </div>
        <div class="stat">
          <p class="muted small">Current term average</p>
          <p class="value">{{ ward.average === null ? '—' : ward.average }}</p>
        </div>
        <div class="stat">
          <p class="muted small">Attendance (30 days)</p>
          <p class="value">
            {{ ward.attendance_rate === null ? '—' : ward.attendance_rate + '%' }}
          </p>
        </div>
      </div>

      <div class="card" style="margin-top: 1.25rem">
        <div class="card-head">
          <h2 style="font-size: 1rem">Report card</h2>
          <span class="badge badge-info">{{ termLabel() || 'Choose a term' }}</span>
        </div>
        <p class="muted small" style="margin: 0">
          The report card includes every subject, the class averages, your child's position in class,
          the class teacher's remark and next term's fees. Use "Print / save PDF" above to open it.
        </p>
      </div>
    } @else {
      <p class="empty">No children are linked to this account yet.</p>
    }
  `,
})
export class ParentWardResults {
  private readonly api = inject(ApiService);

  readonly wards = signal<Ward[]>([]);
  readonly terms = signal<Term[]>([]);
  readonly wardId = signal<number | null>(null);
  readonly termId = signal<number | null>(null);
  readonly printError = signal('');

  readonly selectedWard = computed(
    () => this.wards().find((ward) => ward.id === this.wardId()) ?? null,
  );
  readonly selectedTerm = computed(
    () => this.terms().find((term) => term.id === this.termId()) ?? null,
  );
  readonly termLabel = computed(() => {
    const term = this.selectedTerm();
    return term ? `${term.session_name} · ${term.name}` : '';
  });

  constructor() {
    this.api.get<ParentWardsResponse>('parent/wards').subscribe((body) => {
      this.wards.set(body.wards);
      if (body.wards.length) {
        this.wardId.set(body.wards[0].id);
      }
    });

    this.api.list<Term>('terms').subscribe((rows) => {
      const ordered = rows
        .slice()
        .sort((a, b) => b.session_name.localeCompare(a.session_name) || b.name.localeCompare(a.name));
      this.terms.set(ordered);
      const current = ordered.find((term) => term.is_current) ?? ordered[0];
      if (current) {
        this.termId.set(current.id);
      }
    });
  }

  selectWard(id: number): void {
    this.wardId.set(id);
    this.printError.set('');
  }

  selectTerm(id: number): void {
    this.termId.set(id);
    this.printError.set('');
  }

  printReportCard(): void {
    const ward = this.selectedWard();
    const term = this.selectedTerm();
    if (!ward || !term) {
      return;
    }

    this.printError.set('');
    this.api.text(`students/${ward.id}/report-card`, { session: term.session, term: term.id }).subscribe({
      next: (html) => {
        if (!printHtmlDocument(html)) {
          this.printError.set('Could not open the print view in this browser.');
        }
      },
      error: () => this.printError.set('Could not build the report card. Try again in a moment.'),
    });
  }
}
