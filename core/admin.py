"""Admin configuration — the school office's control panel.

Teacher accounts are created here by a superuser; there is no public teacher
registration route.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    AcademicSession,
    Announcement,
    Assignment,
    Attendance,
    LessonNote,
    Profile,
    Result,
    Schedule,
    SchoolClass,
    Subject,
    Submission,
    Term,
)


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    fields = (
        "role",
        "admission_number",
        "gender",
        "school_class",
        "must_change_password",
    )


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "first_name", "last_name", "role", "is_staff")

    @admin.display(description="Role")
    def role(self, obj):
        return getattr(getattr(obj, "profile", None), "role", "")


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "admission_number", "gender", "school_class")
    list_filter = ("role", "gender", "school_class")
    search_fields = ("user__username", "admission_number")


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_current")
    list_editable = ("is_current",)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ("name", "session", "is_current")
    list_filter = ("session", "name")
    list_editable = ("is_current",)


class SubjectInline(admin.TabularInline):
    model = Subject
    extra = 0
    fields = ("name", "teacher")


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "class_teacher", "capacity", "student_count")
    list_filter = ("level",)
    search_fields = ("name", "class_teacher__username")
    inlines = [SubjectInline]

    @admin.display(description="Students")
    def student_count(self, obj):
        return obj.student_count


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "school_class", "teacher")
    list_filter = ("school_class",)
    search_fields = ("name", "teacher__username")


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "session", "term", "total", "grade", "remarks", "status")
    list_filter = ("status", "session", "term", "subject__school_class")
    search_fields = ("student__username", "subject__name")
    readonly_fields = ("total", "grade", "remarks", "published_at")


@admin.register(LessonNote)
class LessonNoteAdmin(admin.ModelAdmin):
    list_display = ("subject", "week_number", "topic", "term", "status")
    list_filter = ("status", "subject__school_class", "term")
    search_fields = ("topic", "subject__name")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "status", "created_by", "created_at")
    list_filter = ("status", "school_class")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "school_class", "subject", "kind", "due_date", "status")
    list_filter = ("status", "kind", "school_class")
    search_fields = ("title", "subject__name")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "student", "submitted_at", "marks", "is_graded")
    list_filter = ("assignment__school_class",)
    search_fields = ("student__username", "assignment__title")

    @admin.display(boolean=True, description="Graded")
    def is_graded(self, obj):
        return obj.is_graded


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("school_class", "student", "date", "status")
    list_filter = ("status", "school_class")
    date_hierarchy = "date"


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "day", "time")
    list_filter = ("day",)
    search_fields = ("name", "user__username")
