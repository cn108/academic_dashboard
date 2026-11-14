import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { Announcement, SchoolClass, statusTone } from '../../core/models';

@Component({
  selector: 'app-teacher-announcements',
  imports: [DatePipe, FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Teacher portal</p>
        <h1>Announcements</h1>
        <p class="muted small">Post to your class or the whole school. Drafts stay private.</p>
      </div>
    </div>

    @if (message()) {
      <div class="alert alert-success">{{ message() }}</div>
    }
    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    <div class="split">
      <div class="card">
        <div class="card-head">
          <h2 style="font-size: 1rem">{{ editingId() ? 'Edit notice' : 'New notice' }}</h2>
          @if (editingId()) {
            <button class="btn btn-ghost btn-sm" type="button" (click)="cancelEdit()">Cancel</button>
          }
        </div>
        <div class="field">
          <label for="title">Title</label>
          <input id="title" [(ngModel)]="draft.title" />
        </div>
        <div class="field">
          <label for="body">Message</label>
          <textarea id="body" rows="4" [(ngModel)]="draft.body"></textarea>
        </div>
        <div class="field">
          <label for="audience">Audience</label>
          <select id="audience" [(ngModel)]="draft.school_class">
            <option [ngValue]="null">Whole school</option>
            @for (room of classes(); track room.id) {
              <option [ngValue]="room.id">{{ room.name }}</option>
            }
          </select>
        </div>
        <div class="field">
          <label for="status">Visibility</label>
          <select id="status" [(ngModel)]="draft.status">
            <option value="draft">Save as draft</option>
            <option value="published">Publish</option>
          </select>
        </div>
        <button class="btn" type="button" [disabled]="busy()" (click)="save()">
          {{ busy() ? 'Saving…' : editingId() ? 'Save changes' : 'Save announcement' }}
        </button>
      </div>

      <div class="card">
        <div class="card-head"><h2 style="font-size: 1rem">Posted</h2></div>
        @if (announcements().length) {
          <div class="grid">
            @for (item of announcements(); track item.id) {
              <div class="card" style="box-shadow: none; background: rgba(9, 14, 26, 0.5)">
                <div class="card-head" style="margin-bottom: 0.4rem">
                  <div>
                    <h3 style="font-size: 0.98rem">{{ item.title }}</h3>
                    <p class="small muted">{{ item.audience }} · {{ item.created_at | date: 'mediumDate' }}</p>
                  </div>
                  <span class="badge" [class]="tone(item.status)">{{ item.status }}</span>
                </div>
                <p class="small">{{ item.body }}</p>
                <div class="row-actions" style="margin-top: 0.6rem">
                  <button class="btn btn-ghost btn-sm" type="button" (click)="startEdit(item)">Edit</button>
                  @if (item.status !== 'published') {
                    <button class="btn btn-sm" type="button" (click)="publish(item)">Publish</button>
                  }
                  @if (item.status !== 'archived') {
                    <button class="btn btn-ghost btn-sm" type="button" (click)="archive(item)">Archive</button>
                  }
                </div>
              </div>
            }
          </div>
        } @else {
          <p class="empty">Nothing posted yet.</p>
        }
      </div>
    </div>
  `,
})
export class TeacherAnnouncements {
  private readonly api = inject(ApiService);

  readonly classes = signal<SchoolClass[]>([]);
  readonly announcements = signal<Announcement[]>([]);
  readonly message = signal('');
  readonly error = signal('');
  readonly busy = signal(false);
  readonly editingId = signal<number | null>(null);

  draft = {
    title: '',
    body: '',
    school_class: null as number | null,
    status: 'draft',
  };

  constructor() {
    this.api.list<SchoolClass>('classes').subscribe((rows) => this.classes.set(rows));
    this.load();
  }

  load(): void {
    this.api.list<Announcement>('announcements').subscribe((rows) => this.announcements.set(rows));
  }

  tone(status: string): string {
    return statusTone(status as never);
  }

  startEdit(item: Announcement): void {
    this.editingId.set(item.id);
    this.draft = {
      title: item.title,
      body: item.body,
      school_class: item.school_class,
      status: item.status,
    };
    this.message.set('');
    this.error.set('');
  }

  cancelEdit(): void {
    this.editingId.set(null);
    this.draft = { title: '', body: '', school_class: null, status: 'draft' };
    this.error.set('');
  }

  save(): void {
    if (!this.draft.title.trim() || !this.draft.body.trim()) {
      this.error.set('A title and message are required.');
      return;
    }

    const editingId = this.editingId();
    const request = editingId
      ? this.api.update<Announcement>(`announcements/${editingId}`, this.draft)
      : this.api.create<Announcement>('announcements', this.draft);

    this.busy.set(true);
    this.error.set('');
    request.subscribe({
      next: () => {
        this.busy.set(false);
        this.message.set(editingId ? 'Announcement updated.' : 'Announcement saved.');
        this.editingId.set(null);
        this.draft = { ...this.draft, title: '', body: '' };
        this.load();
      },
      error: (error) => {
        this.busy.set(false);
        const body = (error as { error?: Record<string, string[]> }).error;
        const messages = body && typeof body === 'object' ? Object.values(body).flat() : [];
        this.error.set(messages[0] ?? 'Could not save that announcement.');
      },
    });
  }

  publish(item: Announcement): void {
    this.api.action<Announcement>(`announcements/${item.id}/publish`).subscribe({
      next: () => {
        this.message.set(`Published “${item.title}”.`);
        this.load();
      },
      error: () => this.error.set('Could not publish that announcement.'),
    });
  }

  archive(item: Announcement): void {
    this.api.action<Announcement>(`announcements/${item.id}/archive`).subscribe({
      next: () => {
        this.message.set(`Archived “${item.title}”.`);
        this.load();
      },
      error: () => this.error.set('Could not archive that announcement.'),
    });
  }
}
