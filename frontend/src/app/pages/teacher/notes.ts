import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { CurrentTerm, LessonNote, statusTone, Subject, uploadProblem } from '../../core/models';

@Component({
  selector: 'app-teacher-notes',
  imports: [FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Teacher portal</p>
        <h1>Lesson notes</h1>
        <p class="muted small">Write a week's content, keep it as a draft, publish when ready.</p>
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
        <div class="card-head"><h2 style="font-size: 1rem">New note</h2></div>
        <div class="field">
          <label for="subject">Subject</label>
          <select id="subject" [(ngModel)]="draft.subject">
            @for (subject of subjects(); track subject.id) {
              <option [ngValue]="subject.id">{{ subject.name }}</option>
            }
          </select>
        </div>
        <div class="field">
          <label for="week">Week</label>
          <input id="week" type="number" min="1" max="13" [(ngModel)]="draft.week_number" />
        </div>
        <div class="field">
          <label for="topic">Topic</label>
          <input id="topic" [(ngModel)]="draft.topic" />
        </div>
        <div class="field">
          <label for="content">Content</label>
          <textarea id="content" rows="5" [(ngModel)]="draft.content"></textarea>
        </div>
        <div class="field">
          <label for="attachment">Attachment (optional)</label>
          <input
            id="attachment"
            type="file"
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
            (change)="onFile($event)"
          />
          <p class="small muted" style="margin-top: 0.35rem">PDF, Word or image · up to 5 MB.</p>
          @if (file()) {
            <p class="small" style="margin-top: 0.35rem">Attached: {{ file()!.name }}</p>
          }
        </div>
        <div class="field">
          <label for="status">Visibility</label>
          <select id="status" [(ngModel)]="draft.status">
            <option value="draft">Save as draft</option>
            <option value="published">Publish to students</option>
          </select>
        </div>
        <button class="btn" type="button" [disabled]="busy()" (click)="create()">
          {{ busy() ? 'Saving…' : 'Save note' }}
        </button>
      </div>

      <div class="card">
        <div class="card-head"><h2 style="font-size: 1rem">Your notes</h2></div>
        @if (notes().length) {
          <div class="grid">
            @for (note of notes(); track note.id) {
              <div class="card" style="box-shadow: none; background: rgba(9, 14, 26, 0.5)">
                <div class="card-head" style="margin-bottom: 0.4rem">
                  <div>
                    <p class="small muted">{{ note.subject_name }}</p>
                    <h3 style="font-size: 0.98rem">Week {{ note.week_number }} · {{ note.topic }}</h3>
                  </div>
                  <span class="badge" [class]="tone(note.status)">{{ note.status }}</span>
                </div>
                <p class="small muted">{{ note.content }}</p>
                @if (note.attachment) {
                  <a class="small" [href]="note.attachment" target="_blank" rel="noopener">Open attachment</a>
                }
                <div class="row-actions" style="margin-top: 0.6rem">
                  @if (note.status !== 'published') {
                    <button class="btn btn-sm" type="button" (click)="publish(note)">Publish</button>
                  }
                  @if (note.status !== 'archived') {
                    <button class="btn btn-ghost btn-sm" type="button" (click)="archive(note)">Archive</button>
                  }
                </div>
              </div>
            }
          </div>
        } @else {
          <p class="empty">No notes written yet.</p>
        }
      </div>
    </div>
  `,
})
export class TeacherNotes {
  private readonly api = inject(ApiService);

  readonly subjects = signal<Subject[]>([]);
  readonly notes = signal<LessonNote[]>([]);
  readonly current = signal<CurrentTerm | null>(null);
  readonly message = signal('');
  readonly error = signal('');
  readonly busy = signal(false);
  readonly file = signal<File | null>(null);

  draft = {
    subject: null as number | null,
    week_number: 1,
    topic: '',
    content: '',
    status: 'draft',
  };

  constructor() {
    this.api.get<CurrentTerm>('terms/current').subscribe((payload) => this.current.set(payload));
    this.api.list<Subject>('subjects').subscribe((rows) => {
      this.subjects.set(rows);
      if (rows.length && this.draft.subject === null) {
        this.draft.subject = rows[0].id;
      }
    });
    this.load();
  }

  load(): void {
    this.api.list<LessonNote>('lesson-notes').subscribe((rows) => this.notes.set(rows));
  }

  tone(status: string): string {
    return statusTone(status as never);
  }

  create(): void {
    if (!this.draft.subject || !this.draft.topic.trim()) {
      this.error.set('Choose a subject and give the note a topic.');
      return;
    }
    const term = this.current()?.term.id ?? null;
    const file = this.file();

    const handle = {
      next: () => {
        this.busy.set(false);
        this.message.set('Lesson note saved.');
        this.draft = { ...this.draft, topic: '', content: '', week_number: this.draft.week_number + 1 };
        this.file.set(null);
        this.load();
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(this.describe(error));
      },
    };

    this.busy.set(true);
    this.error.set('');

    if (file) {
      const form = new FormData();
      form.append('subject', String(this.draft.subject));
      form.append('week_number', String(this.draft.week_number));
      form.append('topic', this.draft.topic);
      form.append('content', this.draft.content);
      form.append('status', this.draft.status);
      if (term !== null) {
        form.append('term', String(term));
      }
      form.append('attachment', file);
      this.api.upload<LessonNote>('lesson-notes', form).subscribe(handle);
      return;
    }

    this.api.create<LessonNote>('lesson-notes', { ...this.draft, term }).subscribe(handle);
  }

  onFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    if (!file) {
      this.file.set(null);
      return;
    }
    const problem = uploadProblem(file);
    if (problem) {
      input.value = '';
      this.file.set(null);
      this.error.set(problem);
      return;
    }
    this.error.set('');
    this.file.set(file);
  }

  publish(note: LessonNote): void {
    this.api.action<LessonNote>(`lesson-notes/${note.id}/publish`).subscribe({
      next: () => {
        this.message.set(`Published week ${note.week_number}.`);
        this.load();
      },
      error: (error) => this.error.set(this.describe(error)),
    });
  }

  archive(note: LessonNote): void {
    this.api.action<LessonNote>(`lesson-notes/${note.id}/archive`).subscribe({
      next: () => {
        this.message.set(`Archived week ${note.week_number}.`);
        this.load();
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
    return 'Could not save that note.';
  }
}
