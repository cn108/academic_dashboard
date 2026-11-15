import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { ApiService } from '../../core/api.service';
import {
  Quiz,
  QuizAttemptsResponse,
  QuizQuestion,
  quizTone,
  Subject,
} from '../../core/models';

interface Draft {
  text: string;
  options: string[];
  correct: number;
  points: number;
}

function blankDraft(): Draft {
  return { text: '', options: ['', '', '', ''], correct: 0, points: 1 };
}

@Component({
  selector: 'app-teacher-quizzes',
  imports: [FormsModule],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Teacher portal</p>
        <h1>Quizzes</h1>
        <p class="muted small">
          Timed multiple-choice checks. Students only see a quiz once it is published.
        </p>
      </div>
      <div class="row-actions">
        <button class="btn" type="button" (click)="newQuiz()">New quiz</button>
      </div>
    </div>

    @if (message()) {
      <div class="alert alert-success">{{ message() }}</div>
    }
    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    @if (formOpen()) {
      <div class="card" style="margin-bottom: 1.25rem">
        <div class="card-head">
          <h2 style="font-size: 1rem">{{ editingId() ? 'Edit quiz' : 'New quiz' }}</h2>
          <button class="btn btn-ghost btn-sm" type="button" (click)="formOpen.set(false)">
            Cancel
          </button>
        </div>

        <div class="grid grid-2">
          <div class="field">
            <label for="quiz-title">Title</label>
            <input id="quiz-title" maxlength="200" [(ngModel)]="title" />
          </div>
          <div class="field">
            <label for="quiz-subject">Subject</label>
            <select id="quiz-subject" [(ngModel)]="subjectId">
              @for (subject of subjects(); track subject.id) {
                <option [ngValue]="subject.id">{{ subject.name }} · {{ subject.class_name }}</option>
              }
            </select>
          </div>
          <div class="field">
            <label for="quiz-limit">Time limit (minutes)</label>
            <input id="quiz-limit" type="number" min="1" max="180" [(ngModel)]="timeLimit" />
          </div>
          <div class="field">
            <label for="quiz-from">Available from (optional)</label>
            <input id="quiz-from" type="datetime-local" [(ngModel)]="availableFrom" />
          </div>
          <div class="field">
            <label for="quiz-until">Available until (optional)</label>
            <input id="quiz-until" type="datetime-local" [(ngModel)]="availableUntil" />
          </div>
        </div>

        <button class="btn" type="button" [disabled]="saving()" (click)="saveQuiz()">
          {{ saving() ? 'Saving…' : editingId() ? 'Save changes' : 'Create quiz' }}
        </button>
      </div>
    }

    <div class="card" style="margin-bottom: 1.25rem">
      <div class="card-head">
        <h2 style="font-size: 1rem">My quizzes</h2>
        <span class="badge badge-info">{{ quizzes().length }}</span>
      </div>

      @if (quizzes().length) {
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Subject</th>
                <th>Status</th>
                <th>Time</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (quiz of quizzes(); track quiz.id) {
                <tr>
                  <td style="font-weight: 600">
                    {{ quiz.title }}
                    <p class="muted small" style="font-weight: 400">
                      {{ quiz.questions_count }} questions · {{ quiz.total_points }} points
                    </p>
                  </td>
                  <td class="muted">{{ quiz.subject_name }}</td>
                  <td>
                    <span class="badge" [class]="tone(quiz.status)">{{ quiz.status }}</span>
                  </td>
                  <td>{{ quiz.time_limit_minutes }} min</td>
                  <td>
                    <div class="row-actions">
                      <button class="btn btn-ghost btn-sm" type="button" (click)="select(quiz)">
                        Questions
                      </button>
                      @if (quiz.status !== 'published') {
                        <button
                          class="btn btn-ghost btn-sm"
                          type="button"
                          [disabled]="!quiz.questions_count"
                          (click)="publish(quiz)"
                        >
                          Publish
                        </button>
                      } @else {
                        <button class="btn btn-ghost btn-sm" type="button" (click)="close(quiz)">
                          Close
                        </button>
                      }
                      <button class="btn btn-ghost btn-sm" type="button" (click)="edit(quiz)">
                        Edit
                      </button>
                      @if (quiz.status !== 'draft') {
                        <button class="btn btn-ghost btn-sm" type="button" (click)="results(quiz)">
                          Results
                        </button>
                      }
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="empty">No quizzes yet. Create one to get started.</p>
      }
    </div>

    @if (selected(); as quiz) {
      <div class="grid grid-2">
        <div class="card">
          <div class="card-head">
            <div>
              <p class="eyebrow">Question bank</p>
              <h2 style="font-size: 1rem">{{ quiz.title }}</h2>
              <p class="muted small">
                {{ quiz.questions_count }} saved · {{ quiz.total_points }} points
              </p>
            </div>
            <button class="btn btn-ghost btn-sm" type="button" (click)="selected.set(null)">
              Close
            </button>
          </div>

          @if (quiz.questions.length) {
            <div class="grid">
              @for (question of quiz.questions; track question.id; let index = $index) {
                <div class="resource">
                  <p class="small muted">Question {{ index + 1 }} · {{ question.points }} pt</p>
                  <p style="font-weight: 600">{{ question.text }}</p>
                  <div class="grid" style="margin-top: 0.5rem">
                    @for (option of question.options; track $index; let choice = $index) {
                      <div
                        class="small"
                        [style.color]="
                          choice === question.correct_option_index ? 'var(--success)' : 'var(--muted)'
                        "
                      >
                        {{ choice + 1 }}. {{ option }}
                        @if (choice === question.correct_option_index) {
                          <span class="badge badge-success">correct</span>
                        }
                      </div>
                    }
                  </div>
                </div>
              }
            </div>
          } @else {
            <p class="empty">No questions yet. Add one on the right.</p>
          }
        </div>

        <div class="card">
          <div class="card-head">
            <h2 style="font-size: 1rem">Add questions</h2>
            <button class="btn btn-ghost btn-sm" type="button" (click)="addDraft()">
              Add question
            </button>
          </div>

          @if (drafts.length) {
            @for (draft of drafts; track $index; let index = $index) {
              <div class="resource">
                <div class="card-head" style="margin-bottom: 0.5rem">
                  <p class="small muted">New question {{ index + 1 }}</p>
                  <button class="btn btn-ghost btn-sm" type="button" (click)="removeDraft(index)">
                    Remove
                  </button>
                </div>

                <div class="field">
                  <label>Question text</label>
                  <textarea rows="2" [(ngModel)]="draft.text"></textarea>
                </div>

                <div class="grid grid-2 option-grid">
                  @for (option of draft.options; track $index; let choice = $index) {
                    <div class="field" style="margin-bottom: 0">
                      <label>
                        <input
                          type="radio"
                          [name]="'correct-' + index"
                          [checked]="draft.correct === choice"
                          (change)="draft.correct = choice"
                        />
                        Correct option {{ choice + 1 }}
                      </label>
                      <input
                        [placeholder]="'Option ' + (choice + 1)"
                        [ngModel]="option"
                        (ngModelChange)="setOption(draft, choice, $event)"
                      />
                    </div>
                  }
                </div>

                <div class="field" style="margin-top: 0.6rem; margin-bottom: 0">
                  <label>Points</label>
                  <input type="number" min="1" max="10" [(ngModel)]="draft.points" />
                </div>
              </div>
            }

            <button class="btn" type="button" [disabled]="saving()" (click)="saveQuestions(quiz)">
              {{ saving() ? 'Saving…' : 'Save questions' }}
            </button>
          } @else {
            <p class="empty">Add a question to build the quiz.</p>
          }
        </div>
      </div>
    }

    @if (attempts(); as data) {
      <div class="card" style="margin-top: 1.25rem">
        <div class="card-head">
          <div>
            <p class="eyebrow">Results</p>
            <h2 style="font-size: 1rem">{{ data.quiz.title }}</h2>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" (click)="attempts.set(null)">
            Close
          </button>
        </div>

        <div class="grid grid-3" style="margin-bottom: 1rem">
          <div class="stat">
            <p class="muted small">Class average</p>
            <p class="value" style="font-size: 1.5rem">
              {{ data.summary.average_percentage ?? '—' }}%
            </p>
          </div>
          <div class="stat">
            <p class="muted small">Passed</p>
            <p class="value" style="font-size: 1.5rem">{{ data.summary.passed }}</p>
          </div>
          <div class="stat">
            <p class="muted small">Graded</p>
            <p class="value" style="font-size: 1.5rem">
              {{ data.summary.graded }} / {{ data.summary.total }}
            </p>
          </div>
        </div>

        @if (data.attempts.length) {
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Admission</th>
                  <th>Score</th>
                  <th>Percentage</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                @for (row of data.attempts; track row.id) {
                  <tr>
                    <td style="font-weight: 600">{{ row.student_name }}</td>
                    <td class="muted">{{ row.admission_number || '—' }}</td>
                    <td>{{ row.score }} / {{ data.quiz.total_points }}</td>
                    <td>{{ row.percentage }}%</td>
                    <td>
                      @if (row.status === 'auto_graded') {
                        <span class="badge" [class]="row.passed ? 'badge-success' : 'badge-danger'">
                          {{ row.passed ? 'Pass' : 'Fail' }}
                        </span>
                      } @else {
                        <span class="badge badge-warning">In progress</span>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="empty">No student has attempted this quiz yet.</p>
        }
      </div>
    }
  `,
})
export class TeacherQuizzes {
  private readonly api = inject(ApiService);

  readonly quizzes = signal<Quiz[]>([]);
  readonly subjects = signal<Subject[]>([]);
  readonly selected = signal<Quiz | null>(null);
  readonly attempts = signal<QuizAttemptsResponse | null>(null);
  readonly formOpen = signal(false);
  readonly editingId = signal<number | null>(null);
  readonly saving = signal(false);
  readonly message = signal('');
  readonly error = signal('');

  title = '';
  subjectId: number | null = null;
  timeLimit = 10;
  availableFrom = '';
  availableUntil = '';
  drafts: Draft[] = [];

  constructor() {
    this.load();
    this.api.list<Subject>('subjects').subscribe({
      next: (rows) => {
        this.subjects.set(rows);
        if (this.subjectId === null && rows.length) {
          this.subjectId = rows[0].id;
        }
      },
      error: () => this.error.set('Could not load your subjects.'),
    });
  }

  tone(status: Quiz['status']): string {
    return quizTone(status);
  }

  newQuiz(): void {
    this.editingId.set(null);
    this.title = '';
    this.timeLimit = 10;
    this.availableFrom = '';
    this.availableUntil = '';
    this.subjectId = this.subjects()[0]?.id ?? null;
    this.formOpen.set(true);
    this.message.set('');
    this.error.set('');
  }

  edit(quiz: Quiz): void {
    this.editingId.set(quiz.id);
    this.title = quiz.title;
    this.subjectId = quiz.subject;
    this.timeLimit = quiz.time_limit_minutes;
    this.availableFrom = this.localInput(quiz.available_from);
    this.availableUntil = this.localInput(quiz.available_until);
    this.formOpen.set(true);
    this.message.set('');
    this.error.set('');
  }

  saveQuiz(): void {
    const subject = this.subjects().find((row) => row.id === this.subjectId);
    if (!this.title.trim() || !subject) {
      this.error.set('Give the quiz a title and choose its subject.');
      return;
    }

    const body = {
      title: this.title.trim(),
      subject: subject.id,
      class_arm: subject.school_class,
      time_limit_minutes: Number(this.timeLimit) || 10,
      available_from: this.iso(this.availableFrom),
      available_until: this.iso(this.availableUntil),
    };

    const editing = this.editingId();
    const request = editing
      ? this.api.update<Quiz>(`quizzes/${editing}`, body)
      : this.api.create<Quiz>('quizzes', body);

    this.saving.set(true);
    this.error.set('');
    request.subscribe({
      next: (quiz) => {
        this.saving.set(false);
        this.formOpen.set(false);
        this.message.set(editing ? 'Quiz updated.' : 'Quiz created. Add its questions next.');
        this.load();
        this.select(quiz);
      },
      error: (error) => {
        this.saving.set(false);
        this.error.set(this.describe(error));
      },
    });
  }

  select(quiz: Quiz): void {
    this.attempts.set(null);
    this.drafts = [];
    this.api.get<Quiz>(`quizzes/${quiz.id}`).subscribe({
      next: (detail) => this.selected.set(detail),
      error: () => this.error.set('Could not load that quiz.'),
    });
  }

  addDraft(): void {
    this.drafts = [...this.drafts, blankDraft()];
  }

  removeDraft(index: number): void {
    this.drafts = this.drafts.filter((_row, position) => position !== index);
  }

  setOption(draft: Draft, index: number, value: string): void {
    draft.options[index] = value;
  }

  saveQuestions(quiz: Quiz): void {
    if (!this.drafts.length) {
      return;
    }
    const invalid = this.drafts.some(
      (draft) =>
        !draft.text.trim() ||
        draft.options.some((option) => !option.trim()) ||
        !Number.isInteger(draft.correct) ||
        Number(draft.points) < 1,
    );
    if (invalid) {
      this.error.set('Each question needs text, four options, a correct option and at least one point.');
      return;
    }

    const requests = this.drafts.map((draft) =>
      this.api.action<QuizQuestion>(`quizzes/${quiz.id}/questions`, {
        text: draft.text.trim(),
        options: draft.options.map((option) => option.trim()),
        correct_option_index: draft.correct,
        points: Number(draft.points),
      }),
    );

    this.saving.set(true);
    this.error.set('');
    forkJoin(requests).subscribe({
      next: () => {
        this.saving.set(false);
        this.drafts = [];
        this.message.set('Questions saved.');
        this.reload(quiz.id);
        this.load();
      },
      error: (error) => {
        this.saving.set(false);
        this.error.set(this.describe(error));
      },
    });
  }

  publish(quiz: Quiz): void {
    this.api.action<Quiz>(`quizzes/${quiz.id}/publish`).subscribe({
      next: (updated) => {
        this.message.set(`“${updated.title}” is published.`);
        this.error.set('');
        this.afterChange(updated);
      },
      error: (error) => this.error.set(this.describe(error)),
    });
  }

  close(quiz: Quiz): void {
    this.api.action<Quiz>(`quizzes/${quiz.id}/close`).subscribe({
      next: (updated) => {
        this.message.set(`“${updated.title}” is closed.`);
        this.error.set('');
        this.afterChange(updated);
      },
      error: (error) => this.error.set(this.describe(error)),
    });
  }

  results(quiz: Quiz): void {
    this.error.set('');
    this.api.get<QuizAttemptsResponse>(`quizzes/${quiz.id}/attempts`).subscribe({
      next: (data) => this.attempts.set(data),
      error: (error) => this.error.set(this.describe(error)),
    });
  }

  private load(): void {
    this.api.list<Quiz>('quizzes').subscribe({
      next: (rows) => this.quizzes.set(rows),
      error: () => this.error.set('Could not load your quizzes.'),
    });
  }

  private reload(id: number): void {
    this.api.get<Quiz>(`quizzes/${id}`).subscribe({
      next: (detail) => this.selected.set(detail),
      error: () => undefined,
    });
  }

  private afterChange(updated: Quiz): void {
    this.quizzes.update((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
    if (this.selected()?.id === updated.id) {
      this.selected.set(updated);
    }
  }

  private describe(error: unknown): string {
    const body = (error as { error?: Record<string, unknown> }).error;
    if (body && typeof body === 'object') {
      const messages = Object.values(body)
        .flatMap((value) => (Array.isArray(value) ? value : [value]))
        .filter((value): value is string => typeof value === 'string');
      if (messages.length) {
        return messages.join(' ');
      }
    }
    return 'That action did not work. Try again.';
  }

  private iso(value: string): string | null {
    return value ? new Date(value).toISOString() : null;
  }

  private localInput(value: string | null): string {
    if (!value) {
      return '';
    }
    const date = new Date(value);
    const pad = (number: number) => String(number).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
      date.getHours(),
    )}:${pad(date.getMinutes())}`;
  }
}
