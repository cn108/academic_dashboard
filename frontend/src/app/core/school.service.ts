import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';

import { SchoolBranding } from './models';

/**
 * The school's public identity. Loaded once per app session so the login page
 * and the portal sidebar share one name, logo and motto.
 */
@Injectable({ providedIn: 'root' })
export class SchoolService {
  private readonly http = inject(HttpClient);

  readonly school = signal<SchoolBranding | null>(null);

  constructor() {
    this.http.get<SchoolBranding>('/api/school/').subscribe({
      next: (school) => this.school.set(school),
      error: () => this.school.set(null),
    });
  }
}
