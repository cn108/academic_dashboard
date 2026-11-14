from django.contrib.auth.models import User

from core.models import PublishStatus, Result


def make_result(student, subject, session, term, exam, status=PublishStatus.PUBLISHED, **extra):
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
        **extra,
    )


def card_url(student, session, term):
    return f"/api/students/{student.pk}/report-card/?session={session.pk}&term={term.pk}"


def test_student_can_print_their_own_report_card(student_client, student, classmate, subject, session, term):
    make_result(student, subject, session, term, exam=30)
    make_result(classmate, subject, session, term, exam=54)

    response = student_client.get(card_url(student, session, term))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    html = response.content.decode()

    for phrase in (
        "Cognitive Domain",
        "Affective Domain",
        "Psychomotor Domain",
        "Class Teacher's Remark",
        "Principal's Remark",
        "Next Term Fees",
        "Resumption Date",
        "Position in Class",
        "Model Secondary School",
        "JSS 2A",
        "First Term",
        "2025/2026",
        "JSS2A-001",
    ):
        assert phrase in html, phrase

    # Chidera's 58 is behind Emeka's 82, so she is 2nd of the two students.
    assert "2nd out of 2 students" in html
    assert "58" in html
    assert "@media print" in html


def test_class_averages_and_teacher_remarks_are_rendered(
    student_client, student, classmate, subject, session, term
):
    make_result(student, subject, session, term, exam=30, teacher_remark="Needs to show working.")
    make_result(classmate, subject, session, term, exam=54)

    html = student_client.get(card_url(student, session, term)).content.decode()

    assert "Needs to show working." in html
    # Class average for the subject is (58 + 82) / 2.
    assert "<td>70</td>" in html


def test_class_teacher_can_print_any_student_in_the_class(teacher_client, student, subject, session, term):
    make_result(student, subject, session, term, exam=30)
    response = teacher_client.get(card_url(student, session, term))
    assert response.status_code == 200


def test_staff_can_print_any_report_card(student, subject, session, term, db):
    staff = User.objects.create_superuser("principal", password="Board@2026")
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(staff)
    make_result(student, subject, session, term, exam=30)

    response = client.get(card_url(student, session, term))
    assert response.status_code == 200


def test_another_student_cannot_print_someone_elses_card(student, classmate, subject, session, term):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(classmate)

    make_result(student, subject, session, term, exam=30)
    response = client.get(card_url(student, session, term))
    assert response.status_code == 403


def test_a_teacher_from_another_class_is_refused(other_teacher_client, student, subject, session, term):
    response = other_teacher_client.get(card_url(student, session, term))
    assert response.status_code == 403


def test_anonymous_requests_are_rejected(student, session, term, db):
    from rest_framework.test import APIClient

    response = APIClient().get(card_url(student, session, term))
    assert response.status_code == 401


def test_student_without_a_class_gets_a_clear_error(student_client, student, session, term):
    from core.models import Profile

    Profile.objects.filter(user=student).update(school_class=None)
    response = student_client.get(card_url(student, session, term))
    assert response.status_code == 400
    assert "student" in response.json()


def test_draft_results_do_not_appear_on_the_card(student_client, student, subject, session, term):
    draft = make_result(student, subject, session, term, exam=55, status=PublishStatus.DRAFT)
    assert draft.status == PublishStatus.DRAFT

    html = student_client.get(card_url(student, session, term)).content.decode()
    assert "Not ranked yet" in html
    assert "No published results for this term yet." in html
    assert "83" not in html
