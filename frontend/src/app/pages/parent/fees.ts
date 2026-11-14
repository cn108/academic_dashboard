import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import {
  feeTone,
  naira,
  ParentFee,
  ParentFeesResponse,
  ParentPayment,
  PaymentInit,
  Term,
} from '../../core/models';

type Tab = 'fees' | 'history';

@Component({
  selector: 'app-parent-fees',
  imports: [FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Parent portal</p>
        <h1>Fees &amp; payments</h1>
        <p class="muted small">
          Pay outstanding fees securely with Paystack. Balances update as soon as Paystack confirms.
        </p>
      </div>
    </div>

    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }
    @if (notice()) {
      <div class="alert alert-success">{{ notice() }}</div>
    }

    <div class="card" style="margin-bottom: 1.25rem">
      <div class="grid grid-2">
        <div class="field" style="margin-bottom: 0">
          <label for="term">Term</label>
          <select id="term" [ngModel]="termId()" (ngModelChange)="selectTerm($event)">
            @for (term of terms(); track term.id) {
              <option [ngValue]="term.id">{{ term.session_name }} · {{ term.name }}</option>
            }
          </select>
        </div>
        <div class="field" style="margin-bottom: 0">
          <label>View</label>
          <div style="display: flex; gap: 0.5rem">
            <button
              class="btn btn-ghost btn-sm"
              type="button"
              [style.opacity]="tab() === 'fees' ? '1' : '0.6'"
              (click)="show('fees')"
            >
              Fees
            </button>
            <button
              class="btn btn-ghost btn-sm"
              type="button"
              [style.opacity]="tab() === 'history' ? '1' : '0.6'"
              (click)="show('history')"
            >
              Payment history
            </button>
          </div>
        </div>
      </div>
    </div>

    @if (tab() === 'fees') {
      @if (totals(); as summary) {
        <div class="grid grid-3" style="margin-bottom: 1.25rem">
          <div class="stat">
            <p class="muted small">Total billed</p>
            <p class="value" style="font-size: 1.4rem">{{ money(summary.amount) }}</p>
          </div>
          <div class="stat">
            <p class="muted small">Paid</p>
            <p class="value" style="font-size: 1.4rem">{{ money(summary.amount_paid) }}</p>
          </div>
          <div class="stat">
            <p class="muted small">Outstanding</p>
            <p class="value" style="font-size: 1.4rem">{{ money(summary.balance) }}</p>
          </div>
        </div>
      }

      <div class="card">
        <div class="card-head">
          <h2 style="font-size: 1rem">Term fees</h2>
          <span class="badge badge-info">{{ termLabel() || 'No term selected' }}</span>
        </div>

        @if (fees().length) {
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Child</th>
                  <th>Fee</th>
                  <th>Amount</th>
                  <th>Paid</th>
                  <th>Balance</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                @for (fee of fees(); track fee.id) {
                  <tr>
                    <td style="font-weight: 600">{{ fee.student_name }}</td>
                    <td class="muted">{{ fee.description }}</td>
                    <td>{{ money(fee.amount) }}</td>
                    <td>{{ money(fee.amount_paid) }}</td>
                    <td>{{ money(fee.balance) }}</td>
                    <td>
                      <span class="badge" [class]="tone(fee.status)">{{ fee.status }}</span>
                    </td>
                    <td style="text-align: right">
                      <button
                        class="btn btn-sm"
                        type="button"
                        [disabled]="fee.balance === '0.00' || busyId() === fee.id"
                        (click)="pay(fee)"
                      >
                        {{ busyId() === fee.id ? 'Opening…' : 'Pay now' }}
                      </button>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="empty">No fees have been set for this term yet.</p>
        }
      </div>
    } @else {
      <div class="card">
        <div class="card-head">
          <h2 style="font-size: 1rem">Payment history</h2>
          <span class="badge badge-info">{{ payments().length }} transaction(s)</span>
        </div>

        @if (payments().length) {
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Child</th>
                  <th>Fee</th>
                  <th>Amount</th>
                  <th>Reference</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                @for (payment of payments(); track payment.id) {
                  <tr>
                    <td class="muted">{{ day(payment.paid_at || payment.created_at) }}</td>
                    <td style="font-weight: 600">{{ payment.student_name }}</td>
                    <td class="muted">{{ payment.description }}</td>
                    <td>{{ money(payment.amount) }}</td>
                    <td class="muted small">{{ payment.reference }}</td>
                    <td>
                      <span class="badge" [class]="statusTone(payment.status)">{{ payment.status }}</span>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="empty">No payments yet. Paid fees will appear here.</p>
        }
      </div>
    }
  `,
})
export class ParentFees {
  private readonly api = inject(ApiService);

  readonly tab = signal<Tab>('fees');
  readonly terms = signal<Term[]>([]);
  readonly termId = signal<number | null>(null);
  readonly fees = signal<ParentFee[]>([]);
  readonly totals = signal<ParentFeesResponse['totals'] | null>(null);
  readonly payments = signal<ParentPayment[]>([]);
  readonly busyId = signal<number | null>(null);
  readonly error = signal('');
  readonly notice = signal('');
  readonly money = naira;

  readonly termLabel = computed(() => {
    const term = this.terms().find((row) => row.id === this.termId());
    return term ? `${term.session_name} · ${term.name}` : '';
  });

  constructor() {
    this.api.list<Term>('terms').subscribe((rows) => {
      const ordered = rows
        .slice()
        .sort((a, b) => b.session_name.localeCompare(a.session_name) || b.name.localeCompare(a.name));
      this.terms.set(ordered);
      const current = ordered.find((term) => term.is_current) ?? ordered[0];
      if (current) {
        this.termId.set(current.id);
        this.loadFees();
      }
    });

    this.loadPayments();

    if (new URLSearchParams(window.location.search).has('reference')) {
      this.notice.set(
        'Welcome back from Paystack. Your payment appears below once Paystack confirms it.',
      );
    }
  }

  show(tab: Tab): void {
    this.tab.set(tab);
    if (tab === 'history') {
      this.loadPayments();
    }
  }

  selectTerm(id: number): void {
    this.termId.set(id);
    this.error.set('');
    this.loadFees();
  }

  tone(status: string): string {
    return feeTone(status);
  }

  statusTone(status: string): string {
    if (status === 'success') {
      return 'badge-success';
    }
    if (status === 'failed') {
      return 'badge-danger';
    }
    return 'badge-warning';
  }

  day(value: string | null): string {
    if (!value) {
      return '—';
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? '—'
      : date.toLocaleDateString('en-NG', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  pay(fee: ParentFee): void {
    this.error.set('');
    this.notice.set('');
    this.busyId.set(fee.id);

    this.api.action<PaymentInit>('payments/initialize', { student_fee_id: fee.id }).subscribe({
      next: (response) => {
        window.location.assign(response.authorization_url);
      },
      error: (response: { error?: { detail?: string } }) => {
        this.busyId.set(null);
        this.error.set(
          response.error?.detail ?? 'Could not start the payment. Check your connection and try again.',
        );
      },
    });
  }

  private loadFees(): void {
    const id = this.termId();
    if (!id) {
      return;
    }
    this.api.get<ParentFeesResponse>('parent/fees', { term: id }).subscribe({
      next: (body) => {
        this.fees.set(body.fees);
        this.totals.set(body.totals);
      },
      error: () => this.error.set('Could not load fees. Try again in a moment.'),
    });
  }

  private loadPayments(): void {
    this.api.get<{ payments: ParentPayment[] }>('parent/payments').subscribe({
      next: (body) => this.payments.set(body.payments),
      error: () => this.error.set('Could not load your payment history.'),
    });
  }
}
