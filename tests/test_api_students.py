from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import (
    Assignment,
    Attendance,
    Profile,
    PublishStatus,
    Submission,
)


def csv_upload(text: str) -> SimpleUploadedFile:
    return SimpleUploadedFile("students.csv", text.encode(), content_type="text/csv")


@pytest.fixture
def published_assignment(teacher, school_class, subject):
    assignment = Assignment.objects.create(
        title="Fractions homework",
        due_date="2030-01-10",
        school_class=school_class,
        subject=subject,
        marks_total=Decimal("20.0"),
        created_by=teacher,
        status=PublishStatus.PUBLISHED,
    )
    return assignment


# ---------------------------------------------------------------------------
# Student onboarding
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_teacher_imports_students_from_csv(teacher_client, school_class, settings):
    settings.DEFAULT_STUDENT_PASSWORD = "ClassPass!2026"

    response = teacher_client.post(
        reverse("class-import-students", args=[school_class.pk]),
        {
            "file": csv_upload(
                "Full Name,Admission Number,Gender\nChinonso Eze,JSS2A-030,Male\nZainab Bello,JSS2A-031,F\n"
            )
        },
        format="multipart",
    )

    assert response.status_code == 201, response.content
    assert response.json()["created_count"] == 2
    assert response.json()["class"]["student_count"] == 2

    pupil = User.objects.get(username="JSS2A-030")
    assert pupil.first_name == "Chinonso"
    assert pupil.last_name == "Eze"
    assert pupil.check_password("ClassPass!2026")

    profile = pupil.profile
    assert profile.role == Profile.STUDENT
    assert profile.admission_number == "JSS2A-030"
    assert profile.gender == Profile.MALE
    assert profile.school_class == school_class
    assert profile.must_change_password is True


