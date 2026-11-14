import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';
import { Role } from './models';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.accessToken ? true : router.parseUrl('/login');
};

/** Blocks the portals until a student has replaced their default password. */
export const passwordGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.mustChangePassword()) {
    return router.parseUrl('/change-password');
  }
  return true;
};

export const roleGuard = (role: Role): CanActivateFn => () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.accessToken) {
    return router.parseUrl('/login');
  }
  const current = auth.role();
  if (current === role) {
    return true;
  }
  return router.parseUrl(auth.homeFor(current));
};

/** Administration screens (finance, notifications) are for office staff only. */
export const staffGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.accessToken) {
    return router.parseUrl('/login');
  }
  if (auth.user()?.is_staff) {
    return true;
  }
  return router.parseUrl(auth.homeFor(auth.role()));
};

export const homeRedirect: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.mustChangePassword()) {
    return router.parseUrl('/change-password');
  }
  return router.parseUrl(auth.homeFor(auth.role()));
};
