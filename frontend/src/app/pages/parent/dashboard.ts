import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { ParentWardsResponse, Ward } from '../../core/models';

@Component({
  selector: 'app-parent-dashboard',
  imports: [RouterLink],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Parent portal</p>
        <h1>My children</h1>
        <p class="muted small">
          A current-term snapshot of every ward linked to your account.
        </p>
      </div>
      @if (term(); as current) {
        <span class="badge badge-info">{{ current.session_name }} · {{ current.name }}</span>
      }
    </div>

    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    @if (wards().length) {
      <div class="grid grid-3">
        @for (ward of wards(); track ward.id) {
          <div class="card">
            <div class="card-head">
              <h2 style="font-size: 1rem">{{ ward.full_name }}</h2>
              <span class="badge badge-info">{{ ward.relationship }}</span>
            </div>
            <p class="muted small" style="margin-top: 0">
              {{ ward.class_name || 'No class yet' }}
              @if (ward.admission_number) {
                · {{ ward.admission_number }}
              }
            </p>

            <div class="grid grid-2" style="margin: 0.9rem 0">
              <div>
                <p class="muted small" style="margin: 0">Term average</p>
                <p style="font-size: 1.7rem; font-weight: 600; margin: 0.2rem 0">
                  {{ ward.average === null ? '—' : ward.average }}
                </p>
                <p class="small muted">
                  {{ ward.subjects_count }} published subject{{ ward.subjects_count === 1 ? '' : 's' }}
                </p>
              </div>
              <div>
                <p class="muted small" style="margin: 0">Attendance</p>
                <p style="font-size: 1.7rem; font-weight: 600; margin: 0.2rem 0">
                  {{ ward.attendance_rate === null ? '—' : ward.attendance_rate + '%' }}
                </p>
                <p class="small muted">last 30 days · {{ ward.attendance_days }} marked</p>
              </div>
            </div>

            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap">
              <a class="btn btn-ghost btn-sm" routerLink="/parent/results">Report cards</a>
              <a class="btn btn-ghost btn-sm" routerLink="/parent/fees">Fees &amp; payments</a>
            </div>
          </div>
        }
      </div>
    } @else if (loaded()) {
      <p class="empty">
        No children are linked to this account yet. Ask the school office to connect your wards.
      </p>
    }
  `,
})
export class ParentDashboard {
  private readonly api = inject(ApiService);

  readonly wards = signal<Ward[]>([]);
  readonly term = signal<ParentWardsResponse['term']>(null);
  readonly loaded = signal(false);
  readonly error = signal('');

  constructor() {
    this.api.get<ParentWardsResponse>('parent/wards').subscribe({
      next: (body) => {
        this.wards.set(body.wards);
        this.term.set(body.term);
        this.loaded.set(true);
      },
      error: () => {
        this.error.set('Could not load your children right now. Try again in a moment.');
        this.loaded.set(true);
      },
    });
  }
}
