import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { SchoolService } from '../../core/school.service';

@Component({
  selector: 'app-login',
  imports: [FormsModule],
  template: `
    <div class="auth-wrap">
      <div class="auth-card">
        <div class="brand" style="margin-bottom: 1.5rem">
          @if (school()?.logo_url) {
            <img class="brand-logo" [src]="school()!.logo_url" [alt]="school()!.name + ' logo'" />
          } @else {
            <span class="brand-mark">{{ school()?.initials || 'S' }}</span>
          }
          <span>{{ school()?.name || 'School Portal' }}</span>
        </div>

        <h1>Welcome back</h1>
        @if (school()?.motto) {
          <p class="muted small" style="margin-bottom: 0.35rem">{{ school()!.motto }}</p>
        }
        <p class="muted small" style="margin-bottom: 1.5rem">
          Students sign in with their admission number. Teachers and parents use the username issued by the school office.
        </p>

        @if (error()) {
          <div class="alert alert-error">{{ error() }}</div>
        }

        <form (ngSubmit)="submit()">
          <div class="field">
            <label for="username">Admission number or username</label>
            <input
              id="username"
              name="username"
              [(ngModel)]="username"
              autocomplete="username"
              required
            />
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              [(ngModel)]="password"
              autocomplete="current-password"
              required
            />
          </div>
          <button class="btn" type="submit" style="width: 100%" [disabled]="busy()">
            {{ busy() ? 'Signing in…' : 'Sign in' }}
          </button>
        </form>

        <p class="small muted" style="margin-top: 1.25rem">
          Forgot your password? Ask your class teacher to reset it from the school office.
        </p>
      </div>
    </div>
  `,
})
export class LoginPage {
  private readonly auth = inject(AuthService);
  private readonly schoolService = inject(SchoolService);
  private readonly router = inject(Router);

  readonly school = this.schoolService.school;

  username = '';
  password = '';
  readonly error = signal('');
  readonly busy = signal(false);

  submit(): void {
    if (!this.username || !this.password) {
      this.error.set('Enter your admission number and password.');
      return;
    }
    this.busy.set(true);
    this.error.set('');

    this.auth.login(this.username.trim(), this.password).subscribe({
      next: (user) => {
        if (user.must_change_password) {
          this.router.navigateByUrl('/change-password');
          return;
        }
        this.router.navigateByUrl(this.auth.homeFor(user.role));
      },
      error: (error) => {
        this.busy.set(false);
        this.error.set(this.messageFor(error));
      },
    });
  }

  private messageFor(error: unknown): string {
    const status = (error as { status?: number }).status;
    if (status === 429 || status === 403) {
      return 'Too many failed attempts. Try again in a few minutes.';
    }
    return 'Those details did not work. Check your admission number and password.';
  }
}
