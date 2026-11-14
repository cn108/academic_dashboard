"""Term-level reporting: the class broadsheet and its ranking maths.

Only published results feed a broadsheet, so a draft a teacher is still editing
never reaches a parent-facing document or a position calculation.
"""

from __future__ import annotations

from statistics import mean

from .models import PublishStatus, Result, SchoolClass, Term


def average(values):
    """Mean of the non-empty values, rounded to two decimals, or ``None``."""
    numbers = [value for value in values if value is not None]
    return round(mean(numbers), 2) if numbers else None


def position_map(rows):
    """Rank ``[(key, average)]`` by average, ties sharing a position.

    Competition ranking: two students tied for 2nd are followed by 4th.
    Students without a published average are unranked (``None``).
    """
    ranked = sorted(
        ((key, value) for key, value in rows if value is not None),
        key=lambda row: (-row[1], str(row[0])),
    )
    positions: dict = {}
    previous_value = None
    previous_position = 0
    for index, (key, value) in enumerate(ranked, start=1):
        if value == previous_value:
            positions[key] = previous_position
        else:
            positions[key] = index
            previous_value = value
            previous_position = index
    return positions


def build_broadsheet(school_class: SchoolClass, session, term: Term) -> dict:
    """Students × subjects totals for one class, term and session.

    Each student's average covers the subjects that have a published result,
    so a missing subject does not drag the average down (or break it).
    """
    profiles = list(
        school_class.students.select_related("user").order_by(
            "user__first_name", "user__last_name", "user__username"
        )
    )
    subjects = list(school_class.subjects.all().order_by("name"))

    results = Result.objects.filter(
        subject__school_class=school_class,
        session=session,
        term=term,
        status=PublishStatus.PUBLISHED,
    ).select_related("subject")
    by_student_subject = {(row.student_id, row.subject_id): row for row in results}

    scores_for: dict[int, list[dict]] = {}
    averages: list[tuple[int, float | None]] = []
    for profile in profiles:
        student = profile.user
        scores = []
        for subject in subjects:
            result = by_student_subject.get((student.pk, subject.pk))
            if result is None:
                continue
            scores.append(
                {
                    "subject": subject.pk,
                    "subject_name": subject.name,
                    "ca1": result.ca1,
                    "ca2": result.ca2,
                    "ca3": result.ca3,
                    "exam": result.exam,
                    "total": result.total,
                    "grade": result.grade,
                }
            )
        scores_for[student.pk] = scores
        averages.append((student.pk, average([row["total"] for row in scores])))

    positions = position_map(averages)
    average_for = dict(averages)

    subject_averages = {}
    for subject in subjects:
        totals = [row.total for row in results if row.subject_id == subject.pk]
        subject_averages[subject.pk] = average(totals)

    return {
        "class": {"id": school_class.pk, "name": school_class.name, "level": school_class.level},
        "session": {"id": session.pk, "name": session.name},
        "term": {"id": term.pk, "name": term.name, "session_name": session.name},
        "subjects": [
            {
                "id": subject.pk,
                "name": subject.name,
                "teacher": subject.teacher_id,
                "class_average": subject_averages[subject.pk],
                "results_count": len([row for row in results if row.subject_id == subject.pk]),
            }
            for subject in subjects
        ],
        "students": [
            {
                "id": profile.user_id,
                "full_name": profile.user.get_full_name() or profile.user.get_username(),
                "admission_number": profile.admission_number,
                "scores": scores_for[profile.user_id],
                "subjects_count": len(scores_for[profile.user_id]),
                "total": sum(row["total"] for row in scores_for[profile.user_id]),
                "average": average_for[profile.user_id],
                "position": positions.get(profile.user_id),
            }
            for profile in profiles
        ],
        "student_count": len(profiles),
    }
