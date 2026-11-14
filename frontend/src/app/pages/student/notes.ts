import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';

import { ApiService } from '../../core/api.service';
import { LessonNote } from '../../core/models';

@Component({
  selector: 'app-student-notes',
  imports: [DatePipe],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Student portal</p>
        <h1>Lesson notes</h1>
        <p class="muted small">Weekly topics your teachers have published for your class.</p>
      </div>
    </div>

    <div class="grid grid-2">
      @for (note of notes(); track note.id) {
        <div class="card">
          <div class="card-head">
            <div>
              <p class="small muted">{{ note.subject_name }}</p>
              <h2 style="font-size: 1rem">Week {{ note.week_number }} · {{ note.topic }}</h2>
            </div>
            <span class="badge badge-info">{{ note.term_name || 'This term' }}</span>
          </div>
          <p class="small" style="white-space: pre-line">{{ note.content || 'No written content.' }}</p>
          <div class="row-actions" style="margin-top: 0.9rem">
            @if (note.attachment) {
              <a class="btn btn-ghost btn-sm" [href]="note.attachment" target="_blank" rel="noopener">
                Open attachment
              </a>
            }
            <span class="small muted">Added {{ note.created_at | date: 'mediumDate' }}</span>
          </div>
        </div>
      } @empty {
        <div class="card"><p class="empty">No lesson notes published yet.</p></div>
      }
    </div>
  `,
})
export class StudentNotes {
  private readonly api = inject(ApiService);

  readonly notes = signal<LessonNote[]>([]);

  constructor() {
    this.api
      .list<LessonNote>('lesson-notes')
      .subscribe((rows) => this.notes.set(rows.slice().reverse()));
  }
}
