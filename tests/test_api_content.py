import pytest
from django.urls import reverse

from core.models import (
    Announcement,
    Assignment,
    LessonNote,
    PublishStatus,
    Result,
)


def make_result(student, subject, session, term, **overrides):
    defaults = {
        "ca1": 8,
        "ca2": 9,
        "ca3": 11,
        "exam": 50,
        "status": PublishStatus.DRAFT,
    }
    defaults.update(overrides)
    return Result.objects.create(student=student, subject=subject, session=session, term=term, **defaults)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_student_cannot_create_a_result(student_client, subject, student, session, term):
    response = student_client.post(
        reverse("result-list"),
        {
            "student": student.pk,
            "subject": subject.pk,
            "session": session.pk,
            "term": term.pk,
            "ca1": 10,
        },
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_draft_result_is_hidden_from_students(student_client, student, subject, session, term):
    make_result(student, subject, session, term)

    payload = student_client.get(reverse("result-list")).json()

    assert payload["count"] == 0


@pytest.mark.django_db
def test_publishing_a_result_makes_it_visible(student_client, student, subject, session, term):
    result = make_result(student, subject, session, term)

    result.publish()
    result.save()

    payload = student_client.get(reverse("result-list")).json()

    assert payload["count"] == 1
    row = payload["results"][0]
    assert row["subject_name"] == "Mathematics"
    assert row["total"] == 78
    assert row["grade"] == "A"
    assert row["remarks"] == "Excellent"


@pytest.mark.django_db
def test_publish_endpoint_publishes_a_result(teacher_client, student, subject, session, term):
    result = make_result(student, subject, session, term)

    response = teacher_client.post(reverse("result-publish", args=[result.pk]))

    assert response.status_code == 200
    assert response.json()["status"] == PublishStatus.PUBLISHED
    result.refresh_from_db()
    assert result.published_at is not None


@pytest.mark.django_db
def test_student_sees_only_their_own_result(student_client, student, classmate, subject, session, term):
    for user in (student, classmate):
        result = make_result(user, subject, session, term, exam=40)
        result.publish()
        result.save()

    payload = student_client.get(reverse("result-list")).json()

    assert payload["count"] == 1
    assert payload["results"][0]["student"] == student.pk


@pytest.mark.django_db
def test_a_published_result_for_another_class_stays_hidden(outsider, subject, session, term):
    result = make_result(outsider, subject, session, term)
    result.publish()
    result.save()

    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(outsider)

    payload = client.get(reverse("result-list")).json()

    assert payload["count"] == 0


@pytest.mark.django_db
def test_teacher_list_includes_drafts(teacher_client, student, subject, session, term):
    make_result(student, subject, session, term)

    payload = teacher_client.get(reverse("result-list")).json()

    assert payload["count"] == 1
    assert payload["results"][0]["status"] == PublishStatus.DRAFT


@pytest.mark.django_db
def test_other_teacher_cannot_see_or_publish_a_result(other_teacher_client, student, subject, session, term):
    result = make_result(student, subject, session, term)

    listing = other_teacher_client.get(reverse("result-list")).json()
    action = other_teacher_client.post(reverse("result-publish", args=[result.pk]))

    assert listing["count"] == 0
    assert action.status_code == 404


@pytest.mark.django_db
def test_result_scores_are_validated_by_the_api(teacher_client, student, subject, session, term):
    response = teacher_client.post(
        reverse("result-list"),
        {
            "student": student.pk,
            "subject": subject.pk,
            "session": session.pk,
            "term": term.pk,
            "ca3": 40,
            "exam": 10,
        },
        content_type="application/json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_result_for_a_student_in_another_class_is_rejected(teacher_client, outsider, subject, session, term):
    response = teacher_client.post(
        reverse("result-list"),
        {
            "student": outsider.pk,
            "subject": subject.pk,
            "session": session.pk,
            "term": term.pk,
            "exam": 30,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "student" in response.json()


@pytest.mark.django_db
def test_results_can_be_filtered_by_session_and_term(teacher_client, student, subject, session, term):
    from core.models import AcademicSession, Term

    make_result(student, subject, session, term)
    old_session = AcademicSession.objects.create(name="2024/2025")
    old_term = Term.objects.create(session=old_session, name=Term.FIRST)
    make_result(student, subject, old_session, old_term)

    payload = teacher_client.get(reverse("result-list"), {"session": session.pk, "term": term.pk}).json()

    assert payload["count"] == 1
    assert payload["results"][0]["session"] == session.pk


# ---------------------------------------------------------------------------
# Lesson notes
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_lesson_notes_follow_the_publish_rule(teacher_client, student_client, subject, teacher, term):
    draft = LessonNote.objects.create(
        subject=subject, term=term, week_number=1, topic="Fractions", created_by=teacher
    )
    published = LessonNote.objects.create(
        subject=subject,
        term=term,
        week_number=2,
        topic="Decimals",
        created_by=teacher,
        status=PublishStatus.PUBLISHED,
    )

    student_payload = student_client.get(reverse("lesson-note-list")).json()
    teacher_payload = teacher_client.get(reverse("lesson-note-list")).json()

    assert [row["id"] for row in student_payload["results"]] == [published.pk]
    assert {row["id"] for row in teacher_payload["results"]} == {draft.pk, published.pk}


@pytest.mark.django_db
def test_student_cannot_write_lesson_notes(student_client, subject, term):
    response = student_client.post(
        reverse("lesson-note-list"),
        {"subject": subject.pk, "term": term.pk, "week_number": 3, "topic": "Shapes"},
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_teacher_writes_a_lesson_note(teacher_client, subject, term, teacher):
    response = teacher_client.post(
        reverse("lesson-note-list"),
        {
            "subject": subject.pk,
            "term": term.pk,
            "week_number": 3,
            "topic": "Shapes",
            "content": "Identify 2D shapes.",
            "status": "draft",
        },
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    note = LessonNote.objects.get(pk=response.json()["id"])
    assert note.created_by == teacher
    assert note.status == PublishStatus.DRAFT


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_announcements_are_filtered_by_audience_and_status(
    student_client, teacher, school_class, other_class
):
    Announcement.objects.create(
        title="Resumption",
        body="School resumes Monday.",
        created_by=teacher,
        status=PublishStatus.PUBLISHED,
    )
    mine = Announcement.objects.create(
        title="Class trip",
        body="Bring lunch.",
        school_class=school_class,
        created_by=teacher,
        status=PublishStatus.PUBLISHED,
    )
    Announcement.objects.create(
        title="Draft notice",
        body="Not yet.",
        school_class=school_class,
        created_by=teacher,
    )
    Announcement.objects.create(
        title="Other class",
        body="Not yours.",
        school_class=other_class,
        created_by=teacher,
        status=PublishStatus.PUBLISHED,
    )

    payload = student_client.get(reverse("announcement-list")).json()

    titles = {row["title"] for row in payload["results"]}
    assert "Resumption" in titles
    assert mine.title in titles
    assert "Draft notice" not in titles
    assert "Other class" not in titles


@pytest.mark.django_db
def test_teacher_cannot_announce_to_another_class(teacher_client, other_class):
    response = teacher_client.post(
        reverse("announcement-list"),
        {"title": "Hijack", "body": "Not mine", "school_class": other_class.pk},
        content_type="application/json",
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_draft_assignments_are_hidden_from_students(student_client, teacher, school_class, subject):
    Assignment.objects.create(
        title="Draft homework",
        due_date="2030-01-10",
        school_class=school_class,
        subject=subject,
        created_by=teacher,
    )
    published = Assignment.objects.create(
        title="Published homework",
        due_date="2030-01-11",
        school_class=school_class,
        subject=subject,
        created_by=teacher,
        status=PublishStatus.PUBLISHED,
    )

    payload = student_client.get(reverse("assignment-list")).json()

    assert [row["id"] for row in payload["results"]] == [published.pk]


@pytest.mark.django_db
def test_teacher_creates_published_work_for_their_class(teacher_client, school_class, subject, teacher, term):
    response = teacher_client.post(
        reverse("assignment-list"),
        {
            "title": "Fractions worksheet",
            "due_date": "2030-02-01",
            "school_class": school_class.pk,
            "subject": subject.pk,
            "term": term.pk,
            "status": "published",
        },
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assignment = Assignment.objects.get(pk=response.json()["id"])
    assert assignment.created_by == teacher
    assert assignment.published_at is not None


@pytest.mark.django_db
def test_teacher_cannot_set_work_for_another_class(teacher_client, other_class, other_teacher):
    response = teacher_client.post(
        reverse("assignment-list"),
        {"title": "Not mine", "due_date": "2030-02-01", "school_class": other_class.pk},
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_session_lookup_and_current_term(student_client, session, term):
    sessions = student_client.get(reverse("session-list")).json()
    current = student_client.get(reverse("term-current")).json()

    assert sessions["count"] == 1
    assert current["term"]["name"] == term.name
    assert current["session"]["name"] == session.name
