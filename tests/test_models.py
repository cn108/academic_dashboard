from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from core.models import (
    Assignment,
    Profile,
    PublishStatus,
    Result,
    Subject,
    role_of,
)


def make_result(student, subject, session, term, **scores):
    defaults = {"ca1": 8, "ca2": 9, "ca3": 11, "exam": 50}
    defaults.update(scores)
    return Result.objects.create(student=student, subject=subject, session=session, term=term, **defaults)


@pytest.mark.parametrize(
    "total,letter,remark",
    [
        (100, "A", "Excellent"),
        (70, "A", "Excellent"),
        (69, "B", "Very good"),
        (60, "B", "Very good"),
        (59, "C", "Good"),
        (50, "C", "Good"),
        (49, "D", "Fair"),
        (45, "D", "Fair"),
        (44, "E", "Pass"),
        (40, "E", "Pass"),
        (39, "F", "Fail"),
        (0, "F", "Fail"),
    ],
)
def test_nigerian_grade_scale(total, letter, remark):
    assert Result.grade_for(total) == (letter, remark)


@pytest.mark.django_db
def test_result_saves_total_grade_and_remarks(student, subject, session, term):
    result = make_result(student, subject, session, term)

    assert result.total == 78
    assert result.grade == "A"
    assert result.remarks == "Excellent"
    assert result.ca_total == 28


@pytest.mark.django_db
def test_result_recomputes_when_scores_change(student, subject, session, term):
    result = make_result(student, subject, session, term)

    result.exam = 10
    result.save()
    result.refresh_from_db()

    assert result.total == 38
    assert result.grade == "F"
    assert result.remarks == "Fail"


@pytest.mark.django_db
@pytest.mark.parametrize("field,value", [("ca3", 25), ("ca1", 15), ("exam", 70)])
def test_result_rejects_scores_above_the_maximum(field, value, student, subject, session, term):
    result = make_result(student, subject, session, term)
    setattr(result, field, value)

    with pytest.raises(ValidationError):
        result.clean()


@pytest.mark.django_db
def test_one_result_per_subject_per_term(student, subject, session, term):
    make_result(student, subject, session, term)

    with pytest.raises(IntegrityError):
        make_result(student, subject, session, term, exam=10)


@pytest.mark.django_db
def test_publish_sets_status_and_timestamp(student, subject, session, term):
    result = make_result(student, subject, session, term)

    assert result.status == PublishStatus.DRAFT
    assert result.published_at is None

    result.publish()
    result.save()
    result.refresh_from_db()

    assert result.status == PublishStatus.PUBLISHED
    assert result.published_at is not None


@pytest.mark.django_db
def test_saving_a_published_row_stamps_published_at(student, subject, session, term):
    result = make_result(student, subject, session, term)
    result.status = PublishStatus.PUBLISHED
    result.save()

    assert result.published_at is not None


@pytest.mark.django_db
def test_result_rejects_a_term_from_another_session(student, subject, session, term):
    from core.models import AcademicSession, Term

    other_session = AcademicSession.objects.create(name="2024/2025")
    other_term = Term.objects.create(session=other_session, name=Term.FIRST)
    result = make_result(student, subject, session, other_term)

    with pytest.raises(ValidationError):
        result.clean()


@pytest.mark.django_db
def test_class_capacity_and_management(school_class, teacher, student, other_teacher, settings):
    assert school_class.student_count == 1
    assert school_class.capacity == 50
    assert school_class.is_full is False
    assert school_class.can_manage(teacher) is True
    assert school_class.can_manage(other_teacher) is False

    staff = User.objects.create_user(username="head", password="Sup3rSecret!42", is_staff=True)
    assert school_class.can_manage(staff) is True


@pytest.mark.django_db
def test_class_is_full_at_capacity(school_class):
    school_class.capacity = 10
    school_class.save()
    for index in range(10):
        user = User.objects.create_user(username=f"pupil{index}", password="Sup3rSecret!42")
        Profile.objects.create(user=user, role=Profile.STUDENT, school_class=school_class)

    assert school_class.student_count == 10
    assert school_class.is_full is True


@pytest.mark.django_db
def test_staff_are_treated_as_teachers():
    staff = User.objects.create_user(username="head", password="Sup3rSecret!42", is_staff=True)

    assert role_of(staff) == Profile.TEACHER


@pytest.mark.django_db
def test_subject_names_are_unique_within_a_class(school_class, teacher, other_class):
    Subject.objects.create(name="Mathematics", school_class=school_class, teacher=teacher)
    Subject.objects.create(name="Mathematics", school_class=other_class, teacher=teacher)

    with pytest.raises(IntegrityError):
        Subject.objects.create(name="Mathematics", school_class=school_class, teacher=teacher)


@pytest.mark.django_db
def test_assignment_is_overdue_when_past_due(school_class, teacher):
    from datetime import timedelta

    from django.utils import timezone

    overdue = Assignment.objects.create(
        title="Late work",
        due_date=timezone.localdate() - timedelta(days=1),
        school_class=school_class,
        created_by=teacher,
        status=PublishStatus.PUBLISHED,
    )
    future = Assignment.objects.create(
        title="Upcoming",
        due_date=timezone.localdate() + timedelta(days=1),
        school_class=school_class,
        created_by=teacher,
    )

    assert overdue.is_overdue is True
    assert future.is_overdue is False
    assert future.marks_total == Decimal("100.0")
