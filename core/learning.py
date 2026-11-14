"""Learning hub: lesson resources, completion tracking and performance trends.

Students only ever see resources on published lessons for their own class. The
term-over-term trend is calculated from published results with an ORM query
rather than a stored table, so it cannot drift from the marks it summarises.
"""

from __future__ import annotations

from statistics import mean

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    LessonNote,
    LessonResource,
    Profile,
    PublishStatus,
    ResourceProgress,
    Result,
    Term,
    role_of,
)
from .serializers import LessonResourceSerializer

TERM_ORDER = {Term.FIRST: 1, Term.SECOND: 2, Term.THIRD: 3}


def student_profile(user) -> Profile | None:
    return Profile.objects.filter(user=user, role=Profile.STUDENT).first()


def require_student(request) -> Profile:
    profile = student_profile(request.user)
    if profile is None:
        raise PermissionDenied("Only students have a learning dashboard.")
    return profile


def lesson_for(request, pk) -> LessonNote:
    """The lesson if this user may see it, otherwise 404."""
    lesson = get_object_or_404(LessonNote.objects.select_related("subject__school_class", "term"), pk=pk)
    user = request.user
    if user.is_staff:
        return lesson

    role = role_of(user)
    if role == Profile.STUDENT:
        profile = student_profile(user)
        if (
            lesson.status == PublishStatus.PUBLISHED
            and profile is not None
            and profile.school_class_id == lesson.subject.school_class_id
        ):
            return lesson
        raise Http404("No such lesson.")

    if role == Profile.TEACHER and lesson.subject.can_manage(user):
        return lesson
    raise Http404("No such lesson.")


def lesson_payload(lesson: LessonNote) -> dict:
    return {
        "id": lesson.pk,
        "topic": lesson.topic,
        "week_number": lesson.week_number,
        "subject": lesson.subject_id,
        "subject_name": lesson.subject.name,
        "class_name": lesson.subject.school_class.name if lesson.subject.school_class else None,
        "term": lesson.term_id,
        "term_name": lesson.term.name if lesson.term else None,
    }


class LessonResourcesView(APIView):
    """Resources for one lesson; drafts are invisible to students."""

    def get(self, request, pk):
        lesson = lesson_for(request, pk)
        resources = list(lesson.resources.all())

        progress = {}
        if student_profile(request.user) is not None:
            progress = {
                row.resource_id: row
                for row in ResourceProgress.objects.filter(student=request.user, resource__in=resources)
            }

        return Response(
            {
                "lesson": lesson_payload(lesson),
                "resources": LessonResourceSerializer(
                    resources,
                    many=True,
                    context={"request": request, "progress": progress},
                ).data,
            }
        )


class ResourceCompleteView(APIView):
    """Mark one resource as watched/read for the signed-in student."""

    def post(self, request, pk):
        profile = require_student(request)
        resource = get_object_or_404(
            LessonResource.objects.select_related("lesson__subject__school_class"), pk=pk
        )
        lesson = resource.lesson
        if (
            lesson.status != PublishStatus.PUBLISHED
            or lesson.subject.school_class_id != profile.school_class_id
        ):
            raise Http404("No such resource.")

        progress, _created = ResourceProgress.objects.get_or_create(student=request.user, resource=resource)
        already_completed = progress.is_completed
        if not already_completed:
            progress.is_completed = True
            progress.save()

        return Response(
            {
                "resource": resource.pk,
                "lesson": lesson.pk,
                "is_completed": True,
                "already_completed": already_completed,
                "completed_at": progress.completed_at,
            }
        )


def student_performance_trend(student, session=None) -> list[dict]:
    """Published averages per term, oldest first, with each subject's average.

    This is the annotation approach: nothing is stored, so publishing or
    editing a result is reflected immediately.
    """
    results = (
        Result.objects.filter(student=student, status=PublishStatus.PUBLISHED)
        .select_related("subject", "term__session")
        .order_by("session__name", "term__name")
    )
    if session is not None:
        results = results.filter(session=session)

    buckets: dict[tuple[int, int], dict] = {}
    for result in results:
        key = (result.session_id, result.term_id)
        bucket = buckets.setdefault(
            key,
            {
                "session": result.session.name,
                "term": result.term.name,
                "totals": [],
                "subjects": {},
            },
        )
        bucket["totals"].append(result.total)
        bucket["subjects"].setdefault(result.subject.name, []).append(result.total)

    rows = []
    for bucket in buckets.values():
        subjects = [
            {"subject": name, "average": round(mean(values), 1)}
            for name, values in sorted(bucket["subjects"].items())
        ]
        rows.append(
            {
                "session": bucket["session"],
                "term": bucket["term"],
                "average": round(mean(bucket["totals"]), 1),
                "subjects_count": len(subjects),
                "subjects": subjects,
            }
        )

    rows.sort(key=lambda row: (row["session"], TERM_ORDER.get(row["term"], 99), row["term"]))
    return rows


class StudentProgressDashboardView(APIView):
    """Current-term resource completion and term-over-term averages."""

    def get(self, request):
        profile = require_student(request)
        term = Term.current()

        total = 0
        completed = 0
        if profile.school_class_id is not None and term is not None:
            resources = LessonResource.objects.filter(
                lesson__subject__school_class_id=profile.school_class_id,
                lesson__status=PublishStatus.PUBLISHED,
                lesson__term=term,
            )
            total = resources.count()
            completed = ResourceProgress.objects.filter(
                student=request.user, resource__in=resources, is_completed=True
            ).count()

        return Response(
            {
                "term": (
                    {
                        "id": term.pk,
                        "name": term.name,
                        "session_name": term.session.name,
                    }
                    if term is not None
                    else None
                ),
                "resources": {
                    "total": total,
                    "completed": completed,
                    "percentage": round(completed / total * 100) if total else 0,
                },
                "trend": student_performance_trend(
                    request.user, session=term.session if term is not None else None
                ),
            }
        )
