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
    Fee,
    LessonNote,
    LessonResource,
    NotificationLog,
    ParentStudentLink,
    Payment,
    Profile,
    Question,
    Quiz,
    QuizAttempt,
    ResourceProgress,
    Result,
    Schedule,
    School,
    SchoolClass,
    StudentFee,
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
        "phone_number",
        "phone_verified",
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


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    """The singleton school profile: logo, contacts and the current period."""

    list_display = ("name", "current_session", "current_term", "phone", "email")
    fieldsets = (
        (
            "Identity",
            {
                "fields": ("name", "motto", "logo"),
                "description": "Shown on report cards, exports, the login page and the portal sidebar.",
            },
        ),
        ("Contact", {"fields": ("address", "phone", "email")}),
        ("Current period", {"fields": ("current_session", "current_term")}),
    )

    def has_add_permission(self, request):
        # One row for now; the slug and model boundaries allow more later.
        return not School.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


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


class LessonResourceInline(admin.TabularInline):
    model = LessonResource
    extra = 0
    fields = ("type", "title", "url", "file", "order_index")


@admin.register(LessonNote)
class LessonNoteAdmin(admin.ModelAdmin):
    list_display = ("subject", "week_number", "topic", "term", "status")
    list_filter = ("status", "subject__school_class", "term")
    search_fields = ("topic", "subject__name")
    inlines = [LessonResourceInline]


@admin.register(ResourceProgress)
class ResourceProgressAdmin(admin.ModelAdmin):
    list_display = ("student", "resource", "is_completed", "completed_at")
    list_filter = ("is_completed", "resource__lesson__subject__school_class")
    search_fields = ("student__username", "student__first_name", "resource__title")
    readonly_fields = ("completed_at",)


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ("text", "options", "correct_option_index", "points")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "subject",
        "class_arm",
        "status",
        "time_limit_minutes",
        "total_points",
        "available_from",
        "available_until",
    )
    list_filter = ("status", "class_arm", "subject")
    search_fields = ("title", "subject__name", "class_arm__name")
    readonly_fields = ("total_points", "created_at")
    inlines = [QuestionInline]


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("quiz", "student", "status", "score", "started_at", "submitted_at")
    list_filter = ("status", "quiz")
    search_fields = ("student__username", "student__first_name", "quiz__title")
    readonly_fields = ("started_at", "submitted_at", "score", "answers", "status")


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


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("recipient", "channel", "event_type", "status", "external_id", "created_at")
    list_filter = ("channel", "event_type", "status")
    search_fields = ("recipient__username", "recipient__first_name", "external_id")
    readonly_fields = ("recipient", "channel", "event_type", "payload", "status", "external_id")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False


@admin.register(ParentStudentLink)
class ParentStudentLinkAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "relationship", "created_at")
    list_filter = ("relationship",)
    search_fields = ("parent__username", "student__username", "student__first_name")


@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ("description", "class_level", "session", "term", "amount")
    list_filter = ("session", "term", "class_level")
    search_fields = ("description",)


@admin.register(StudentFee)
class StudentFeeAdmin(admin.ModelAdmin):
    list_display = ("student", "fee", "amount_paid", "balance", "status")
    list_filter = ("status", "fee__session", "fee__term", "fee__class_level")
    search_fields = ("student__username", "student__first_name", "fee__description")
    readonly_fields = ("balance", "status")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "parent", "student_fee", "amount", "gateway", "status", "paid_at")
    list_filter = ("status", "gateway")
    search_fields = ("reference", "parent__username")
    readonly_fields = ("reference", "paid_at", "created_at")


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "day", "time")
    list_filter = ("day",)
    search_fields = ("name", "user__username")
