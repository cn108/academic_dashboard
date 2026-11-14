"""URL configuration for the core app — a headless JSON API."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

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
    path("api/me/", views.MeView.as_view(), name="api-me"),
    path("api/me/password/", views.PasswordChangeView.as_view(), name="api-password-change"),
    path("api/token/", views.TokenLoginView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", views.TokenRefreshAPIView.as_view(), name="token_refresh"),
    path("api/", include(router.urls)),
]
