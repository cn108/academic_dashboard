"""Learning hub: lesson resources, completion marks, progress and trends."""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from core.models import (
    AcademicSession,
    LessonNote,
    LessonResource,
    Profile,
    PublishStatus,
    ResourceProgress,
    Result,
    Subject,
    Term,
)


def make_lesson(subject, term, teacher, week=1, topic="Fractions", published=True):
    lesson = LessonNote.objects.create(
        subject=subject,
        term=term,
        week_number=week,
        topic=topic,
        content="Worked examples and class exercises.",
        created_by=teacher,
    )
    if published:
        lesson.publish()
        lesson.save()
    return lesson


@pytest.fixture
def lesson(subject, term, teacher):
    return make_lesson(subject, term, teacher)


@pytest.fixture
def draft_lesson(subject, term, teacher):
    return make_lesson(subject, term, teacher, week=2, topic="Decimals", published=False)


@pytest.fixture
def video(lesson):
    return LessonResource.objects.create(
        lesson=lesson,
        type=LessonResource.VIDEO,
        title="Fractions video",
        url="https://example.com/fractions",
        order_index=1,
    )


@pytest.fixture
def reading(lesson):
    return LessonResource.objects.create(
        lesson=lesson,
        type=LessonResource.READING_LINK,
        title="BBC Bitesize: fractions",
        url="https://example.com/reading",
        order_index=2,
    )


