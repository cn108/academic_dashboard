import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { Paged } from './models';

type Params = Record<string, string | number | undefined>;

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  /** GET a list endpoint, unwrapping the DRF pagination envelope. */
  list<T>(path: string, params: Params = {}): Observable<T[]> {
    return this.http
      .get<Paged<T> | T[]>(`/api/${path}/`, { params: this.toParams(params) })
      .pipe(map((body) => (Array.isArray(body) ? body : body.results)));
  }

  get<T>(path: string, params: Params = {}): Observable<T> {
    return this.http.get<T>(`/api/${path}/`, { params: this.toParams(params) });
  }

  create<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(`/api/${path}/`, body);
  }

  update<T>(path: string, body: unknown): Observable<T> {
    return this.http.patch<T>(`/api/${path}/`, body);
  }

  remove(path: string): Observable<void> {
    return this.http.delete<void>(`/api/${path}/`);
  }

  upload<T>(path: string, form: FormData, params: Params = {}): Observable<T> {
    return this.http.post<T>(`/api/${path}/`, form, { params: this.toParams(params) });
  }

  /** Download a file (CSV template) as a blob. */
  download(path: string, params: Params = {}): Observable<Blob> {
    return this.http.get(`/api/${path}/`, {
      params: this.toParams(params),
      responseType: 'blob',
    });
  }

  /** Fetch an HTML page such as a printable report card. */
  text(path: string, params: Params = {}): Observable<string> {
    return this.http.get(`/api/${path}/`, {
      params: this.toParams(params),
      responseType: 'text',
    });
  }

  /** POST to a custom action such as publish/ or archive/. */
  action<T>(path: string, body: unknown = {}): Observable<T> {
    return this.http.post<T>(`/api/${path}/`, body);
  }

  private toParams(params: Params): HttpParams {
    let httpParams = new HttpParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') {
        httpParams = httpParams.set(key, String(value));
      }
    }
    return httpParams;
  }
}