@pytest.mark.django_db
def test_teacher_imports_students_from_json(teacher_client, school_class):
    response = teacher_client.post(
        reverse("class-import-students", args=[school_class.pk]),
        {
            "students": [
                {"full_name": "Sarah Adamu", "admission_number": "JSS2A-040", "gender": "F"},
            ]
        },
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["created"] == ["JSS2A-040"]


@pytest.mark.django_db
def test_import_skips_duplicate_admission_numbers(teacher_client, school_class, student):
    response = teacher_client.post(
        reverse("class-import-students", args=[school_class.pk]),
        {
            "students": [
                {"full_name": "Copy Cat", "admission_number": "JSS2A-001"},
                {"full_name": "New Pupil", "admission_number": "JSS2A-050"},
            ]
        },
        content_type="application/json",
    )

    payload = response.json()
    assert payload["created"] == ["JSS2A-050"]
    assert payload["skipped"][0]["admission_number"] == "JSS2A-001"


@pytest.mark.django_db
def test_import_skips_rows_without_a_name(teacher_client, school_class):
    response = teacher_client.post(
        reverse("class-import-students", args=[school_class.pk]),
        {"students": [{"full_name": "", "admission_number": "JSS2A-060"}]},
        content_type="application/json",
    )

    payload = response.json()
    assert payload["created_count"] == 0
    assert payload["skipped_count"] == 1


@pytest.mark.django_db
def test_class_capacity_is_enforced_on_import(teacher_client, school_class):
    school_class.capacity = 10
    school_class.save()
    for index in range(10):
        user = User.objects.create_user(username=f"old{index}", password="Sup3rSecret!42")
        Profile.objects.create(user=user, role=Profile.STUDENT, school_class=school_class)

    response = teacher_client.post(
        reverse("class-import-students", args=[school_class.pk]),
        {
            "students": [
                {"full_name": "One Too Many", "admission_number": "JSS2A-099"},
            ]
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "can hold 10" in response.json()["detail"]


@pytest.mark.django_db
def test_other_teacher_cannot_import_into_the_class(other_teacher_client, school_class):
    response = other_teacher_client.post(
        reverse("class-import-students", args=[school_class.pk]),
        {"students": [{"full_name": "Sneaky", "admission_number": "JSS2A-070"}]},
        content_type="application/json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_students_cannot_import_classmates(student_client, school_class):
    response = student_client.post(
        reverse("class-import-students", args=[school_class.pk]),
        {"students": [{"full_name": "Sneaky", "admission_number": "JSS2A-071"}]},
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_imported_student_can_log_in_with_the_default_password(
    teacher_client, school_class, client, settings
):
    settings.AXES_ENABLED = False
    teacher_client.post(
        reverse("class-import-students", args=[school_class.pk]),
        {"students": [{"full_name": "Login Test", "admission_number": "JSS2A-080", "gender": "F"}]},
        content_type="application/json",
    )

    response = client.post(
        reverse("token_obtain_pair"),
        {"username": "JSS2A-080", "password": settings.DEFAULT_STUDENT_PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content


# ---------------------------------------------------------------------------
# Class roster access
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_teacher_sees_only_their_own_classes(teacher_client, other_teacher_client, school_class, other_class):
    mine = teacher_client.get(reverse("class-list")).json()
    theirs = other_teacher_client.get(reverse("class-list")).json()

    assert [row["id"] for row in mine["results"]] == [school_class.pk]
    assert [row["id"] for row in theirs["results"]] == [other_class.pk]


@pytest.mark.django_db
def test_student_sees_only_their_class(student_client, school_class):
    payload = student_client.get(reverse("class-list")).json()

    assert payload["count"] == 1
    assert payload["results"][0]["id"] == school_class.pk


@pytest.mark.django_db
def test_only_staff_can_create_classes(teacher_client, client):
    payload = {"name": "JSS 1A", "level": "JSS 1"}

    response = teacher_client.post(reverse("class-list"), payload, content_type="application/json")

    assert response.status_code == 403

    admin = User.objects.create_user(username="head", password="Sup3rSecret!42", is_staff=True)
    admin_client = APIClient()
    admin_client.force_authenticate(admin)
    created = admin_client.post(reverse("class-list"), payload, content_type="application/json")

    assert created.status_code == 201, created.content


@pytest.mark.django_db
def test_class_payload_lists_students_with_admission_numbers(teacher_client, school_class, student):
    payload = teacher_client.get(reverse("class-list")).json()
    row = payload["results"][0]

    assert row["student_count"] == 1
    assert row["students_detail"][0]["admission_number"] == "JSS2A-001"
    assert row["students_detail"][0]["full_name"] == "Chidera Okafor"


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_teacher_saves_a_whole_register(teacher_client, school_class, student, teacher):
    response = teacher_client.post(
        reverse("attendance-bulk"),
        {
            "class": school_class.pk,
            "date": "2026-03-02",
            "records": [{"student": student.pk, "status": "late"}],
        },
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    entry = Attendance.objects.get(student=student, date="2026-03-02")
    assert entry.status == Attendance.LATE
    assert entry.school_class == school_class
    assert entry.marked_by == teacher


@pytest.mark.django_db
def test_register_upserts_instead_of_duplicating(teacher_client, school_class, student):
    payload = {
        "class": school_class.pk,
        "date": "2026-03-02",
        "records": [{"student": student.pk, "status": "absent"}],
    }
    teacher_client.post(reverse("attendance-bulk"), payload, content_type="application/json")
    payload["records"][0]["status"] = "present"
    teacher_client.post(reverse("attendance-bulk"), payload, content_type="application/json")

    assert Attendance.objects.filter(student=student).count() == 1
    assert Attendance.objects.get(student=student).status == Attendance.PRESENT


@pytest.mark.django_db
def test_attendance_summary_counts_by_class(teacher_client, school_class, student):
    teacher_client.post(
        reverse("attendance-bulk"),
        {
            "class": school_class.pk,
            "date": "2026-03-02",
            "records": [{"student": student.pk, "status": "present"}],
        },
        content_type="application/json",
    )

    payload = teacher_client.get(reverse("attendance-summary")).json()

    assert payload[0]["class_name"] == "JSS 2A"
    assert payload[0]["present"] == 1


@pytest.mark.django_db
def test_other_teacher_cannot_mark_the_register(other_teacher_client, school_class, student):
    response = other_teacher_client.post(
        reverse("attendance-bulk"),
        {
            "class": school_class.pk,
            "date": "2026-03-02",
            "records": [{"student": student.pk, "status": "present"}],
        },
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_student_sees_only_their_own_attendance(student_client, student, classmate, school_class):
    for user in (student, classmate):
        Attendance.objects.create(
            school_class=school_class, student=user, date="2026-03-02", status="present"
        )

    payload = student_client.get(reverse("attendance-list")).json()

    assert payload["count"] == 1
    assert payload["results"][0]["student"] == student.pk


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_student_uploads_work_for_a_published_assignment(
    student_client, student, published_assignment, media_root
):
    upload = SimpleUploadedFile("homework.pdf", b"%PDF-1.4 work", content_type="application/pdf")

    response = student_client.post(
        reverse("submission-list"),
        {"assignment": published_assignment.pk, "file": upload, "note": "Done"},
        format="multipart",
    )

    assert response.status_code == 201, response.content
    submission = Submission.objects.get(student=student, assignment=published_assignment)
    assert submission.note == "Done"
    assert submission.is_graded is False


@pytest.mark.django_db
def test_student_cannot_submit_to_a_draft_assignment(
    student_client, teacher, school_class, subject, media_root
):
    draft = Assignment.objects.create(
        title="Not yet",
        due_date="2030-01-10",
        school_class=school_class,
        subject=subject,
        created_by=teacher,
    )

    response = student_client.post(
        reverse("submission-list"),
        {"assignment": draft.pk, "file": SimpleUploadedFile("x.pdf", b"x")},
        format="multipart",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_student_cannot_submit_twice(student_client, student, published_assignment, media_root):
    Submission.objects.create(
        assignment=published_assignment,
        student=student,
        file=SimpleUploadedFile("first.pdf", b"1"),
    )

    response = student_client.post(
        reverse("submission-list"),
        {"assignment": published_assignment.pk, "file": SimpleUploadedFile("second.pdf", b"2")},
        format="multipart",
    )

    assert response.status_code == 400
    assert Submission.objects.filter(student=student).count() == 1


@pytest.mark.django_db
def test_student_in_another_class_cannot_submit(outsider, published_assignment, media_root):
    client = APIClient()
    client.force_authenticate(outsider)

    response = client.post(
        reverse("submission-list"),
        {"assignment": published_assignment.pk, "file": SimpleUploadedFile("x.pdf", b"x")},
        format="multipart",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_teacher_grades_and_cannot_exceed_the_total(
    teacher_client, student, published_assignment, teacher, media_root
):
    submission = Submission.objects.create(
        assignment=published_assignment,
        student=student,
        file=SimpleUploadedFile("work.pdf", b"work"),
    )

    too_high = teacher_client.patch(
        reverse("submission-grade", args=[submission.pk]),
        {"marks": "25"},
        content_type="application/json",
    )
    graded = teacher_client.patch(
        reverse("submission-grade", args=[submission.pk]),
        {"marks": "18.5", "feedback": "Well done"},
        content_type="application/json",
    )

    assert too_high.status_code == 400
    assert graded.status_code == 200, graded.content
    submission.refresh_from_db()
    assert submission.marks == Decimal("18.5")
    assert submission.graded_by == teacher


@pytest.mark.django_db
def test_other_teacher_cannot_grade(other_teacher_client, student, published_assignment, media_root):
    submission = Submission.objects.create(
        assignment=published_assignment,
        student=student,
        file=SimpleUploadedFile("work.pdf", b"work"),
    )

    response = other_teacher_client.patch(
        reverse("submission-grade", args=[submission.pk]),
        {"marks": "10"},
        content_type="application/json",
    )

    assert response.status_code == 404
