import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { quizTone, StudentQuiz } from '../../core/models';

@Component({
  selector: 'app-student-quizzes',
  imports: [DatePipe, RouterLink],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Student portal</p>
        <h1>Quizzes</h1>
        <p class="muted small">
          Timed multiple-choice checks from your teachers. The clock runs on the school server.
        </p>
      </div>
    </div>

    @if (error()) {
      <div class="alert alert-error">{{ error() }}</div>
    }

    <div class="grid grid-2">
      @for (quiz of quizzes(); track quiz.id) {
        <div class="card">
          <div class="card-head">
            <div>
              <p class="small muted">{{ quiz.subject_name }}</p>
              <h2 style="font-size: 1.05rem">{{ quiz.title }}</h2>
            </div>
            <span class="badge" [class]="tone(quiz.status)">{{ quiz.status }}</span>
          </div>

          <p class="small muted">
            {{ quiz.questions_count }} questions · {{ quiz.time_limit_minutes }} minutes ·
            {{ quiz.total_points }} points
          </p>
          @if (quiz.available_from) {
            <p class="small muted">Opens {{ quiz.available_from | date: 'short' }}</p>
          }
          @if (quiz.available_until) {
            <p class="small muted">Closes {{ quiz.available_until | date: 'short' }}</p>
          }

          <div class="row-actions" style="margin-top: 1rem">
            @if (open(quiz)) {
              <a class="btn" [routerLink]="['/student/quizzes', quiz.id, 'take']">Start quiz</a>
            } @else if (quiz.status === 'closed') {
              <span class="badge badge-danger">Closed</span>
            } @else if (quiz.status === 'draft') {
              <span class="badge badge-warning">Coming soon</span>
            } @else {
              <span class="badge badge-warning">Not open right now</span>
            }
          </div>
        </div>
      } @empty {
        <div class="card">
          <p class="empty">No quizzes have been published for your class yet.</p>
        </div>
      }
    </div>
  `,
})
export class StudentQuizzes {
  private readonly api = inject(ApiService);

  readonly quizzes = signal<StudentQuiz[]>([]);
  readonly error = signal('');

  constructor() {
    this.api.list<StudentQuiz>('quizzes').subscribe({
      next: (rows) => this.quizzes.set(rows),
      error: () => this.error.set('Could not load your quizzes.'),
    });
  }

  tone(status: StudentQuiz['status']): string {
    return quizTone(status);
  }

  open(quiz: StudentQuiz): boolean {
    if (quiz.status !== 'published' || !quiz.questions_count) {
      return false;
    }
    const now = Date.now();
    if (quiz.available_from && new Date(quiz.available_from).getTime() > now) {
      return false;
    }
    if (quiz.available_until && new Date(quiz.available_until).getTime() < now) {
      return false;
    }
    return true;
  }
}
