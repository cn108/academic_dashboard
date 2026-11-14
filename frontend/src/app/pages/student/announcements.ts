import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';

import { ApiService } from '../../core/api.service';
import { Announcement } from '../../core/models';

@Component({
  selector: 'app-student-announcements',
  imports: [DatePipe],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Student portal</p>
        <h1>Announcements</h1>
        <p class="muted small">Notices from the school and your class teacher.</p>
      </div>
    </div>

    <div class="grid">
      @for (item of announcements(); track item.id) {
        <div class="card">
          <div class="card-head">
            <h2 style="font-size: 1rem">{{ item.title }}</h2>
            <div class="row-actions">
              <span class="badge badge-info">{{ item.audience }}</span>
              <span class="small muted">{{ item.created_at | date: 'mediumDate' }}</span>
            </div>
          </div>
          <p class="small" style="white-space: pre-line">{{ item.body }}</p>
          @if (item.author) {
            <p class="small muted" style="margin-top: 0.6rem">Posted by {{ item.author }}</p>
          }
        </div>
      } @empty {
        <div class="card"><p class="empty">No announcements yet.</p></div>
      }
    </div>
  `,
})
export class StudentAnnouncements {
  private readonly api = inject(ApiService);

  readonly announcements = signal<Announcement[]>([]);

  constructor() {
    this.api
      .list<Announcement>('announcements')
      .subscribe((rows) => this.announcements.set(rows));
  }
}
