import { Routes } from '@angular/router';

import { authGuard, homeRedirect, passwordGuard, roleGuard, staffGuard } from './core/guards';
import { Shell } from './shell/shell';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./pages/login/login').then((m) => m.LoginPage),
  },
  {
    path: 'change-password',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/change-password/change-password').then((m) => m.ChangePasswordPage),
  },
  // The exam room sits outside the shell so the sidebar and nav disappear.
  {
    path: 'student/quizzes/:id/take',
    canActivate: [authGuard, roleGuard('student'), passwordGuard],
    loadComponent: () =>
      import('./pages/student/exam-room').then((m) => m.StudentExamRoom),
  },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', canActivate: [homeRedirect], children: [] },
      {
        path: 'student',
        canActivate: [roleGuard('student'), passwordGuard],
        children: [
          {
            path: 'dashboard',
            loadComponent: () => import('./pages/student/dashboard').then((m) => m.StudentDashboard),
          },
          {
            path: 'results',
            loadComponent: () => import('./pages/student/results').then((m) => m.StudentResults),
          },
          {
            path: 'notes',
            loadComponent: () => import('./pages/student/notes').then((m) => m.StudentNotes),
          },
          {
            path: 'learning',
            loadComponent: () =>
              import('./pages/student/learning').then((m) => m.StudentLearning),
          },
          {
            path: 'quizzes',
            loadComponent: () =>
              import('./pages/student/quizzes').then((m) => m.StudentQuizzes),
          },
          {
            path: 'assignments',
            loadComponent: () =>
              import('./pages/student/assignments').then((m) => m.StudentAssignments),
          },
          {
            path: 'attendance',
            loadComponent: () =>
              import('./pages/student/attendance').then((m) => m.StudentAttendance),
          },
          {
            path: 'announcements',
            loadComponent: () =>
              import('./pages/student/announcements').then((m) => m.StudentAnnouncements),
          },
          { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
        ],
      },
      {
        path: 'teacher',
        canActivate: [roleGuard('teacher'), passwordGuard],
        children: [
          {
            path: 'dashboard',
            loadComponent: () => import('./pages/teacher/dashboard').then((m) => m.TeacherDashboard),
          },
          {
            path: 'class',
            loadComponent: () => import('./pages/teacher/class-roster').then((m) => m.ClassRoster),
          },
          {
            path: 'results',
            loadComponent: () => import('./pages/teacher/results').then((m) => m.TeacherResults),
          },
          {
            path: 'notes',
            loadComponent: () => import('./pages/teacher/notes').then((m) => m.TeacherNotes),
          },
          {
            path: 'assignments',
            loadComponent: () =>
              import('./pages/teacher/assignments').then((m) => m.TeacherAssignments),
          },
          {
            path: 'broadsheet',
            loadComponent: () =>
              import('./pages/teacher/broadsheet').then((m) => m.TeacherBroadsheet),
          },
          {
            path: 'quizzes',
            loadComponent: () =>
              import('./pages/teacher/quizzes').then((m) => m.TeacherQuizzes),
          },
          {
            path: 'submissions',
            loadComponent: () =>
              import('./pages/teacher/submissions').then((m) => m.TeacherSubmissions),
          },
          {
            path: 'announcements',
            loadComponent: () =>
              import('./pages/teacher/announcements').then((m) => m.TeacherAnnouncements),
          },
          {
            path: 'attendance',
            loadComponent: () => import('./pages/teacher/attendance').then((m) => m.TeacherAttendance),
          },
          {
            path: 'finance',
            canActivate: [staffGuard],
            loadComponent: () => import('./pages/staff/finance').then((m) => m.StaffFinance),
          },
          { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
        ],
      },
      {
        path: 'parent',
        canActivate: [roleGuard('parent')],
        children: [
          {
            path: 'dashboard',
            loadComponent: () => import('./pages/parent/dashboard').then((m) => m.ParentDashboard),
          },
          {
            path: 'results',
            loadComponent: () =>
              import('./pages/parent/ward-results').then((m) => m.ParentWardResults),
          },
          {
            path: 'fees',
            loadComponent: () => import('./pages/parent/fees').then((m) => m.ParentFees),
          },
          { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
        ],
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
