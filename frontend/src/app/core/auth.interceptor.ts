import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';

import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const token = auth.accessToken;
  const isTokenCall = request.url.startsWith('/api/token/');

  const authorised =
    token && !isTokenCall
      ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
      : request;

  return next(authorised).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401 || !token || isTokenCall) {
        return throwError(() => error);
      }

      return auth.refreshTokens().pipe(
        switchMap((refreshed) => {
          if (!refreshed) {
            auth.logout();
            return throwError(() => error);
          }
          return next(
            request.clone({
              setHeaders: { Authorization: `Bearer ${auth.accessToken}` },
            }),
          );
        }),
      );
    }),
  );
};
