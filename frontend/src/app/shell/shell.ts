import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '../core/auth.service';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">
          <span class="brand-mark">A</span>
          <span>School<br />Portal</span>
        </div>

        <nav class="nav">
          <p class="nav-label">{{ role() === 'teacher' ? 'Teaching' : 'My class' }}</p>

          @if (role() === 'teacher') {
            <a routerLink="/teacher/dashboard" routerLinkActive="active">Overview</a>
            <a routerLink="/teacher/class" routerLinkActive="active">My class</a>
            <a routerLink="/teacher/results" routerLinkActive="active">Results</a>
            <a routerLink="/teacher/broadsheet" routerLinkActive="active">Broadsheet</a>
            <a routerLink="/teacher/notes" routerLinkActive="active">Lesson notes</a>
            <a routerLink="/teacher/assignments" routerLinkActive="active">Assignments</a>
            <a routerLink="/teacher/submissions" routerLinkActive="active">Submissions</a>
            <a routerLink="/teacher/announcements" routerLinkActive="active">Announcements</a>
            <a routerLink="/teacher/attendance" routerLinkActive="active">Attendance</a>
          } @else {
            <a routerLink="/student/dashboard" routerLinkActive="active">Overview</a>
            <a routerLink="/student/results" routerLinkActive="active">My results</a>
            <a routerLink="/student/notes" routerLinkActive="active">Lesson notes</a>
            <a routerLink="/student/assignments" routerLinkActive="active">Assignments</a>
            <a routerLink="/student/attendance" routerLinkActive="active">Attendance</a>
            <a routerLink="/student/announcements" routerLinkActive="active">Announcements</a>
          }
        </nav>

        <div class="sidebar-footer">
          <p class="small muted">
            {{ user()?.class_name || 'No class assigned' }}
            @if (user()?.admission_number) {
              · {{ user()?.admission_number }}
            }
          </p>
          <p style="color: var(--text); font-weight: 600; margin-bottom: 0.6rem">
            {{ user()?.name }}
          </p>
          <button class="btn btn-ghost btn-sm" type="button" (click)="logout()">Sign out</button>
        </div>
      </aside>

      <main class="content">
        <router-outlet />
      </main>
    </div>
  `,
})
export class Shell {
  private readonly auth = inject(AuthService);

  readonly user = this.auth.user;
  readonly role = computed(() => this.auth.role());

  logout(): void {
    this.auth.logout();
  }
}
