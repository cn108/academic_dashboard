import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-change-password',
  imports: [FormsModule],
  template: `
    <div class="auth-wrap">
      <div class="auth-card">
        <div class="brand" style="margin-bottom: 1.5rem">
          <span class="brand-mark">A</span>
          <span>School Portal</span>
        </div>

        <h1>Choose a new password</h1>
        <p class="muted small" style="margin-bottom: 1.5rem">
          You are using the password the school gave you. Pick something only you know before you
          continue.
        </p>

        @if (error()) {
          <div class="alert alert-error">{{ error() }}</div>
        }

        <form (ngSubmit)="submit()">
          <div class="field">
            <label for="current">Current password</label>
            <input id="current" name="current" type="password" [(ngModel)]="current" required />
          </div>
          <div class="field">
            <label for="next">New password</label>
            <input
              id="next"
              name="next"
              type="password"
              [(ngModel)]="next"
              autocomplete="new-password"
              required
            />
          </div>
          <div class="field">
            <label for="confirm">Confirm new password</label>
            <input
              id="confirm"
              name="confirm"
              type="password"
              [(ngModel)]="confirm"
              autocomplete="new-password"
              required
            />
          </div>
          <button class="btn" type="submit" style="width: 100%" [disabled]="busy()">
            {{ busy() ? 'Saving…' : 'Save and continue' }}
          </button>
        </form>

        @if (!forced()) {
          <p class="small muted" style="margin-top: 1rem">
            <a href="/logout" (click)="signOut($event)">Sign out instead</a>
          </p>
        }
      </div>
    </div>
  `,
})
export class ChangePasswordPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  current = '';
  next = '';
  confirm = '';
  readonly error = signal('');
  readonly busy = signal(false);
  readonly forced = this.auth.mustChangePassword;

  submit(): void {
    if (this.next !== this.confirm) {
      this.error.set('The two new passwords do not match.');
      return;
    }
    if (this.next.length < 8) {
      this.error.set('Use at least 8 characters.');
      return;
    }

    this.busy.set(true);
    this.error.set('');
    this.auth.changePassword(this.current, this.next).subscribe({
      next: (user) => this.router.navigateByUrl(this.auth.homeFor(user.role)),
      error: (error) => {
        this.busy.set(false);
        this.error.set(this.describe(error));
      },
    });
  }

  signOut(event: Event): void {
    event.preventDefault();
    this.auth.logout();
  }

  private describe(error: unknown): string {
    const body = (error as { error?: Record<string, string[]> }).error;
    if (body && typeof body === 'object') {
      const messages = Object.values(body).flat();
      if (messages.length) {
        return messages.join(' ');
      }
    }
    return 'Could not change your password. Try again.';
  }
}
