"""Serializers for the school management API."""

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

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


class AcademicSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicSession
        fields = ["id", "name", "start_date", "end_date", "is_current"]


class TermSerializer(serializers.ModelSerializer):
    session_name = serializers.CharField(source="session.name", read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Term
        fields = ["id", "session", "session_name", "name", "display_name", "is_current"]
        read_only_fields = ["is_current"]

    def get_display_name(self, obj) -> str:
        return f"{obj.session.name} — {obj.name}"


class SchoolClassSerializer(serializers.ModelSerializer):
    class_teacher_name = serializers.SerializerMethodField()
    student_count = serializers.IntegerField(read_only=True)
    students_detail = serializers.SerializerMethodField()

    class Meta:
        model = SchoolClass
        fields = [
            "id",
            "name",
            "level",
            "class_teacher",
            "class_teacher_name",
            "capacity",
            "student_count",
            "students_detail",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_class_teacher_name(self, obj) -> str | None:
        teacher = obj.class_teacher
        if teacher is None:
            return None
        return teacher.get_full_name() or teacher.username

    def get_students_detail(self, obj) -> list[dict]:
        rows = []
        for profile in obj.students.select_related("user").order_by("user__first_name"):
            user = profile.user
            rows.append(
                {
                    "id": user.pk,
                    "username": user.username,
                    "full_name": user.get_full_name() or user.username,
                    "admission_number": profile.admission_number,
                    "gender": profile.gender,
                }
            )
        return rows


class SubjectSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="school_class.name", read_only=True)
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ["id", "name", "school_class", "class_name", "teacher", "teacher_name"]
        extra_kwargs = {"teacher": {"required": False, "allow_null": True}}

    def get_teacher_name(self, obj) -> str | None:
        teacher = obj.teacher
        if teacher is None:
            return None
        return teacher.get_full_name() or teacher.username

    def validate_school_class(self, school_class):
        if school_class is None:
            raise serializers.ValidationError("A subject must belong to a class.")
        return school_class


class ResultSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    school_class = serializers.IntegerField(source="subject.school_class_id", read_only=True)
    class_name = serializers.CharField(source="subject.school_class.name", read_only=True)
    session_name = serializers.CharField(source="session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    ca_total = serializers.IntegerField(read_only=True)

    class Meta:
        model = Result
        fields = [
            "id",
            "student",
            "student_name",
            "admission_number",
            "subject",
            "subject_name",
            "school_class",
            "class_name",
            "session",
            "session_name",
            "term",
            "term_name",
            "ca1",
            "ca2",
            "ca3",
            "ca_total",
            "exam",
            "total",
            "grade",
            "remarks",
            "teacher_remark",
            "status",
            "published_at",
            "updated_at",
        ]
        read_only_fields = ["total", "grade", "remarks", "published_at", "updated_at"]

    def get_student_name(self, obj) -> str:
        return obj.student.get_full_name() or obj.student.username

    def get_admission_number(self, obj) -> str | None:
        profile = getattr(obj.student, "profile", None)
        return profile.admission_number if profile else None

    def validate(self, attrs):
        subject = attrs.get("subject") or getattr(self.instance, "subject", None)
        student = attrs.get("student") or getattr(self.instance, "student", None)

        if subject and student:
            profile = getattr(student, "profile", None)
            if profile is None or profile.school_class_id != subject.school_class_id:
                raise serializers.ValidationError({"student": "This student is not in the subject's class."})
        return attrs


class LessonNoteSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    class_name = serializers.CharField(source="subject.school_class.name", read_only=True)
    school_class = serializers.IntegerField(source="subject.school_class_id", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True, default=None)

    class Meta:
        model = LessonNote
        fields = [
            "id",
            "subject",
            "subject_name",
            "school_class",
            "class_name",
            "term",
            "term_name",
            "week_number",
            "topic",
            "content",
            "attachment",
            "status",
            "published_at",
            "created_at",
        ]
        read_only_fields = ["published_at", "created_at"]


class AnnouncementSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="school_class.name", read_only=True, default=None)
    audience = serializers.CharField(read_only=True)
    author = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = [
            "id",
            "title",
            "body",
            "school_class",
            "class_name",
            "audience",
            "author",
            "status",
            "published_at",
            "created_at",
        ]
        read_only_fields = ["published_at", "created_at"]

    def get_author(self, obj) -> str | None:
        user = obj.created_by
        if user is None:
            return None
        return user.get_full_name() or user.username


class AssignmentSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)
    class_name = serializers.CharField(source="school_class.name", read_only=True, default=None)
    term_name = serializers.CharField(source="term.name", read_only=True, default=None)
    submissions_count = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Assignment
        fields = [
            "id",
            "title",
            "due_date",
            "kind",
            "subject",
            "subject_name",
            "school_class",
            "class_name",
            "term",
            "term_name",
            "marks_total",
            "status",
            "published_at",
            "is_overdue",
            "submissions_count",
            "created_at",
        ]
        read_only_fields = ["published_at", "created_at"]

    def get_submissions_count(self, obj) -> int:
        return obj.submissions.count()

    def validate(self, attrs):
        subject = attrs.get("subject") or getattr(self.instance, "subject", None)
        school_class = attrs.get("school_class") or getattr(self.instance, "school_class", None)
        if subject and school_class and subject.school_class_id != school_class.pk:
            raise serializers.ValidationError(
                {"school_class": "The class does not match the chosen subject."}
            )
        return attrs


class SubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    assignment_title = serializers.CharField(source="assignment.title", read_only=True)
    class_name = serializers.CharField(source="assignment.school_class.name", read_only=True, default=None)
    is_graded = serializers.BooleanField(read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "assignment",
            "assignment_title",
            "class_name",
            "student",
            "student_name",
            "file",
            "note",
            "submitted_at",
            "marks",
            "feedback",
            "is_graded",
        ]
        read_only_fields = ["student", "submitted_at", "marks", "feedback"]

    def get_student_name(self, obj) -> str:
        return obj.student.get_full_name() or obj.student.username

    def validate_assignment(self, assignment):
        request = self.context.get("request")
        if request and Submission.objects.filter(assignment=assignment, student=request.user).exists():
            raise serializers.ValidationError("You have already submitted this assignment.")
        return assignment


class GradingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = ["marks", "feedback"]

    def validate_marks(self, marks):
        assignment = self.instance.assignment
        if marks is not None and assignment.marks_total and marks > assignment.marks_total:
            raise serializers.ValidationError(
                f"Marks cannot exceed {assignment.marks_total} for this assignment."
            )
        return marks


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    class_name = serializers.CharField(source="school_class.name", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "school_class",
            "class_name",
            "student",
            "student_name",
            "date",
            "status",
        ]

    def get_student_name(self, obj) -> str:
        return obj.student.get_full_name() or obj.student.username

    def validate(self, attrs):
        if self.instance is None and not attrs.get("school_class"):
            raise serializers.ValidationError({"school_class": "A class is required."})
        return attrs


class ScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Schedule
        fields = ["id", "name", "day", "time"]


class StudentImportRowSerializer(serializers.Serializer):
    """One row of the CSV a class teacher uploads to onboard students."""

    full_name = serializers.CharField(max_length=150)
    admission_number = serializers.CharField(max_length=20)
    gender = serializers.ChoiceField(choices=Profile.GENDER_CHOICES, required=False, allow_blank=True)

    def validate_full_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("A full name is required.")
        return value.strip()


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        if value == self.initial_data.get("current_password"):
            raise serializers.ValidationError("Choose a password different from the current one.")
        return value
