"""Headless JSON API for a Nigerian primary/secondary school.

Django serves JSON only. The visibility rule lives here and in the models: a
student only ever receives rows whose ``status`` is ``published`` and which
belong to their own class. Teachers see everything they own, drafts included.
"""

import csv
import io

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import (
    CA_MAX,
    EXAM_MAX,
    AcademicSession,
    Announcement,
    Assignment,
    Attendance,
    LessonNote,
    Profile,
    PublishStatus,
    Result,
    Schedule,
    SchoolClass,
    Subject,
    Submission,
    Term,
    is_teacher,
    role_of,
)
from .permissions import IsStaffOrReadOnly, IsTeacher
from .reports import build_broadsheet, build_report_card
from .serializers import (
    AcademicSessionSerializer,
    AnnouncementSerializer,
    AssignmentSerializer,
    AttendanceSerializer,
    GradingSerializer,
    LessonNoteSerializer,
    PasswordChangeSerializer,
    ResultSerializer,
    ScheduleSerializer,
    SchoolClassSerializer,
    StudentImportRowSerializer,
    SubjectSerializer,
    SubmissionSerializer,
    TermSerializer,
)

RESULT_IMPORT_COLUMNS = ["Admission Number", "Subject", "CA1", "CA2", "CA3", "Exam"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def profile_for(user) -> Profile:
    profile, _created = Profile.objects.get_or_create(user=user)
    return profile


def student_class_id(user):
    return profile_for(user).school_class_id


def apply_term_filters(queryset, request, prefix=""):
    session = request.query_params.get("session")
    term = request.query_params.get("term")
    if session:
        queryset = queryset.filter(**{f"{prefix}session_id": session})
    if term:
        queryset = queryset.filter(**{f"{prefix}term_id": term})
    return queryset


def normalise_gender(value) -> str:
    text = (value or "").strip().lower()
    if text.startswith("m"):
        return Profile.MALE
    if text.startswith("f"):
        return Profile.FEMALE
    return ""


def resolve_period(request) -> tuple[AcademicSession, Term]:
    """Return the (session, term) a report or import is about.

    An explicit ``term`` wins; otherwise the current term is used. A supplied
    ``session`` must agree with the term's own session.
    """
    term_id = request.query_params.get("term")
    session_id = request.query_params.get("session")

    if term_id:
        term = Term.objects.select_related("session").filter(pk=term_id).first()
        if term is None:
            raise ValidationError({"term": "No such term."})
    else:
        term = Term.current()
        if term is None:
            raise ValidationError({"term": "No current term is set."})

    if session_id and str(session_id) != str(term.session_id):
        raise ValidationError({"session": "That session does not match the term."})
    return term.session, term


def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class HealthView(APIView):
    """Unversioned readiness probe for the deployment platform."""

    permission_classes = [AllowAny]
    authentication_classes = ()  # type: ignore[assignment]

    def get(self, request):
        return Response({"status": "ok"})


class TokenLoginView(TokenObtainPairView):
    """JWT login for the SPA.

    Session authentication is disabled on purpose: it would make DRF enforce CSRF
    against a browser that also holds a Django session cookie.
    """

    authentication_classes = ()


class TokenRefreshAPIView(TokenRefreshView):
    authentication_classes = ()


class MeView(APIView):
    """Who am I, which portal, and must this password be changed?"""

    def get(self, request):
        user = request.user
        profile = profile_for(user)
        school_class = profile.school_class
        return Response(
            {
                "id": user.pk,
                "username": user.username,
                "name": user.get_full_name() or user.username,
                "email": user.email,
                "role": role_of(user),
                "is_staff": user.is_staff,
                "admission_number": profile.admission_number,
                "gender": profile.gender,
                "school_class": school_class.pk if school_class else None,
                "class_name": school_class.name if school_class else None,
                "must_change_password": profile.must_change_password,
            }
        )


class PasswordChangeView(APIView):
    """First-login password change for students (and anyone else)."""

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        Profile.objects.filter(user=request.user).update(must_change_password=False)

        refresh = RefreshToken.for_user(request.user)
        return Response(
            {
                "detail": "Password updated.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        )


# ---------------------------------------------------------------------------
# Sessions and terms (set up by the school office)
# ---------------------------------------------------------------------------
class AcademicSessionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AcademicSession.objects.all()
    serializer_class = AcademicSessionSerializer


class TermViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TermSerializer

    def get_queryset(self):
        queryset = Term.objects.select_related("session")
        session = self.request.query_params.get("session")
        if session:
            queryset = queryset.filter(session_id=session)
        return queryset

    @action(detail=False, methods=["get"])
    def current(self, request):
        term = Term.current()
        if term is None:
            return Response({"detail": "No current term is set."}, status=404)
        return Response(
            {
                "term": TermSerializer(term).data,
                "session": AcademicSessionSerializer(term.session).data,
            }
        )


# ---------------------------------------------------------------------------
# Publishable content
# ---------------------------------------------------------------------------
class PublishableViewSet(viewsets.ModelViewSet):
    """Base for content a teacher drafts, then publishes to their class.

    ``class_lookup`` is the ORM path from this model to a ``SchoolClass``.
    """

    class_lookup = "school_class"

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsTeacher()]

    def student_queryset(self, queryset, user):
        class_id = student_class_id(user)
        if not class_id:
            return queryset.none()
        return queryset.filter(status=PublishStatus.PUBLISHED, **{self.class_lookup: class_id})

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        instance = self.get_object()
        instance.publish()
        instance.save()
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        instance = self.get_object()
        instance.status = PublishStatus.ARCHIVED
        instance.save()
        return Response(self.get_serializer(instance).data)


class ResultViewSet(PublishableViewSet):
    serializer_class = ResultSerializer
    class_lookup = "subject__school_class"

    def get_queryset(self):
        user = self.request.user
        queryset = Result.objects.select_related(
            "subject__school_class", "student__profile", "session", "term"
        )
        if is_teacher(user):
            queryset = queryset.filter(
                Q(created_by=user) | Q(subject__teacher=user) | Q(subject__school_class__class_teacher=user)
            ).distinct()
        else:
            queryset = self.student_queryset(queryset, user).filter(student=user)

        queryset = apply_term_filters(queryset, self.request)
        subject = self.request.query_params.get("subject")
        if subject:
            queryset = queryset.filter(subject_id=subject)
        student = self.request.query_params.get("student")
        if student:
            queryset = queryset.filter(student_id=student)
        return queryset

    def perform_create(self, serializer):
        subject = serializer.validated_data["subject"]
        if not subject.can_manage(self.request.user):
            raise PermissionDenied("You can only enter results for subjects you teach.")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        subject = serializer.validated_data.get("subject") or serializer.instance.subject
        if not subject.can_manage(self.request.user):
            raise PermissionDenied("You can only change results for subjects you teach.")
        serializer.save()


class LessonNoteViewSet(PublishableViewSet):
    serializer_class = LessonNoteSerializer
    class_lookup = "subject__school_class"
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        user = self.request.user
        queryset = LessonNote.objects.select_related("subject__school_class", "term")
        if is_teacher(user):
            queryset = queryset.filter(
                Q(created_by=user) | Q(subject__teacher=user) | Q(subject__school_class__class_teacher=user)
            ).distinct()
        else:
            queryset = self.student_queryset(queryset, user)

        queryset = apply_term_filters(queryset, self.request)
        subject = self.request.query_params.get("subject")
        if subject:
            queryset = queryset.filter(subject_id=subject)
        return queryset

    def perform_create(self, serializer):
        subject = serializer.validated_data["subject"]
        if not subject.can_manage(self.request.user):
            raise PermissionDenied("You can only write notes for subjects you teach.")
        serializer.save(created_by=self.request.user)


class AnnouncementViewSet(PublishableViewSet):
    serializer_class = AnnouncementSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Announcement.objects.select_related("school_class", "created_by")
        if is_teacher(user):
            return queryset
        class_id = student_class_id(user)
        return queryset.filter(
            Q(school_class__isnull=True) | Q(school_class_id=class_id),
            status=PublishStatus.PUBLISHED,
        ).distinct()

    def perform_create(self, serializer):
        school_class = serializer.validated_data.get("school_class")
        user = self.request.user
        if school_class is not None and not school_class.can_manage(user):
            raise PermissionDenied("You can only post to your own class.")
        serializer.save(created_by=user)


class AssignmentViewSet(PublishableViewSet):
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Assignment.objects.select_related("subject", "school_class", "term")
        if is_teacher(user):
            queryset = queryset.filter(
                Q(created_by=user) | Q(subject__teacher=user) | Q(school_class__class_teacher=user)
            ).distinct()
        else:
            queryset = self.student_queryset(queryset, user)

        queryset = apply_term_filters(queryset, self.request)
        school_class = self.request.query_params.get("class")
        if school_class:
            queryset = queryset.filter(school_class_id=school_class)
        return queryset

    def perform_create(self, serializer):
        school_class = serializer.validated_data.get("school_class")
        subject = serializer.validated_data.get("subject")
        user = self.request.user

        managed_class = school_class or (subject.school_class if subject else None)
        if managed_class is None:
            raise PermissionDenied("Choose the class this assignment is for.")
        if not managed_class.can_manage(user):
            raise PermissionDenied("You can only set work for your own class.")
        if subject is not None and subject.school_class_id != managed_class.pk:
            raise PermissionDenied("That subject is not taught in this class.")

        serializer.save(created_by=user, school_class=managed_class)


# ---------------------------------------------------------------------------
# Classes, subjects, students
# ---------------------------------------------------------------------------
class SchoolClassViewSet(viewsets.ModelViewSet):
    serializer_class = SchoolClassSerializer

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsAuthenticated(), IsStaffOrReadOnly()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        queryset = SchoolClass.objects.select_related("class_teacher").prefetch_related("students__user")
        if user.is_staff:
            return queryset
        if is_teacher(user):
            return queryset.filter(Q(class_teacher=user) | Q(subjects__teacher=user)).distinct()
        class_id = student_class_id(user)
        return queryset.filter(pk=class_id) if class_id else queryset.none()

    @action(
        detail=True,
        methods=["post"],
        url_path="import-students",
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def import_students(self, request, pk=None):
        """Bulk-onboard students from a CSV file or a JSON array.

        Columns: Full Name, Admission Number, Gender. Each student gets the
        admission number as their username and a default password that must be
        changed on first login.
        """
        school_class = self.get_object()
        if not school_class.can_manage(request.user):
            raise PermissionDenied("Only the class teacher can add students.")

        rows = self._extract_rows(request)
        if rows is None:
            return Response(
                {
                    "detail": "Upload a CSV with columns Full Name, Admission Number, Gender, "
                    "or send a 'students' array."
                },
                status=400,
            )
        if not rows:
            return Response({"detail": "No student rows found."}, status=400)

        if school_class.student_count + len(rows) > school_class.capacity:
            return Response(
                {
                    "detail": (
                        f"{school_class.name} can hold {school_class.capacity} students "
                        f"and already has {school_class.student_count}."
                    )
                },
                status=400,
            )

        created: list[str] = []
        skipped: list[dict] = []

        with transaction.atomic():
            for row in rows:
                serializer = StudentImportRowSerializer(data=row)
                if not serializer.is_valid():
                    reasons = [
                        f"{field}: {message}"
                        for field, messages in serializer.errors.items()
                        for message in messages
                    ]
                    skipped.append(
                        {
                            "admission_number": row.get("admission_number", ""),
                            "reason": "; ".join(reasons),
                        }
                    )
                    continue

                data = serializer.validated_data
                admission_number = data["admission_number"].strip()
                if User.objects.filter(username__iexact=admission_number).exists():
                    skipped.append(
                        {
                            "admission_number": admission_number,
                            "reason": "A user with this admission number already exists.",
                        }
                    )
                    continue

                first_name, last_name = split_name(data["full_name"])
                user = User.objects.create_user(
                    username=admission_number,
                    password=settings.DEFAULT_STUDENT_PASSWORD,
                    first_name=first_name,
                    last_name=last_name,
                )
                Profile.objects.update_or_create(
                    user=user,
                    defaults={
                        "role": Profile.STUDENT,
                        "admission_number": admission_number,
                        "gender": data.get("gender") or "",
                        "school_class": school_class,
                        "must_change_password": True,
                    },
                )
                created.append(admission_number)

        # Re-read so the reported roster size reflects the rows just created
        # (the instance above carries a prefetched, now-stale student list).
        refreshed = SchoolClass.objects.get(pk=school_class.pk)
        return Response(
            {
                "created": created,
                "created_count": len(created),
                "skipped": skipped,
                "skipped_count": len(skipped),
                "class": SchoolClassSerializer(refreshed).data,
                "default_password": settings.DEFAULT_STUDENT_PASSWORD,
            },
            status=201,
        )

    def _extract_rows(self, request):
        upload = request.FILES.get("file")
        if upload is not None:
            return self._rows_from_csv(upload)
        rows = request.data.get("students")
        if isinstance(rows, list):
            return rows
        return None

    def _rows_from_csv(self, upload):
        raw = upload.read()
        text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else raw
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for raw_row in reader:
            row = {}
            for key, value in raw_row.items():
                if key is None:
                    continue
                column = key.strip().lower().replace("_", " ").replace("-", " ")
                if column in {"full name", "name", "student name"}:
                    row["full_name"] = (value or "").strip()
                elif column in {"admission number", "admission no", "admission"}:
                    row["admission_number"] = (value or "").strip()
                elif column == "gender":
                    row["gender"] = normalise_gender(value)
            if any(row.values()):
                rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # Term reporting and bulk result entry
    # ------------------------------------------------------------------
    @action(detail=True, methods=["get"])
    def broadsheet(self, request, pk=None):
        """Students × subjects totals, averages and class positions."""
        school_class = self.get_object()
        if not school_class.can_manage(request.user):
            raise PermissionDenied("Only the class teacher or a principal can open the broadsheet.")
        session, term = resolve_period(request)
        return Response(build_broadsheet(school_class, session, term))

    @action(detail=True, methods=["get"], url_path="results/template")
    def results_template(self, request, pk=None):
        """A blank CSV with the columns the importer expects."""
        school_class = self.get_object()
        if not school_class.can_manage(request.user):
            raise PermissionDenied("Only the class teacher can download a result template.")
        _session, term = resolve_period(request)

        response = HttpResponse(content_type="text/csv")
        filename = f"results-template-{slugify(school_class.name)}-term-{term.pk}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow(RESULT_IMPORT_COLUMNS)
        return response

    @action(
        detail=True,
        methods=["post"],
        url_path="results/bulk-import",
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def bulk_import_results(self, request, pk=None):
        """Create or update results from a CSV (or a JSON ``rows`` array).

        New rows are saved as drafts so the teacher reviews them before
        publishing; existing rows keep whatever status they already had.
        Valid rows are imported even when other rows fail validation.
        """
        school_class = self.get_object()
        if not school_class.can_manage(request.user):
            raise PermissionDenied("Only the class teacher can import results.")
        session, term = resolve_period(request)

        numbered_rows = self._extract_result_rows(request)
        if numbered_rows is None:
            return Response(
                {
                    "detail": "Upload a CSV with columns "
                    + ", ".join(RESULT_IMPORT_COLUMNS)
                    + ", or send a 'rows' array."
                },
                status=400,
            )
        if not numbered_rows:
            return Response({"detail": "No result rows found."}, status=400)

        students = {
            profile.admission_number.strip().upper(): profile.user
            for profile in school_class.students.select_related("user")
            if profile.admission_number
        }
        subjects = {subject.name.strip().lower(): subject for subject in school_class.subjects.all()}

        created = 0
        updated = 0
        errors: list[dict] = []

        with transaction.atomic():
            for line_number, row in numbered_rows:
                cleaned, reason = self._clean_result_row(row, students, subjects)
                if reason:
                    errors.append({"row": line_number, "reason": reason})
                    continue

                student, subject, scores = cleaned
                result = Result.objects.filter(
                    student=student, subject=subject, session=session, term=term
                ).first()
                if result is None:
                    result = Result(student=student, subject=subject, session=session, term=term)
                    created += 1
                else:
                    updated += 1

                for field, value in scores.items():
                    setattr(result, field, value)
                result.created_by = request.user
                # save() recomputes total, grade and remark from the components.
                result.save()

        return Response(
            {
                "class": {"id": school_class.pk, "name": school_class.name},
                "session": {"id": session.pk, "name": session.name},
                "term": {"id": term.pk, "name": term.name},
                "created": created,
                "updated": updated,
                "errors": errors,
                "total_rows": len(numbered_rows),
            }
        )

    def _extract_result_rows(self, request):
        upload = request.FILES.get("file")
        if upload is not None:
            return self._result_rows_from_csv(upload)
        rows = request.data.get("rows")
        if isinstance(rows, list):
            return [(index + 2, row) for index, row in enumerate(rows) if isinstance(row, dict)]
        return None

    def _result_rows_from_csv(self, upload):
        raw = upload.read()
        text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else raw
        reader = csv.DictReader(io.StringIO(text))
        headings = {
            (name or "").strip().lower().replace("_", " ").replace("-", " ")
            for name in reader.fieldnames or []
        }
        if not headings & {"admission number", "admission no", "admission"}:
            raise ValidationError({"file": "The CSV needs an Admission Number column."})

        rows = []
        for index, raw_row in enumerate(reader, start=2):
            row = {}
            for key, value in raw_row.items():
                if key is None:
                    continue
                column = key.strip().lower().replace("_", " ").replace("-", " ")
                text_value = (value or "").strip()
                if column in {"admission number", "admission no", "admission"}:
                    row["admission_number"] = text_value
                elif column == "subject":
                    row["subject"] = text_value
                elif column in {"ca1", "ca2", "ca3", "exam"}:
                    row[column] = text_value
            if any(str(value).strip() for value in row.values()):
                rows.append((index, row))
        return rows

    def _clean_result_row(self, row, students, subjects):
        """Return ``((student, subject, scores), "")`` or ``(None, reason)``."""
        admission = str(row.get("admission_number", "")).strip()
        if not admission:
            return None, "Admission number is required."
        student = students.get(admission.upper())
        if student is None:
            return None, f"Admission number {admission} is not in this class."

        subject_name = str(row.get("subject", "")).strip()
        if not subject_name:
            return None, "Subject is required."
        subject = subjects.get(subject_name.lower())
        if subject is None:
            return None, f"{subject_name} is not taught in this class."

        scores = {}
        for field in ("ca1", "ca2", "ca3", "exam"):
            label = "Exam" if field == "exam" else field.upper()
            raw = str(row.get(field, "")).strip()
            maximum = EXAM_MAX if field == "exam" else CA_MAX[field]
            if raw == "":
                scores[field] = 0
                continue
            try:
                value = int(raw)
            except ValueError:
                return None, f"{label} must be a whole number."
            if value < 0:
                return None, f"{label} cannot be negative."
            if value > maximum:
                return None, f"{label} score {value} exceeds maximum of {maximum}."
            scores[field] = value

        return (student, subject, scores), ""


class SubjectViewSet(viewsets.ModelViewSet):
    serializer_class = SubjectSerializer

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        user = self.request.user
        queryset = Subject.objects.select_related("school_class", "teacher")
        if user.is_staff:
            return queryset
        if is_teacher(user):
            return queryset.filter(Q(teacher=user) | Q(school_class__class_teacher=user)).distinct()
        class_id = student_class_id(user)
        return queryset.filter(school_class_id=class_id) if class_id else queryset.none()

    def perform_create(self, serializer):
        user = self.request.user
        school_class = serializer.validated_data["school_class"]
        teacher = serializer.validated_data.get("teacher") or user

        if not school_class.can_manage(user):
            raise PermissionDenied("You can only add subjects to your own class.")
        if not (user.is_staff or teacher.pk == user.pk):
            raise PermissionDenied("You cannot assign another teacher to a subject.")
        serializer.save(teacher=teacher)

    def perform_update(self, serializer):
        subject = serializer.instance
        if not subject.can_manage(self.request.user):
            raise PermissionDenied("You can only change subjects in your own class.")
        serializer.save()


# ---------------------------------------------------------------------------
# Submissions and attendance
# ---------------------------------------------------------------------------
class SubmissionViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        queryset = Submission.objects.select_related(
            "assignment", "assignment__school_class", "assignment__subject", "student"
        )
        if is_teacher(user):
            return queryset.filter(
                Q(assignment__created_by=user)
                | Q(assignment__subject__teacher=user)
                | Q(assignment__school_class__class_teacher=user)
            ).distinct()
        return queryset.filter(student=user)

    def get_serializer_class(self):
        if self.action == "grade":
            return GradingSerializer
        return SubmissionSerializer

    def perform_create(self, serializer):
        assignment = serializer.validated_data["assignment"]
        user = self.request.user

        if assignment.status != PublishStatus.PUBLISHED:
            raise PermissionDenied("This assignment is not open for submissions.")
        if assignment.school_class_id:
            profile = profile_for(user)
            if profile.school_class_id != assignment.school_class_id:
                raise PermissionDenied("This assignment is for another class.")
        serializer.save(student=user)

    @action(detail=True, methods=["patch"])
    def grade(self, request, pk=None):
        submission = self.get_object()
        assignment = submission.assignment
        user = request.user

        can_grade = (
            user.is_staff
            or assignment.created_by_id == user.pk
            or (assignment.subject_id and assignment.subject.teacher_id == user.pk)
            or (assignment.school_class_id and assignment.school_class.class_teacher_id == user.pk)
        )
        if not can_grade:
            raise PermissionDenied("Only the teacher who set this work can grade it.")

        serializer = GradingSerializer(submission, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(graded_by=user, graded_at=timezone.now())
        return Response(SubmissionSerializer(submission, context={"request": request}).data)


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Attendance.objects.select_related("school_class", "student")
        if is_teacher(user):
            queryset = queryset.filter(
                Q(school_class__class_teacher=user) | Q(school_class__subjects__teacher=user)
            ).distinct()
        else:
            queryset = queryset.filter(student=user)

        school_class = self.request.query_params.get("class")
        date = self.request.query_params.get("date")
        if school_class:
            queryset = queryset.filter(school_class_id=school_class)
        if date:
            queryset = queryset.filter(date=date)
        return queryset

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy", "bulk"}:
            return [IsAuthenticated(), IsTeacher()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        school_class = serializer.validated_data["school_class"]
        if not school_class.can_manage(self.request.user):
            raise PermissionDenied("You can only mark attendance for your own class.")
        serializer.save(marked_by=self.request.user)

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Upsert a whole class register for one date."""
        school_class = get_object_or_404(SchoolClass, pk=request.data.get("class"))
        if not school_class.can_manage(request.user):
            raise PermissionDenied("You can only mark attendance for your own class.")

        date = request.data.get("date")
        records = request.data.get("records", [])
        if not date or not records:
            return Response({"detail": "A date and at least one record are required."}, status=400)

        saved = []
        for record in records:
            entry, _created = Attendance.objects.update_or_create(
                school_class=school_class,
                student_id=record["student"],
                date=date,
                defaults={
                    "status": record.get("status", Attendance.PRESENT),
                    "marked_by": request.user,
                },
            )
            saved.append(entry)
        return Response(AttendanceSerializer(saved, many=True).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        rows = (
            self.get_queryset()
            .values("school_class__id", "school_class__name", "status")
            .annotate(total=Count("id"))
        )
        summary = {}
        for row in rows:
            key = (row["school_class__id"], row["school_class__name"])
            entry = summary.setdefault(
                key,
                {
                    "school_class": key[0],
                    "class_name": key[1],
                    "present": 0,
                    "late": 0,
                    "absent": 0,
                },
            )
            entry[row["status"]] = row["total"]
        return Response(list(summary.values()))


class StudentReportCardView(APIView):
    """A print-ready HTML report card for one student and term.

    Accessible to the student, their class teacher, and staff. The page carries
    its own print CSS so the browser can "Save as PDF" without a server-side
    PDF toolchain.
    """

    def get(self, request, pk):
        student = get_object_or_404(User.objects.select_related("profile"), pk=pk)
        profile = profile_for(student)
        school_class = profile.school_class
        if school_class is None:
            raise ValidationError({"student": "This student is not in a class."})

        allowed = (
            request.user.is_staff
            or request.user.pk == student.pk
            or school_class.class_teacher_id == request.user.pk
        )
        if not allowed:
            raise PermissionDenied(
                "Only the student, their class teacher or a principal can open this report card."
            )

        session, term = resolve_period(request)
        context = build_report_card(student, session, term)
        if context is None:
            raise ValidationError({"student": "This student is not enrolled in that class."})
        context["request"] = request
        return render(request, "reports/report_card.html", context)


class ScheduleViewSet(viewsets.ModelViewSet):
    """A student's personal timetable; always scoped to the caller."""

    serializer_class = ScheduleSerializer
    throttle_scope = "schedule"

    def get_queryset(self):
        return Schedule.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
