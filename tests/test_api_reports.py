import pytest

from core.models import Profile, PublishStatus, Result, Subject
from tests.conftest import make_user


def add_student(school_class, admission_number, first_name, last_name="Test"):
    user = make_user(admission_number, Profile.STUDENT, first_name=first_name, last_name=last_name)
    profile = user.profile
    profile.admission_number = admission_number
    profile.school_class = school_class
    profile.save()
    return user


def add_result(student, subject, session, term, exam, status=PublishStatus.PUBLISHED):
    return Result.objects.create(
        student=student,
        subject=subject,
        session=session,
        term=term,
        ca1=8,
        ca2=9,
        ca3=11,
        exam=exam,
        status=status,
    )


@pytest.fixture
def english(school_class, teacher):
    return Subject.objects.create(name="English Language", school_class=school_class, teacher=teacher)


@pytest.fixture
def science(school_class, teacher):
    return Subject.objects.create(name="Basic Science", school_class=school_class, teacher=teacher)


@pytest.fixture
def broadsheet_client(teacher, teacher_client):
    return teacher_client


def url(school_class, session, term):
    return f"/api/classes/{school_class.pk}/broadsheet/?session={session.pk}&term={term.pk}"


def test_broadsheet_matrix_averages_and_positions(
    broadsheet_client, school_class, subject, english, science, student, classmate, session, term
):
    # Chidera: Maths 58, English 70 -> average 64.
    add_result(student, subject, session, term, exam=30)
    add_result(student, english, session, term, exam=42)
    # Emeka: Maths 82, English 50 -> average 66, plus a draft that must be ignored.
    add_result(classmate, subject, session, term, exam=54)
    add_result(classmate, english, session, term, exam=22)
    draft = add_result(classmate, science, session, term, exam=60, status=PublishStatus.DRAFT)

    response = broadsheet_client.get(url(school_class, session, term))
    assert response.status_code == 200
    body = response.json()

    assert body["class"] == {"id": school_class.pk, "name": "JSS 2A", "level": "JSS 2"}
    assert body["term"]["name"] == "First Term"
    assert body["session"]["name"] == session.name
    assert [row["name"] for row in body["subjects"]] == [
        "Basic Science",
        "English Language",
        "Mathematics",
    ]

    by_name = {row["name"]: row for row in body["subjects"]}
    assert by_name["Mathematics"]["class_average"] == 70.0
    assert by_name["English Language"]["class_average"] == 60.0
    # The only Basic Science result is a draft, so it contributes nothing.
    assert by_name["Basic Science"]["class_average"] is None
    assert by_name["Basic Science"]["results_count"] == 0
    assert draft.status == PublishStatus.DRAFT

    students = {row["admission_number"]: row for row in body["students"]}
    assert students["JSS2A-002"]["average"] == 66.0
    assert students["JSS2A-002"]["position"] == 1
    assert students["JSS2A-002"]["total"] == 132
    assert students["JSS2A-002"]["subjects_count"] == 2

    assert students["JSS2A-001"]["average"] == 64.0
    assert students["JSS2A-001"]["position"] == 2
    assert students["JSS2A-001"]["total"] == 128

    # Scores travel per subject with their component marks.
    maths_row = next(row for row in students["JSS2A-001"]["scores"] if row["subject"] == subject.pk)
    assert maths_row == {
        "subject": subject.pk,
        "subject_name": "Mathematics",
        "ca1": 8,
        "ca2": 9,
        "ca3": 11,
        "exam": 30,
        "total": 58,
        "grade": "C",
        "remarks": "Good",
        "teacher_remark": "",
    }


def test_missing_subjects_do_not_break_the_average(
    broadsheet_client, school_class, subject, english, student, classmate, session, term
):
    # Chidera only has Maths (88); Emeka has Maths 50 + English 50 (average 50).
    add_result(student, subject, session, term, exam=60)
    add_result(classmate, subject, session, term, exam=22)
    add_result(classmate, english, session, term, exam=22)

    body = broadsheet_client.get(url(school_class, session, term)).json()
    students = {row["admission_number"]: row for row in body["students"]}

    assert students["JSS2A-001"]["subjects_count"] == 1
    assert students["JSS2A-001"]["average"] == 88.0
    assert students["JSS2A-001"]["position"] == 1
    assert students["JSS2A-002"]["average"] == 50.0
    assert students["JSS2A-002"]["position"] == 2


def test_students_without_published_results_are_unranked(
    broadsheet_client, school_class, subject, student, classmate, session, term
):
    add_result(student, subject, session, term, exam=40)
    add_result(classmate, subject, session, term, exam=50, status=PublishStatus.DRAFT)

    body = broadsheet_client.get(url(school_class, session, term)).json()
    students = {row["admission_number"]: row for row in body["students"]}

    assert students["JSS2A-001"]["position"] == 1
    assert students["JSS2A-001"]["average"] == 68.0
    assert students["JSS2A-002"]["average"] is None
    assert students["JSS2A-002"]["position"] is None
    assert students["JSS2A-002"]["subjects_count"] == 0


def test_ties_share_a_position_and_skip_the_next(
    broadsheet_client, school_class, subject, student, classmate, session, term
):
    third = add_student(school_class, "JSS2A-003", "Fatima", "Bello")
    fourth = add_student(school_class, "JSS2A-004", "Ibrahim", "Musa")

    add_result(student, subject, session, term, exam=52)  # 80
    add_result(classmate, subject, session, term, exam=42)  # 70
    add_result(third, subject, session, term, exam=42)  # 70
    add_result(fourth, subject, session, term, exam=32)  # 60

    body = broadsheet_client.get(url(school_class, session, term)).json()
    positions = {row["admission_number"]: row["position"] for row in body["students"]}

    assert positions["JSS2A-001"] == 1
    assert positions["JSS2A-002"] == 2
    assert positions["JSS2A-003"] == 2
    assert positions["JSS2A-004"] == 4


def test_broadsheet_defaults_to_the_current_term(
    broadsheet_client, school_class, subject, student, session, term
):
    add_result(student, subject, session, term, exam=30)

    body = broadsheet_client.get(f"/api/classes/{school_class.pk}/broadsheet/").json()
    assert body["term"]["id"] == term.pk
    assert body["students"][0]["total"] == 58


def test_broadsheet_rejects_a_session_that_does_not_match_the_term(
    broadsheet_client, school_class, session, term, db
):
    from core.models import AcademicSession

    other_session = AcademicSession.objects.create(name="2030/2031")
    response = broadsheet_client.get(
        f"/api/classes/{school_class.pk}/broadsheet/?session={other_session.pk}&term={term.pk}"
    )
    assert response.status_code == 400
    assert "session" in response.json()


def test_another_teacher_cannot_open_the_broadsheet(other_teacher_client, school_class, session, term):
    response = other_teacher_client.get(url(school_class, session, term))
    assert response.status_code == 404


def test_students_cannot_open_the_class_broadsheet(student_client, school_class, session, term, student):
    response = student_client.get(url(school_class, session, term))
    assert response.status_code == 403
