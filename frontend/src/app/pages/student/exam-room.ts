import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { QuizStart, QuizSubmitResult } from '../../core/models';

@Component({
  selector: 'app-student-exam-room',
  imports: [RouterLink],
  template: `
    <div class="exam">
      @if (!result() && data(); as exam) {
        <div class="exam-bar">
          <div>
            <p class="eyebrow">Exam room</p>
            <h1 style="font-size: 1.25rem">{{ exam.quiz.title }}</h1>
            <p class="muted small">
              {{ exam.questions.length }} questions · {{ exam.quiz.total_points }} points
            </p>
          </div>
          <div style="text-align: right">
            <p class="exam-timer" [class.urgent]="remaining() <= 60">{{ clock() }}</p>
            <p class="muted small">time remaining</p>
          </div>
        </div>
      }

      @if (error()) {
        <div class="alert alert-error">{{ error() }}</div>
      }

      @if (!result() && data(); as exam) {
        <div class="grid">
          @for (question of exam.questions; track question.id; let index = $index) {
            <div class="card">
              <p class="small muted">
                Question {{ index + 1 }} · {{ question.points }}
                {{ question.points === 1 ? 'point' : 'points' }}
              </p>
              <h2 style="font-size: 1.05rem; margin: 0.35rem 0 0.9rem">{{ question.text }}</h2>

              <div class="grid">
                @for (option of question.options; track $index; let choice = $index) {
                  <label class="option" [class.selected]="answers()[question.id] === choice">
                    <input
                      type="radio"
                      [name]="'q' + question.id"
                      [checked]="answers()[question.id] === choice"
                      (change)="choose(question.id, choice)"
                    />
                    <span>{{ option }}</span>
                  </label>
                }
              </div>
            </div>
          }
        </div>

        <div class="exam-actions">
          <p class="muted small">Answers are graded on the school server when you submit.</p>
          <button class="btn" type="button" [disabled]="submitting()" (click)="submit()">
            {{ submitting() ? 'Submitting…' : 'Submit quiz' }}
          </button>
        </div>
      }

      @if (result(); as scored) {
        <div class="card" style="margin-bottom: 1rem">
          <div class="card-head">
            <div>
              <p class="eyebrow">Quiz result</p>
              <h1>{{ scored.attempt.passed ? 'Passed' : 'Keep practising' }}</h1>
            </div>
            <span
              class="badge"
              [class]="scored.attempt.passed ? 'badge-success' : 'badge-danger'"
            >
              {{ scored.attempt.percentage }}%
            </span>
          </div>
          <p class="muted">
            {{ scored.attempt.score }} of {{ scored.attempt.total_points }} points ·
            {{ scored.attempt.percentage }}%
          </p>

          <div class="table-wrap" style="margin-top: 1rem">
            <table>
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Your answer</th>
                  <th>Correct answer</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                @for (answer of scored.answers; track answer.question) {
                  <tr>
                    <td>{{ questionText(answer.question) }}</td>
                    <td>{{ optionText(answer.question, answer.selected_option) }}</td>
                    <td>{{ optionText(answer.question, answer.correct_option_index) }}</td>
                    <td>
                      <span class="badge" [class]="answer.is_correct ? 'badge-success' : 'badge-danger'">
                        {{ answer.is_correct ? 'Correct' : 'Wrong' }}
                      </span>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <div class="row-actions" style="margin-top: 1rem">
            <a class="btn" routerLink="/student/quizzes">Back to quizzes</a>
          </div>
        </div>
      }

      @if (!data() && !error()) {
        <p class="empty">Loading your quiz…</p>
      }

      @if (error() && !data()) {
        <div class="row-actions" style="margin-top: 1rem">
          <a class="btn btn-ghost" routerLink="/student/quizzes">Back to quizzes</a>
        </div>
      }

      @if (expiredModal()) {
        <div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="expired-title">
          <div class="card" style="max-width: 440px; width: 100%">
            <h2 id="expired-title" style="font-size: 1.3rem">Time's up!</h2>
            @if (result(); as scored) {
              <p style="margin-top: 0.6rem">Your quiz has been auto-graded.</p>
              <p class="muted small">
                You scored {{ scored.attempt.score }} of {{ scored.attempt.total_points }}
                ({{ scored.attempt.percentage }}%).
              </p>
              <div class="row-actions" style="margin-top: 1rem">
                <button class="btn" type="button" (click)="expiredModal.set(false)">See result</button>
              </div>
            } @else {
              <p style="margin-top: 0.6rem">
                The timer ran out and the server did not accept your answers in time. Ask your
                teacher about a retake.
              </p>
              <div class="row-actions" style="margin-top: 1rem">
                <a class="btn" routerLink="/student/quizzes">Back to quizzes</a>
              </div>
            }
          </div>
        </div>
      }
    </div>
  `,
})
export class StudentExamRoom implements OnDestroy {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);

  readonly data = signal<QuizStart | null>(null);
  readonly answers = signal<Record<number, number>>({});
  readonly remaining = signal(0);
  readonly submitting = signal(false);
  readonly submitted = signal(false);
  readonly result = signal<QuizSubmitResult | null>(null);
  readonly expiredModal = signal(false);
  readonly expired = signal(false);
  readonly error = signal('');

  readonly clock = computed(() => {
    const total = this.remaining();
    const minutes = String(Math.floor(total / 60)).padStart(2, '0');
    const seconds = String(total % 60).padStart(2, '0');
    return `${minutes}:${seconds}`;
  });

  private timer: ReturnType<typeof setInterval> | undefined;
  private deadline = 0;
  private autoTried = false;

  constructor() {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.error.set('Quiz not found.');
      return;
    }
    this.api.action<QuizStart>(`quizzes/${id}/start`).subscribe({
      next: (data) => {
        this.data.set(data);
        this.deadline = new Date(data.attempt.expires_at).getTime();
        this.tick();
        this.timer = setInterval(() => this.tick(), 1000);
      },
      error: (error) => this.error.set(this.messageFor(error)),
    });
  }

  ngOnDestroy(): void {
    this.clearTimer();
  }

  choose(questionId: number, option: number): void {
    this.answers.update((current) => ({ ...current, [questionId]: option }));
  }

  questionText(questionId: number): string {
    return (
      this.data()?.questions.find((question) => question.id === questionId)?.text ??
      `Question ${questionId}`
    );
  }

  optionText(questionId: number, index: number | null): string {
    if (index === null) {
      return 'Not answered';
    }
    const question = this.data()?.questions.find((row) => row.id === questionId);
    return question?.options[index] ?? `Option ${index + 1}`;
  }

  submit(auto = false): void {
    if (this.submitting() || this.submitted()) {
      return;
    }
    const data = this.data();
    if (!data) {
      return;
    }

    const answers = Object.entries(this.answers()).map(([question, option]) => ({
      question: Number(question),
      selected_option: option,
    }));

    this.submitting.set(true);
    this.error.set('');
    this.api.action<QuizSubmitResult>(`quizzes/${data.quiz.id}/submit`, { answers }).subscribe({
      next: (result) => {
        this.submitting.set(false);
        this.submitted.set(true);
        this.result.set(result);
        this.clearTimer();
        if (auto) {
          this.expiredModal.set(true);
        }
      },
      error: (error) => {
        this.submitting.set(false);
        const detail = this.detailOf(error);
        if (detail === 'Time expired') {
          this.submitted.set(true);
          this.expired.set(true);
          this.expiredModal.set(true);
          this.clearTimer();
          return;
        }
        this.error.set(detail || 'Could not submit your answers. Check your connection and try again.');
      },
    });
  }

  private tick(): void {
    const seconds = Math.max(0, Math.ceil((this.deadline - Date.now()) / 1000));
    this.remaining.set(seconds);
    if (seconds === 0 && !this.autoTried && !this.submitting() && !this.submitted()) {
      this.autoTried = true;
      this.submit(true);
    }
  }

  private clearTimer(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = undefined;
    }
  }

  private messageFor(error: unknown): string {
    const detail = this.detailOf(error);
    return detail || 'Could not start this quiz. Ask your teacher to check it.';
  }

  private detailOf(error: unknown): string {
    const body = (error as { error?: { detail?: unknown } }).error;
    const detail = body?.detail;
    return typeof detail === 'string' ? detail : '';
  }
}
