"""Timed multiple-choice quizzes (CBT).

The timer is enforced on the server: an attempt's deadline is derived from its
stored ``started_at``, never from a value the browser sends. A one-minute grace
window absorbs network lag, after which a submission is refused.
"""

from __future__ import annotations

from datetime import timedelta
from statistics import mean

from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import (
    Profile,
    Quiz,
    QuizAttempt,
    QuizAttemptStatus,
    QuizStatus,
    role_of,
)
from .serializers import QuestionSerializer, QuestionStudentSerializer, QuizSerializer, StudentQuizSerializer

GRACE_SECONDS = 60
PASS_RATIO = 0.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def student_profile(user) -> Profile | None:
    return Profile.objects.filter(user=user, role=Profile.STUDENT).first()


def require_student(request) -> Profile:
    profile = student_profile(request.user)
    if profile is None:
        raise PermissionDenied("Only students can take quizzes.")
    return profile


def can_manage_quiz(user, quiz: Quiz) -> bool:
    if user.is_staff:
        return True
    return bool(quiz.class_arm.can_manage(user) or quiz.subject.teacher_id == user.pk)


def require_manager(request, quiz: Quiz) -> None:
    if not can_manage_quiz(request.user, quiz):
        raise PermissionDenied("Only the teacher who set this quiz can manage it.")


def deadline_for(attempt: QuizAttempt):
    return attempt.started_at + timedelta(minutes=attempt.quiz.time_limit_minutes)


def percentage_for(score: int, total_points: int) -> float:
    return round(score / total_points * 100, 1) if total_points else 0.0


def passed_for(score: int, total_points: int) -> bool:
    return bool(total_points) and score / total_points >= PASS_RATIO


def attempt_payload(attempt: QuizAttempt) -> dict:
    return {
        "id": attempt.pk,
        "quiz": attempt.quiz_id,
        "started_at": attempt.started_at,
        "submitted_at": attempt.submitted_at,
        "score": attempt.score,
        "total_points": attempt.quiz.total_points,
        "percentage": percentage_for(attempt.score, attempt.quiz.total_points),
        "passed": passed_for(attempt.score, attempt.quiz.total_points),
        "status": attempt.status,
    }


