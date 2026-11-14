"""URL configuration for the core app — a headless JSON API."""

from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve as serve_media
from rest_framework.routers import DefaultRouter

from . import parents, views

router = DefaultRouter()
router.register("sessions", views.AcademicSessionViewSet, basename="session")
router.register("terms", views.TermViewSet, basename="term")
router.register("classes", views.SchoolClassViewSet, basename="class")
router.register("subjects", views.SubjectViewSet, basename="subject")
router.register("results", views.ResultViewSet, basename="result")
router.register("lesson-notes", views.LessonNoteViewSet, basename="lesson-note")
router.register("announcements", views.AnnouncementViewSet, basename="announcement")
router.register("assignments", views.AssignmentViewSet, basename="assignment")
router.register("submissions", views.SubmissionViewSet, basename="submission")
router.register("attendance", views.AttendanceViewSet, basename="attendance")
router.register("schedule", views.ScheduleViewSet, basename="schedule")

urlpatterns = [
    path("api/health/", views.HealthView.as_view(), name="api-health"),
    path("api/school/", views.SchoolBrandingView.as_view(), name="api-school"),
    path("api/me/", views.MeView.as_view(), name="api-me"),
    path("api/finance/summary/", views.FinanceSummaryView.as_view(), name="finance-summary"),
    path("api/finance/debtors/", views.FinanceDebtorsView.as_view(), name="finance-debtors"),
    path("api/finance/ledger/", views.FinanceLedgerView.as_view(), name="finance-ledger"),
    path("api/me/password/", views.PasswordChangeView.as_view(), name="api-password-change"),
    path(
        "api/students/<int:pk>/reset-password/",
        views.StudentPasswordResetView.as_view(),
        name="student-password-reset",
    ),
    path(
        "api/parent/wards/<int:pk>/reset-password/",
        views.ParentWardPasswordResetView.as_view(),
        name="parent-ward-password-reset",
    ),
    path(
        "api/students/<int:pk>/report-card/",
        views.StudentReportCardView.as_view(),
        name="api-student-report-card",
    ),
    path("api/parent/wards/", parents.ParentWardsView.as_view(), name="parent-wards"),
    path("api/parent/fees/", parents.ParentFeesView.as_view(), name="parent-fees"),
    path("api/parent/payments/", parents.ParentPaymentsView.as_view(), name="parent-payments"),
    path(
        "api/payments/initialize/",
        parents.InitializePaymentView.as_view(),
        name="payment-initialize",
    ),
    path(
        "api/webhooks/paystack/",
        parents.PaystackWebhookView.as_view(),
        name="paystack-webhook",
    ),
    path("api/token/", views.TokenLoginView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", views.TokenRefreshAPIView.as_view(), name="token_refresh"),
    path(
        "api/notifications/logs/",
        views.NotificationLogsView.as_view(),
        name="notification-logs",
    ),
    path("api/", include(router.urls)),
]


# Uploaded files. Nginx proxies /media/ to Gunicorn in the production stack.
if settings.DEBUG or getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve_media, {"document_root": settings.MEDIA_ROOT}),
    ]