@pytest.fixture
def document(lesson, media_root):
    return LessonResource.objects.create(
        lesson=lesson,
        type=LessonResource.DOCUMENT,
        title="Worksheet",
        file=SimpleUploadedFile("worksheet.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
        order_index=3,
    )


def resources_url(lesson):
    return f"/api/lessons/{lesson.pk}/resources/"


def complete_url(resource):
    return f"/api/resources/{resource.pk}/complete/"


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def make_result(student, subject, session, term, total, status=PublishStatus.PUBLISHED):
    """Create a result whose computed total equals ``total`` (0-100)."""
    ca1 = min(total, 10)
    ca2 = min(max(total - 10, 0), 10)
    ca3 = min(max(total - 20, 0), 20)
    exam = min(max(total - 40, 0), 60)
    return Result.objects.create(
        student=student,
        subject=subject,
        session=session,
        term=term,
        ca1=ca1,
        ca2=ca2,
        ca3=ca3,
        exam=exam,
        status=status,
    )


# ---------------------------------------------------------------------------
# Listing resources
# ---------------------------------------------------------------------------
def test_student_sees_published_resources_with_completion_flags(
    student_client, student, lesson, video, reading
):
    ResourceProgress.objects.create(student=student, resource=video, is_completed=True)

    response = student_client.get(resources_url(lesson))

    assert response.status_code == 200
    body = response.json()
    assert body["lesson"]["id"] == lesson.pk
    assert body["lesson"]["topic"] == "Fractions"
    assert body["lesson"]["subject_name"] == "Mathematics"
    assert [row["id"] for row in body["resources"]] == [video.pk, reading.pk]

    first, second = body["resources"]
    assert first["type"] == "video"
    assert first["type_label"] == "Video"
    assert first["url"] == "https://example.com/fractions"
    assert first["is_completed"] is True
    assert first["completed_at"] is not None
    assert second["is_completed"] is False
    assert second["completed_at"] is None


def test_document_resource_exposes_an_absolute_file_url(student_client, lesson, document):
    body = student_client.get(resources_url(lesson)).json()

    row = body["resources"][0]
    assert row["type"] == "document_attachment"
    assert row["url"] == ""
    assert row["file_url"].startswith("http://testserver/media/lesson-resources/")
    assert row["file_url"].endswith("worksheet.pdf")


def test_draft_lesson_resources_are_invisible_to_students(student_client, draft_lesson):
    resource = LessonResource.objects.create(
        lesson=draft_lesson,
        type=LessonResource.READING_LINK,
        title="Hidden draft resource",
        url="https://example.com/hidden",
    )

    assert student_client.get(resources_url(draft_lesson)).status_code == 404
    assert student_client.post(complete_url(resource)).status_code == 404


def test_resources_are_scoped_to_the_students_class(student_client, other_class, other_teacher):
    other_lesson = make_lesson(
        Subject.objects.create(name="Mathematics", school_class=other_class, teacher=other_teacher),
        term=None,
        teacher=other_teacher,
    )

    assert student_client.get(resources_url(other_lesson)).status_code == 404


def test_teacher_can_review_draft_resources(teacher_client, draft_lesson):
    resource = LessonResource.objects.create(
        lesson=draft_lesson,
        type=LessonResource.READING_LINK,
        title="Draft resource",
        url="https://example.com/draft",
    )

    response = teacher_client.get(resources_url(draft_lesson))

    assert response.status_code == 200
    assert response.json()["resources"][0]["id"] == resource.pk
    assert response.json()["resources"][0]["is_completed"] is False


def test_another_teacher_cannot_read_resources(other_teacher_client, lesson):
    assert other_teacher_client.get(resources_url(lesson)).status_code == 404


def test_staff_can_read_any_lesson_resources(db, lesson, video):
    staff = User.objects.create_superuser("principal-learning", password="Board@2026")

    response = client_for(staff).get(resources_url(lesson))

    assert response.status_code == 200
    assert response.json()["resources"][0]["id"] == video.pk


def test_parent_and_anonymous_are_refused(parent_client, lesson):
    assert parent_client.get(resources_url(lesson)).status_code == 404
    assert APIClient().get(resources_url(lesson)).status_code == 401


# ---------------------------------------------------------------------------
# Completing resources
# ---------------------------------------------------------------------------
def test_student_can_complete_a_resource_once(student_client, student, video):
    first = student_client.post(complete_url(video))

    assert first.status_code == 200
    body = first.json()
    assert body["is_completed"] is True
    assert body["already_completed"] is False
    assert body["completed_at"] is not None

    progress = ResourceProgress.objects.get(student=student, resource=video)
    assert progress.is_completed is True
    completed_at = progress.completed_at

    second = student_client.post(complete_url(video))

    assert second.status_code == 200
    assert second.json()["already_completed"] is True
    progress.refresh_from_db()
    assert progress.completed_at == completed_at
    assert ResourceProgress.objects.count() == 1


def test_completion_appears_on_the_resource_list(student_client, video):
    student_client.post(complete_url(video))

    row = student_client.get(resources_url(video.lesson)).json()["resources"][0]
    assert row["is_completed"] is True


def test_teacher_and_parent_cannot_mark_completion(teacher_client, parent_client, video):
    assert teacher_client.post(complete_url(video)).status_code == 403
    assert parent_client.post(complete_url(video)).status_code == 403
    assert ResourceProgress.objects.count() == 0


def test_student_cannot_complete_another_class_resource(student_client, other_class, other_teacher):
    other_lesson = make_lesson(
        Subject.objects.create(name="Mathematics", school_class=other_class, teacher=other_teacher),
        term=None,
        teacher=other_teacher,
    )
    resource = LessonResource.objects.create(
        lesson=other_lesson,
        type=LessonResource.READING_LINK,
        title="Not yours",
        url="https://example.com/other",
    )

    assert student_client.post(complete_url(resource)).status_code == 404


# ---------------------------------------------------------------------------
# Progress dashboard
# ---------------------------------------------------------------------------
def test_dashboard_completion_uses_current_term_published_resources(
    student_client, student, lesson, term, subject, teacher, video, reading
):
    # A draft lesson in the same term, and a published lesson from another term,
    # must not count towards this term's completion.
    draft = make_lesson(subject, term, teacher, week=4, topic="Draft topic", published=False)
    LessonResource.objects.create(
        lesson=draft, type=LessonResource.READING_LINK, title="Draft", url="https://e.com/d"
    )
    other_term, _ = Term.objects.get_or_create(session=term.session, name=Term.THIRD)
    old_lesson = make_lesson(subject, other_term, teacher, week=5, topic="Old topic")
    LessonResource.objects.create(
        lesson=old_lesson, type=LessonResource.READING_LINK, title="Old", url="https://e.com/o"
    )

    ResourceProgress.objects.create(student=student, resource=video, is_completed=True)

    response = student_client.get("/api/student/progress/dashboard/")

    assert response.status_code == 200
    body = response.json()
    assert body["term"]["name"] == term.name
    assert body["term"]["session_name"] == term.session.name
    assert body["resources"] == {"total": 2, "completed": 1, "percentage": 50}
    assert body["trend"] == []


def test_dashboard_percentage_rounds_to_a_whole_number(
    student_client, student, lesson, video, reading, document
):
    ResourceProgress.objects.create(student=student, resource=video, is_completed=True)

    body = student_client.get("/api/student/progress/dashboard/").json()

    # 1 of 3 complete.
    assert body["resources"] == {"total": 3, "completed": 1, "percentage": 33}


def test_dashboard_reports_term_over_term_averages(
    student_client, student, subject, school_class, teacher, term
):
    english = Subject.objects.create(name="English Language", school_class=school_class, teacher=teacher)
    second, _ = Term.objects.get_or_create(session=term.session, name=Term.SECOND)

    make_result(student, subject, term.session, term, 70)
    make_result(student, english, term.session, term, 50)
    make_result(student, subject, term.session, second, 80)
    make_result(student, english, term.session, second, 60)
    # Draft marks never feed the trend.
    science = Subject.objects.create(name="Basic Science", school_class=school_class, teacher=teacher)
    make_result(student, science, term.session, second, 10, status=PublishStatus.DRAFT)

    body = student_client.get("/api/student/progress/dashboard/").json()

    trend = body["trend"]
    assert [row["term"] for row in trend] == [Term.FIRST, Term.SECOND]
    assert [row["average"] for row in trend] == [60.0, 70.0]
    assert trend[0]["session"] == term.session.name
    assert trend[0]["subjects_count"] == 2
    subjects = {row["subject"]: row["average"] for row in trend[0]["subjects"]}
    assert subjects == {"English Language": 50.0, "Mathematics": 70.0}
    assert trend[1]["average"] == 70.0


def test_dashboard_trend_is_limited_to_the_current_session(student_client, student, subject, term):
    older_session = AcademicSession.objects.create(name="2024/2025", start_date="2024-09-01")
    older_term = Term.objects.create(session=older_session, name=Term.FIRST)
    make_result(student, subject, older_session, older_term, 30)
    make_result(student, subject, term.session, term, 90)

    trend = student_client.get("/api/student/progress/dashboard/").json()["trend"]

    assert len(trend) == 1
    assert trend[0]["session"] == term.session.name
    assert trend[0]["average"] == 90.0


def test_dashboard_for_a_student_without_a_class(student_client, student):
    Profile.objects.filter(user=student).update(school_class=None)

    body = student_client.get("/api/student/progress/dashboard/").json()

    assert body["resources"] == {"total": 0, "completed": 0, "percentage": 0}


def test_dashboard_is_student_only(teacher_client, parent_client):
    assert teacher_client.get("/api/student/progress/dashboard/").status_code == 403
    assert parent_client.get("/api/student/progress/dashboard/").status_code == 403
    assert APIClient().get("/api/student/progress/dashboard/").status_code == 401