def _parse_answers(raw, quiz: Quiz) -> dict[int, int]:
    """Accept ``[{question, selected_option}]`` or ``{question_id: index}``."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, list):
        pairs = [
            (item.get("question"), item.get("selected_option")) for item in raw if isinstance(item, dict)
        ]
    else:
        raise ValidationError({"answers": "Send a list of answers."})

    valid_ids = set(quiz.questions.values_list("id", flat=True))
    answers: dict[int, int] = {}
    for question_id, selected in pairs:
        try:
            question_pk = int(question_id)
        except (TypeError, ValueError) as error:
            raise ValidationError({"answers": "Question ids must be integers."}) from error
        if question_pk not in valid_ids:
            raise ValidationError({"answers": f"Question {question_pk} does not belong to this quiz."})
        if selected is None or selected == "":
            continue
        try:
            index = int(selected)
        except (TypeError, ValueError) as error:
            raise ValidationError({"answers": "Selected options must be integers."}) from error
        if not 0 <= index <= 3:
            raise ValidationError({"answers": "Selected options must be between 0 and 3."})
        answers[question_pk] = index
    return answers


def _grade(quiz: Quiz, answers: dict[int, int]) -> tuple[int, list[dict]]:
    score = 0
    breakdown = []
    for question in quiz.questions.all():
        selected = answers.get(question.pk)
        is_correct = selected == question.correct_option_index
        points_awarded = question.points if is_correct else 0
        score += points_awarded
        breakdown.append(
            {
                "question": question.pk,
                "selected_option": selected,
                "correct_option_index": question.correct_option_index,
                "is_correct": is_correct,
                "points_awarded": points_awarded,
            }
        )
    return score, breakdown


# ---------------------------------------------------------------------------
# Quiz API
# ---------------------------------------------------------------------------
class QuizViewSet(viewsets.ModelViewSet):
    """Quizzes for teachers; read-only summaries for students."""

    def get_serializer_class(self):
        if role_of(self.request.user) == Profile.STUDENT:
            return StudentQuizSerializer
        return QuizSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Quiz.objects.select_related("subject__school_class", "class_arm").prefetch_related(
            "questions"
        )
        if user.is_staff:
            return queryset

        role = role_of(user)
        if role == Profile.TEACHER:
            return queryset.filter(Q(class_arm__class_teacher=user) | Q(subject__teacher=user)).distinct()
        if role == Profile.STUDENT:
            profile = student_profile(user)
            if profile is None or profile.school_class_id is None:
                return queryset.none()
            return queryset.filter(
                class_arm_id=profile.school_class_id,
                status__in=[QuizStatus.PUBLISHED, QuizStatus.CLOSED],
            )
        return queryset.none()

    def _check_class_permission(self, class_arm, subject) -> None:
        user = self.request.user
        if user.is_staff or class_arm.class_teacher_id == user.pk or subject.teacher_id == user.pk:
            return
        raise PermissionDenied("You can only set quizzes for a class you teach.")

    def perform_create(self, serializer):
        self._check_class_permission(
            serializer.validated_data["class_arm"], serializer.validated_data["subject"]
        )
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        quiz = self.get_object()
        require_manager(self.request, quiz)
        self._check_class_permission(
            serializer.validated_data.get("class_arm", quiz.class_arm),
            serializer.validated_data.get("subject", quiz.subject),
        )
        serializer.save()

    def perform_destroy(self, instance):
        require_manager(self.request, instance)
        instance.delete()

    @action(detail=True, methods=["get", "post"])
    def questions(self, request, pk=None):
        """List (GET) or add (POST) questions on a quiz; teacher only."""
        quiz = self.get_object()
        require_manager(request, quiz)

        if request.method == "GET":
            return Response(QuestionSerializer(quiz.questions.all(), many=True).data)

        serializer = QuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.save(quiz=quiz)
        return Response(QuestionSerializer(question).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        quiz = self.get_object()
        require_manager(request, quiz)
        if not quiz.questions.exists():
            raise ValidationError({"questions": "Add at least one question before publishing."})
        quiz.refresh_total_points()
        quiz.status = QuizStatus.PUBLISHED
        quiz.save(update_fields=["status"])
        return Response(QuizSerializer(quiz).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        quiz = self.get_object()
        require_manager(request, quiz)
        quiz.status = QuizStatus.CLOSED
        quiz.save(update_fields=["status"])
        return Response(QuizSerializer(quiz).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start or resume this student's attempt and return the questions."""
        profile = require_student(request)
        quiz = get_object_or_404(self.get_queryset(), pk=pk)
        if quiz.class_arm_id != profile.school_class_id:
            raise Http404("No such quiz.")
        if quiz.status != QuizStatus.PUBLISHED:
            raise ValidationError({"detail": "This quiz is closed."})
        if not quiz.is_open:
            raise ValidationError({"detail": "This quiz is not open yet or has closed."})
        if not quiz.questions.exists():
            raise ValidationError({"detail": "This quiz has no questions yet."})

        attempt = QuizAttempt.objects.filter(quiz=quiz, student=request.user).first()
        if attempt is not None and attempt.status == QuizAttemptStatus.AUTO_GRADED:
            raise ValidationError({"detail": "You have already submitted this quiz."})
        if attempt is None:
            attempt = QuizAttempt.objects.create(quiz=quiz, student=request.user)

        return Response(
            {
                "attempt": {
                    "id": attempt.pk,
                    "quiz": quiz.pk,
                    "started_at": attempt.started_at,
                    "expires_at": deadline_for(attempt),
                    "status": attempt.status,
                },
                "quiz": {
                    "id": quiz.pk,
                    "title": quiz.title,
                    "time_limit_minutes": quiz.time_limit_minutes,
                    "total_points": quiz.total_points,
                },
                "questions": QuestionStudentSerializer(quiz.questions.all(), many=True).data,
            }
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Auto-grade answers if the attempt is still within its grace window."""
        require_student(request)
        quiz = get_object_or_404(self.get_queryset(), pk=pk)
        attempt = QuizAttempt.objects.filter(quiz=quiz, student=request.user).first()
        if attempt is None:
            raise ValidationError({"detail": "Start the quiz before submitting."})
        if attempt.status == QuizAttemptStatus.AUTO_GRADED:
            raise ValidationError({"detail": "This quiz has already been submitted."})

        deadline = deadline_for(attempt)
        now = timezone.now()
        if now > deadline + timedelta(seconds=GRACE_SECONDS):
            raise ValidationError({"detail": "Time expired", "deadline": deadline})

        answers = _parse_answers(request.data.get("answers"), quiz)
        score, breakdown = _grade(quiz, answers)

        attempt.score = score
        attempt.answers = {str(question_id): index for question_id, index in answers.items()}
        attempt.submitted_at = now
        attempt.status = QuizAttemptStatus.AUTO_GRADED
        attempt.save(update_fields=["score", "answers", "submitted_at", "status"])

        return Response({"attempt": attempt_payload(attempt), "answers": breakdown})

    @action(detail=True, methods=["get"])
    def attempts(self, request, pk=None):
        """Every student's attempt, with pass/fail counts and the class average."""
        quiz = self.get_object()
        require_manager(request, quiz)

        rows = []
        for attempt in quiz.attempts.select_related("student__profile").order_by(
            "-score", "student__first_name", "student__last_name"
        ):
            profile = getattr(attempt.student, "profile", None)
            rows.append(
                {
                    "id": attempt.pk,
                    "student": attempt.student_id,
                    "student_name": attempt.student.get_full_name() or attempt.student.get_username(),
                    "admission_number": profile.admission_number if profile else None,
                    "started_at": attempt.started_at,
                    "submitted_at": attempt.submitted_at,
                    "score": attempt.score,
                    "percentage": percentage_for(attempt.score, quiz.total_points),
                    "passed": passed_for(attempt.score, quiz.total_points),
                    "status": attempt.status,
                }
            )

        graded = [row for row in rows if row["status"] == QuizAttemptStatus.AUTO_GRADED]
        percentages = [row["percentage"] for row in graded]
        scores = [row["score"] for row in graded]

        return Response(
            {
                "quiz": {
                    "id": quiz.pk,
                    "title": quiz.title,
                    "total_points": quiz.total_points,
                    "pass_mark": quiz.total_points * PASS_RATIO,
                },
                "attempts": rows,
                "summary": {
                    "total": len(rows),
                    "graded": len(graded),
                    "in_progress": len(rows) - len(graded),
                    "average_score": round(mean(scores), 1) if scores else None,
                    "average_percentage": round(mean(percentages), 1) if percentages else None,
                    "passed": sum(1 for row in graded if row["passed"]),
                    "failed": sum(1 for row in graded if not row["passed"]),
                },
            }
        )
