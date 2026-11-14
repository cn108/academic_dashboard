import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, map, of, switchMap, tap } from 'rxjs';

import { Me, Role, Tokens } from './models';

const ACCESS_KEY = 'ad.access';
const REFRESH_KEY = 'ad.refresh';
const USER_KEY = 'ad.user';

interface PasswordChangeResponse extends Tokens {
  detail: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  readonly user = signal<Me | null>(this.readStoredUser());
  readonly role = computed<Role | null>(() => this.user()?.role ?? null);
  readonly signedIn = computed(() => Boolean(this.accessToken));
  readonly mustChangePassword = computed(() => this.user()?.must_change_password ?? false);

  get accessToken(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  }

  get refreshToken(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  }

  /** Students sign in with their admission number; teachers with a username. */
  login(username: string, password: string): Observable<Me> {
    return this.http.post<Tokens>('/api/token/', { username, password }).pipe(
      tap((tokens) => this.storeTokens(tokens)),
      switchMap(() => this.fetchMe()),
    );
  }

  fetchMe(): Observable<Me> {
    return this.http.get<Me>('/api/me/').pipe(
      tap((user) => {
        this.user.set(user);
        localStorage.setItem(USER_KEY, JSON.stringify(user));
      }),
    );
  }

  changePassword(currentPassword: string, newPassword: string): Observable<Me> {
    return this.http
      .post<PasswordChangeResponse>('/api/me/password/', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      .pipe(
        tap((response) => {
          this.storeTokens({ access: response.access, refresh: response.refresh });
          const user = this.user();
          if (user) {
            const updated = { ...user, must_change_password: false };
            this.user.set(updated);
            localStorage.setItem(USER_KEY, JSON.stringify(updated));
          }
        }),
        switchMap(() => this.fetchMe()),
      );
  }

  /** Called on app start so a refresh restores the role from the server. */
  restore(): void {
    if (this.accessToken) {
      this.fetchMe().subscribe({ error: () => this.clear() });
    }
  }

  refreshTokens(): Observable<boolean> {
    const refresh = this.refreshToken;
    if (!refresh) {
      return of(false);
    }
    return this.http.post<Tokens>('/api/token/refresh/', { refresh }).pipe(
      tap((tokens) => this.storeTokens(tokens)),
      map(() => true),
      catchError(() => {
        this.clear();
        return of(false);
      }),
    );
  }

  logout(): void {
    this.clear();
    this.router.navigateByUrl('/login');
  }

  homeFor(role: Role | null): string {
    return role === 'teacher' ? '/teacher/dashboard' : '/student/dashboard';
  }

  private storeTokens(tokens: Tokens): void {
    localStorage.setItem(ACCESS_KEY, tokens.access);
    localStorage.setItem(REFRESH_KEY, tokens.refresh);
  }

  private clear(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
    this.user.set(null);
  }

  private readStoredUser(): Me | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw) as Me;
    } catch {
      return null;
    }
  }
}
