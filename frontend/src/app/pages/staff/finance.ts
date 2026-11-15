import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { ScrollHint } from '../../core/scroll-hint.directive';
import { Debtor, FinanceSummary, naira, Paged, Term } from '../../core/models';

@Component({
  selector: 'app-staff-finance',
  imports: [FormsModule, ScrollHint],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Bursar</p>
        <h1>Finance</h1>
        <p class="muted small">
          Fees for the selected term, from the same ledger parents pay into.
        </p>
      </div>
      <div class="row-actions">
        <button
          class="btn"
          type="button"
          [disabled]="!term() || downloading()"
          (click)="exportLedger()"
        >
          {{ downloading() ? 'Preparing…' : 'Export ledger (.xlsx)' }}
        </button>
      </div>
    </div>

    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    <div class="card" style="margin-bottom: 1.25rem">
      <div class="grid grid-2">
        <div class="field" style="margin-bottom: 0">
          <label for="term">Session and term</label>
          <select id="term" [ngModel]="termId()" (ngModelChange)="selectTerm($event)">
            @for (term of terms(); track term.id) {
              <option [ngValue]="term.id">{{ term.session_name }} · {{ term.name }}</option>
            }
          </select>
        </div>
        <div class="field" style="margin-bottom: 0">
          <label>Students</label>
          <input
            [value]="(summary()?.billed_student_count ?? 0) + ' billed'"
            readonly
          />
        </div>
      </div>
    </div>

    @if (summary(); as totals) {
      <div class="grid grid-4" style="margin-bottom: 1.25rem">
        <div class="stat">
          <p class="muted small">Total expected</p>
          <p class="value" style="font-size: 1.5rem">{{ money(totals.total_expected) }}</p>
        </div>
        <div class="stat">
          <p class="muted small">Collected</p>
          <p class="value" style="font-size: 1.5rem">{{ money(totals.total_collected) }}</p>
        </div>
        <div class="stat">
          <p class="muted small">Outstanding</p>
          <p class="value" style="font-size: 1.5rem">{{ money(totals.outstanding) }}</p>
        </div>
        <div class="stat">
          <p class="muted small">Debtors</p>
          <p class="value" style="font-size: 1.5rem">{{ totals.debtor_count }}</p>
        </div>
      </div>

      <p class="muted small" style="margin-bottom: 1.25rem">
        {{ totals.fully_paid_count }} fully paid · {{ totals.partial_count }} part payment ·
        {{ totals.unpaid_count }} unpaid · {{ totals.student_count }} students on roll
      </p>
    }

    <div class="card">
      <div class="card-head">
        <h2 style="font-size: 1rem">Debtors</h2>
        <div class="row-actions">
          <input
            type="search"
            placeholder="Search name, admission or phone"
            aria-label="Search debtors"
            style="max-width: 260px"
            [ngModel]="search()"
            (ngModelChange)="onSearch($event)"
          />
        </div>
      </div>

      @if (rows().length) {
        <div class="table-shell">
          <p class="scroll-hint">Swipe sideways to see every balance →</p>
          <div class="table-wrap" appScrollHint>
          <table>
            <thead>
              <tr>
                <th>Student</th>
                <th>Class</th>
                <th>Billed</th>
                <th>Paid</th>
                <th>Outstanding</th>
                <th>Guardian</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              @for (row of rows(); track row.student) {
                <tr>
                  <td style="font-weight: 600">
                    {{ row.full_name }}
                    <p class="muted small" style="font-weight: 400">
                      {{ row.admission_number || '—' }}
                    </p>
                  </td>
                  <td class="muted">{{ row.class_name || '—' }}</td>
                  <td>{{ money(row.expected) }}</td>
                  <td>{{ money(row.paid) }}</td>
                  <td style="font-weight: 600">{{ money(row.balance) }}</td>
                  <td class="muted small">{{ guardianFor(row) }}</td>
                  <td>
                    <span class="badge" [class]="statusClass(row.status)">{{ labelFor(row.status) }}</span>
                  </td>
                </tr>
              }
            </tbody>
          </table>
          </div>
        </div>

        <div class="row-actions" style="justify-content: space-between; margin-top: 1rem">
          <span class="muted small">
            {{ total() }} debtor{{ total() === 1 ? '' : 's' }} · page {{ page() }}
          </span>
          <div class="row-actions">
            <button
              class="btn btn-ghost btn-sm"
              type="button"
              [disabled]="!hasPrevious() || loading()"
              (click)="go(page() - 1)"
            >
              Previous
            </button>
            <button
              class="btn btn-ghost btn-sm"
              type="button"
              [disabled]="!hasNext() || loading()"
              (click)="go(page() + 1)"
            >
              Next
            </button>
          </div>
        </div>
      } @else if (!loading()) {
        <p class="empty">
          @if (search()) {
            No debtor matches “{{ search() }}”.
          } @else {
            Every billed student has paid in full for this term.
          }
        </p>
      } @else {
        <p class="empty">Loading debtors…</p>
      }
    </div>
  `,
})
export class StaffFinance {
  private readonly api = inject(ApiService);

  readonly terms = signal<Term[]>([]);
  readonly termId = signal<number | null>(null);
  readonly summary = signal<FinanceSummary | null>(null);
  readonly rows = signal<Debtor[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly search = signal('');
  readonly hasNext = signal(false);
  readonly hasPrevious = signal(false);
  readonly loading = signal(false);
  readonly downloading = signal(false);
  readonly error = signal('');
  readonly money = naira;

  readonly term = computed(() => this.terms().find((row) => row.id === this.termId()) ?? null);

  private searchTimer: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    this.api.list<Term>('terms').subscribe({
      next: (rows) => {
        const ordered = rows
          .slice()
          .sort((a, b) => b.session_name.localeCompare(a.session_name) || b.name.localeCompare(a.name));
        this.terms.set(ordered);
        const current = ordered.find((term) => term.is_current) ?? ordered[0];
        if (current) {
          this.termId.set(current.id);
          this.load();
        }
      },
      error: () => this.error.set('Could not load terms.'),
    });
  }

  selectTerm(id: number): void {
    this.termId.set(id);
    this.page.set(1);
    this.search.set('');
    this.load();
  }

  onSearch(value: string): void {
    this.search.set(value);
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.page.set(1);
      this.loadDebtors();
    }, 300);
  }

  go(page: number): void {
    this.page.set(Math.max(1, page));
    this.loadDebtors();
  }

  guardianFor(row: Debtor): string {
    const guardian = row.guardians.find((entry) => entry.phone) ?? row.guardians[0];
    if (!guardian) {
      return 'No guardian on file';
    }
    return guardian.phone ? `${guardian.name} · ${guardian.phone}` : guardian.name;
  }

  statusClass(status: string): string {
    if (status === 'paid') {
      return 'badge-success';
    }
    if (status === 'partial') {
      return 'badge-warning';
    }
    if (status === 'no_fees') {
      return 'badge-info';
    }
    return 'badge-danger';
  }

  labelFor(status: string): string {
    if (status === 'partial') {
      return 'Part payment';
    }
    if (status === 'no_fees') {
      return 'No fees';
    }
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  exportLedger(): void {
    const term = this.term();
    if (!term) {
      return;
    }
    this.downloading.set(true);
    this.error.set('');
    this.api
      .download('finance/ledger', { session: term.session, term: term.id, format: 'xlsx' })
      .subscribe({
        next: (blob) => {
          this.downloading.set(false);
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = `fee-ledger-${this.slug(term.session_name)}-${this.slug(term.name)}.xlsx`;
          anchor.click();
          URL.revokeObjectURL(url);
        },
        error: () => {
          this.downloading.set(false);
          this.error.set('Could not export the ledger. Try again in a moment.');
        },
      });
  }

  private load(): void {
    this.loadSummary();
    this.loadDebtors();
  }

  private loadSummary(): void {
    const term = this.term();
    if (!term) {
      return;
    }
    this.api
      .get<FinanceSummary>('finance/summary', { session: term.session, term: term.id })
      .subscribe({
        next: (summary) => this.summary.set(summary),
        error: () => this.error.set('Could not load the fee summary for that term.'),
      });
  }

  private loadDebtors(): void {
    const term = this.term();
    if (!term) {
      return;
    }
    this.loading.set(true);
    this.api
      .get<Paged<Debtor>>('finance/debtors', {
        session: term.session,
        term: term.id,
        page: this.page(),
        search: this.search().trim() || undefined,
      })
      .subscribe({
        next: (body) => {
          this.loading.set(false);
          this.rows.set(body.results);
          this.total.set(body.count);
          this.hasNext.set(Boolean(body.next));
          this.hasPrevious.set(Boolean(body.previous));
        },
        error: () => {
          this.loading.set(false);
          this.error.set('Could not load the debtors list.');
        },
      });
  }

  private slug(value: string): string {
    return value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '');
  }
}
