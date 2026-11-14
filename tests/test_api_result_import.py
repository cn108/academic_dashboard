import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import PublishStatus, Result, Subject

HEADER = "Admission Number,Subject,CA1,CA2,CA3,Exam\n"


def csv_file(body: str, name: str = "results.csv"):
    return SimpleUploadedFile(name, (HEADER + body).encode(), content_type="text/csv")


def import_url(school_class, session, term):
    return f"/api/classes/{school_class.pk}/results/bulk-import/?session={session.pk}&term={term.pk}"


@pytest.fixture
def english(school_class, teacher):
    return Subject.objects.create(name="English Language", school_class=school_class, teacher=teacher)


def test_template_has_the_expected_headers(teacher_client, school_class, session, term):
    response = teacher_client.get(
        f"/api/classes/{school_class.pk}/results/template/?session={session.pk}&term={term.pk}"
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "attachment" in response["Content-Disposition"]
    assert response.content.decode().strip() == "Admission Number,Subject,CA1,CA2,CA3,Exam"


def test_import_creates_draft_results(
    teacher_client, teacher, school_class, subject, english, student, classmate, session, term
):
    upload = csv_file("JSS2A-001,Mathematics,8,9,11,30\nJSS2A-002,English Language,7,8,10,45\n")

    response = teacher_client.post(
        import_url(school_class, session, term), {"file": upload}, format="multipart"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 2
    assert body["updated"] == 0
    assert body["errors"] == []
    assert body["total_rows"] == 2

    maths = Result.objects.get(student=student, subject=subject, session=session, term=term)
    assert (maths.ca1, maths.ca2, maths.ca3, maths.exam) == (8, 9, 11, 30)
    assert maths.total == 58
    assert maths.grade == "C"
    assert maths.status == PublishStatus.DRAFT
    assert maths.created_by == teacher

    english_result = Result.objects.get(student=classmate, subject=english)
    assert english_result.total == 70
    assert english_result.status == PublishStatus.DRAFT


def test_boundary_violations_are_reported_per_row(
    teacher_client, school_class, subject, student, classmate, session, term
):
    upload = csv_file(
        "JSS2A-001,Mathematics,8,9,11,85\nJSS2A-002,Mathematics,11,9,11,30\nJSS2A-001,Mathematics,8,9,11,30\n"
    )

    body = teacher_client.post(
        import_url(school_class, session, term), {"file": upload}, format="multipart"
    ).json()

    assert body["created"] == 1
    assert body["updated"] == 0
    assert [error["row"] for error in body["errors"]] == [2, 3]
    assert body["errors"][0]["reason"] == "Exam score 85 exceeds maximum of 60."
    assert body["errors"][1]["reason"] == "CA1 score 11 exceeds maximum of 10."
    assert Result.objects.filter(subject=subject, student=student).count() == 1


def test_unknown_admission_numbers_are_rejected(teacher_client, school_class, subject, session, term):
    upload = csv_file("JSS2A-999,Mathematics,8,9,11,30\n")

    body = teacher_client.post(
        import_url(school_class, session, term), {"file": upload}, format="multipart"
    ).json()

    assert body["created"] == 0
    assert body["errors"] == [{"row": 2, "reason": "Admission number JSS2A-999 is not in this class."}]


def test_subjects_from_another_class_are_rejected(
    teacher_client, school_class, other_class, other_teacher, student, session, term
):
    foreign = Subject.objects.create(name="Music", school_class=other_class, teacher=other_teacher)
    upload = csv_file("JSS2A-001,Music,8,9,11,30\n")

    body = teacher_client.post(
        import_url(school_class, session, term), {"file": upload}, format="multipart"
    ).json()

    assert body["created"] == 0
    assert body["errors"][0]["reason"] == "Music is not taught in this class."
    assert Result.objects.filter(subject=foreign).count() == 0


def test_non_numeric_scores_are_rejected(teacher_client, school_class, subject, student, session, term):
    upload = csv_file("JSS2A-001,Mathematics,eight,9,11,30\n")

    body = teacher_client.post(
        import_url(school_class, session, term), {"file": upload}, format="multipart"
    ).json()

    assert body["errors"] == [{"row": 2, "reason": "CA1 must be a whole number."}]


def test_import_updates_existing_results_without_unpublishing(
    teacher_client, school_class, subject, student, session, term
):
    existing = Result.objects.create(
        student=student,
        subject=subject,
        session=session,
        term=term,
        ca1=5,
        ca2=5,
        ca3=5,
        exam=5,
        status=PublishStatus.PUBLISHED,
    )

    upload = csv_file("JSS2A-001,Mathematics,8,9,11,30\n")
    body = teacher_client.post(
        import_url(school_class, session, term), {"file": upload}, format="multipart"
    ).json()

    assert body["created"] == 0
    assert body["updated"] == 1
    existing.refresh_from_db()
    assert existing.total == 58
    assert existing.status == PublishStatus.PUBLISHED


def test_import_requires_a_result_column(teacher_client, school_class, session, term):
    upload = SimpleUploadedFile("bad.csv", b"Name,Score\nEmeka,10\n", content_type="text/csv")

    response = teacher_client.post(
        import_url(school_class, session, term), {"file": upload}, format="multipart"
    )
    assert response.status_code == 400
    assert "Admission Number" in str(response.json()["file"])


def test_another_teacher_cannot_import(other_teacher_client, school_class, session, term):
    upload = csv_file("JSS2A-001,Mathematics,8,9,11,30\n")
    response = other_teacher_client.post(
        import_url(school_class, session, term), {"file": upload}, format="multipart"
    )
    assert response.status_code == 404


def test_mismatched_session_is_rejected(teacher_client, school_class, term, db):
    from core.models import AcademicSession

    other_session = AcademicSession.objects.create(name="2030/2031")
    upload = csv_file("JSS2A-001,Mathematics,8,9,11,30\n")
    response = teacher_client.post(
        import_url(school_class, other_session, term), {"file": upload}, format="multipart"
    )
    assert response.status_code == 400
    assert "session" in response.json()
