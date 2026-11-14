"""Timed quiz engine: question secrecy, grading, time enforcement and results."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Question,
    Quiz,
    QuizAttempt,
    QuizAttemptStatus,
    QuizStatus,
    Subject,
)

OPTIONS = ["Lagos", "Abuja", "Kano", "Port Harcourt"]


@pytest.fixture
def quiz(school_class, subject, teacher):
    return Quiz.objects.create(
        title="Fractions check",
        subject=subject,
        class_arm=school_class,
        time_limit_minutes=10,
        status=QuizStatus.PUBLISHED,
        created_by=teacher,
    )


@pytest.fixture
def questions(quiz):
    rows = [
        Question.objects.create(
            quiz=quiz,
            text="What is the capital of Nigeria?",
            options=OPTIONS,
            correct_option_index=1,
            points=1,
        ),
        Question.objects.create(
            quiz=quiz,
            text="What is 2 + 2?",
            options=["3", "4", "5", "6"],
            correct_option_index=1,
            points=2,
        ),
        Question.objects.create(
            quiz=quiz,
            text="What colour is a clear daytime sky?",
            options=["Blue", "Red", "Green", "Black"],
            correct_option_index=0,
            points=1,
        ),
    ]
    quiz.refresh_from_db()
    return rows


def start_url(quiz):
    return f"/api/quizzes/{quiz.pk}/start/"


def submit_url(quiz):
    return f"/api/quizzes/{quiz.pk}/submit/"


def attempts_url(quiz):
    return f"/api/quizzes/{quiz.pk}/attempts/"


def questions_url(quiz):
    return f"/api/quizzes/{quiz.pk}/questions/"


def start(client, quiz):
    return client.post(start_url(quiz))


def submit(client, quiz, answers):
    return client.post(submit_url(quiz), {"answers": answers}, format="json")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def question_ids(quiz):
    return list(quiz.questions.values_list("id", flat=True))


# ---------------------------------------------------------------------------
# Starting a quiz
# ---------------------------------------------------------------------------
def test_start_returns_questions_without_the_correct_answers(student_client, quiz, questions):
    response = start(student_client, quiz)

    assert response.status_code == 200
    body = response.json()
    assert body["quiz"]["id"] == quiz.pk
    assert body["quiz"]["time_limit_minutes"] == 10
    assert body["quiz"]["total_points"] == 4
    assert body["attempt"]["status"] == "in_progress"

    assert [row["id"] for row in body["questions"]] == [q.pk for q in questions]
    for row in body["questions"]:
        assert set(row) == {"id", "text", "options", "points"}

    assert "correct_option_index" not in response.content.decode()
    assert "correct_option_index" not in str(body)
    assert QuizAttempt.objects.filter(quiz=quiz).count() == 1


def test_start_sets_a_deadline_from_the_server_clock(student_client, quiz, questions):
    body = start(student_client, quiz).json()

    attempt = QuizAttempt.objects.get(pk=body["attempt"]["id"])
    expected = attempt.started_at + timedelta(minutes=quiz.time_limit_minutes)
    assert body["attempt"]["expires_at"].startswith(expected.isoformat()[:19])


def test_starting_again_resumes_the_same_attempt(student_client, quiz, questions):
    first = start(student_client, quiz).json()["attempt"]
    second = start(student_client, quiz).json()["attempt"]

    assert second["id"] == first["id"]
    assert second["started_at"] == first["started_at"]
    assert QuizAttempt.objects.filter(quiz=quiz).count() == 1


def test_draft_quiz_is_invisible_to_students(student_client, quiz, questions):
    Quiz.objects.filter(pk=quiz.pk).update(status=QuizStatus.DRAFT)

    assert start(student_client, quiz).status_code == 404


def test_closed_quiz_cannot_be_started(student_client, quiz, questions):
    Quiz.objects.filter(pk=quiz.pk).update(status=QuizStatus.CLOSED)

    response = start(student_client, quiz)

    assert response.status_code == 400
    assert response.json()["detail"] == "This quiz is closed."


def test_quiz_outside_its_availability_window_cannot_start(student_client, quiz, questions):
    Quiz.objects.filter(pk=quiz.pk).update(available_from=timezone.now() + timedelta(hours=1))
    assert start(student_client, quiz).status_code == 400

    Quiz.objects.filter(pk=quiz.pk).update(
        available_from=timezone.now() - timedelta(hours=2),
        available_until=timezone.now() - timedelta(hours=1),
    )
    assert start(student_client, quiz).status_code == 400


def test_start_requires_a_published_quiz_with_questions(student_client, quiz):
    quiz.refresh_from_db()
    response = start(student_client, quiz)
    assert response.status_code == 400
    assert "no questions" in response.json()["detail"]


def test_teacher_cannot_start_a_quiz(teacher_client, quiz, questions):
    assert teacher_client.post(start_url(quiz)).status_code == 403


def test_student_from_another_class_cannot_start(db, quiz, questions, outsider):
    assert client_for(outsider).post(start_url(quiz)).status_code == 404


def test_a_submitted_attempt_cannot_be_restarted(student_client, student, quiz, questions):
    QuizAttempt.objects.create(
        quiz=quiz, student=student, status=QuizAttemptStatus.AUTO_GRADED, submitted_at=timezone.now()
    )

    response = start(student_client, quiz)

    assert response.status_code == 400
    assert "already submitted" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Submitting and grading
# ---------------------------------------------------------------------------
def test_submit_grades_answers_and_returns_the_result(student_client, quiz, questions):
    started = start(student_client, quiz).json()
    first, second, third = questions

    response = submit(
        student_client,
        quiz,
        [
            {"question": first.pk, "selected_option": 1},
            {"question": second.pk, "selected_option": 1},
            {"question": third.pk, "selected_option": 3},
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["attempt"]["score"] == 3
    assert body["attempt"]["total_points"] == 4
    assert body["attempt"]["percentage"] == 75.0
    assert body["attempt"]["passed"] is True
    assert body["attempt"]["status"] == "auto_graded"

    breakdown = {row["question"]: row for row in body["answers"]}
    assert breakdown[first.pk]["is_correct"] is True
    assert breakdown[first.pk]["points_awarded"] == 1
    assert breakdown[second.pk]["points_awarded"] == 2
    assert breakdown[third.pk]["is_correct"] is False
    assert breakdown[third.pk]["correct_option_index"] == 0

    attempt = QuizAttempt.objects.get(pk=started["attempt"]["id"])
    assert attempt.status == QuizAttemptStatus.AUTO_GRADED
    assert attempt.submitted_at is not None
    assert attempt.answers == {str(first.pk): 1, str(second.pk): 1, str(third.pk): 3}


def test_unanswered_questions_score_zero(student_client, quiz, questions):
    start(student_client, quiz)

    body = submit(student_client, quiz, []).json()

    assert body["attempt"]["score"] == 0
    assert body["attempt"]["percentage"] == 0.0
    assert body["attempt"]["passed"] is False
    assert all(row["is_correct"] is False for row in body["answers"])


def test_submission_after_the_grace_window_is_rejected(student_client, student, quiz, questions):
    start(student_client, quiz)
    attempt = QuizAttempt.objects.get(quiz=quiz, student=student)
    QuizAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=11))

    response = submit(student_client, quiz, [{"question": questions[0].pk, "selected_option": 1}])

    assert response.status_code == 400
    assert response.json()["detail"] == "Time expired"

    attempt.refresh_from_db()
    assert attempt.status == QuizAttemptStatus.IN_PROGRESS
    assert attempt.submitted_at is None
    assert attempt.score == 0


def test_submission_inside_the_grace_window_is_accepted(student_client, student, quiz, questions):
    start(student_client, quiz)
    attempt = QuizAttempt.objects.get(quiz=quiz, student=student)
    # 10-minute limit plus 30 seconds late: still inside the 60-second grace.
    QuizAttempt.objects.filter(pk=attempt.pk).update(
        started_at=timezone.now() - timedelta(minutes=10, seconds=30)
    )

    response = submit(student_client, quiz, [{"question": questions[0].pk, "selected_option": 1}])

    assert response.status_code == 200
    assert response.json()["attempt"]["score"] == 1


def test_answers_for_another_quiz_are_rejected(student_client, quiz, questions, other_class, other_teacher):
    other_subject = Subject.objects.create(
        name="Mathematics", school_class=other_class, teacher=other_teacher
    )
    other_quiz = Quiz.objects.create(
        title="Other quiz",
        subject=other_subject,
        class_arm=other_class,
        time_limit_minutes=5,
        status=QuizStatus.PUBLISHED,
    )
    foreign_question = Question.objects.create(
        quiz=other_quiz, text="Foreign?", options=OPTIONS, correct_option_index=0
    )
    start(student_client, quiz)

    response = submit(student_client, quiz, [{"question": foreign_question.pk, "selected_option": 0}])

    assert response.status_code == 400
    assert "does not belong" in response.json()["answers"]


def test_out_of_range_option_index_is_rejected(student_client, quiz, questions):
    start(student_client, quiz)

    response = submit(student_client, quiz, [{"question": questions[0].pk, "selected_option": 9}])

    assert response.status_code == 400
    assert "between 0 and 3" in response.json()["answers"]


def test_submitting_twice_is_rejected(student_client, quiz, questions):
    start(student_client, quiz)
    answers = [{"question": questions[0].pk, "selected_option": 1}]
    assert submit(student_client, quiz, answers).status_code == 200

    second = submit(student_client, quiz, answers)

    assert second.status_code == 400
    assert "already been submitted" in second.json()["detail"]


def test_submit_without_starting_is_rejected(student_client, quiz, questions):
    response = submit(student_client, quiz, [])

    assert response.status_code == 400
    assert "Start the quiz" in response.json()["detail"]


def test_teacher_cannot_submit(teacher_client, quiz, questions):
    assert teacher_client.post(submit_url(quiz), {"answers": []}, format="json").status_code == 403


# ---------------------------------------------------------------------------
# Teacher results
# ---------------------------------------------------------------------------
def test_attempts_show_pass_fail_counts_and_class_average(
    teacher_client, student, classmate, outsider, quiz, questions, student_client
):
    start(student_client, quiz)
    submit(
        student_client,
        quiz,
        [
            {"question": questions[0].pk, "selected_option": 1},
            {"question": questions[1].pk, "selected_option": 1},
            {"question": questions[2].pk, "selected_option": 3},
        ],
    )
    QuizAttempt.objects.create(
        quiz=quiz,
        student=classmate,
        score=1,
        status=QuizAttemptStatus.AUTO_GRADED,
        submitted_at=timezone.now(),
    )
    QuizAttempt.objects.create(quiz=quiz, student=outsider)

    response = teacher_client.get(attempts_url(quiz))

    assert response.status_code == 200
    body = response.json()
    assert body["quiz"]["pass_mark"] == 2
    assert [row["student_name"] for row in body["attempts"]] == [
        "Chidera Okafor",
        "Emeka Nwosu",
        "Fatima Bello",
    ]
    assert body["attempts"][0]["percentage"] == 75.0
    assert body["attempts"][0]["passed"] is True
    assert body["attempts"][1]["percentage"] == 25.0
    assert body["attempts"][1]["passed"] is False
    assert body["attempts"][2]["status"] == "in_progress"

    assert body["summary"] == {
        "total": 3,
        "graded": 2,
        "in_progress": 1,
        "average_score": 2.0,
        "average_percentage": 50.0,
        "passed": 1,
        "failed": 1,
    }


def test_attempts_are_teacher_only_for_their_own_quiz(student_client, other_teacher_client, quiz, questions):
    assert student_client.get(attempts_url(quiz)).status_code == 403
    assert other_teacher_client.get(attempts_url(quiz)).status_code == 404


def test_staff_can_review_attempts(db, quiz, questions):
    staff = User.objects.create_superuser("principal-quiz", password="Board@2026")

    assert client_for(staff).get(attempts_url(quiz)).status_code == 200


# ---------------------------------------------------------------------------
# Building quizzes
# ---------------------------------------------------------------------------
def test_teacher_creates_a_quiz_for_their_own_class(teacher_client, teacher, school_class, subject):
    response = teacher_client.post(
        "/api/quizzes/",
        {
            "title": "Week 3 check",
            "subject": subject.pk,
            "class_arm": school_class.pk,
            "time_limit_minutes": 15,
        },
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == QuizStatus.DRAFT
    assert body["total_points"] == 0
    assert Quiz.objects.get(pk=body["id"]).created_by_id == teacher.pk


def test_teacher_cannot_create_a_quiz_for_another_class(teacher_client, other_class):
    other_subject = Subject.objects.create(name="Mathematics", school_class=other_class, teacher=None)

    response = teacher_client.post(
        "/api/quizzes/",
        {
            "title": "Not mine",
            "subject": other_subject.pk,
            "class_arm": other_class.pk,
            "time_limit_minutes": 10,
        },
        format="json",
    )

    assert response.status_code == 403


def test_quiz_subject_must_belong_to_the_class(teacher_client, school_class, subject, other_class):
    response = teacher_client.post(
        "/api/quizzes/",
        {
            "title": "Mismatch",
            "subject": subject.pk,
            "class_arm": other_class.pk,
            "time_limit_minutes": 10,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "subject" in response.json()


def test_student_cannot_create_a_quiz(student_client, school_class, subject):
    response = student_client.post(
        "/api/quizzes/",
        {
            "title": "Self quiz",
            "subject": subject.pk,
            "class_arm": school_class.pk,
            "time_limit_minutes": 10,
        },
        format="json",
    )

    assert response.status_code == 403


def test_adding_questions_updates_total_points(teacher_client, quiz):
    response = teacher_client.post(
        questions_url(quiz),
        {
            "text": "What is 5 x 5?",
            "options": ["10", "20", "25", "30"],
            "correct_option_index": 2,
            "points": 2,
        },
        format="json",
    )

    assert response.status_code == 201
    quiz.refresh_from_db()
    assert quiz.total_points == 2
    assert quiz.questions.count() == 1

    listing = teacher_client.get(questions_url(quiz)).json()
    assert listing[0]["correct_option_index"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "Three options", "options": ["A", "B", "C"], "correct_option_index": 0},
        {"text": "Index too high", "options": OPTIONS, "correct_option_index": 4},
        {"text": "Blank option", "options": ["A", "", "C", "D"], "correct_option_index": 0},
    ],
)
def test_invalid_questions_are_rejected(teacher_client, quiz, payload):
    response = teacher_client.post(questions_url(quiz), payload, format="json")

    assert response.status_code == 400
    assert quiz.questions.count() == 0


def test_student_cannot_add_questions(student_client, quiz):
    response = student_client.post(
        questions_url(quiz),
        {"text": "Sneaky", "options": OPTIONS, "correct_option_index": 0},
        format="json",
    )

    assert response.status_code == 403


def test_publishing_requires_questions(teacher_client, quiz):
    response = teacher_client.post(f"/api/quizzes/{quiz.pk}/publish/")

    assert response.status_code == 400
    assert "question" in str(response.json()).lower()


def test_publish_and_close_change_status(teacher_client, quiz, questions):
    quiz.status = QuizStatus.DRAFT
    quiz.save(update_fields=["status"])

    published = teacher_client.post(f"/api/quizzes/{quiz.pk}/publish/")
    assert published.status_code == 200
    assert published.json()["status"] == QuizStatus.PUBLISHED
    assert published.json()["total_points"] == 4

    closed = teacher_client.post(f"/api/quizzes/{quiz.pk}/close/")
    assert closed.status_code == 200
    assert closed.json()["status"] == QuizStatus.CLOSED


def test_students_only_list_published_quizzes_for_their_class(
    student_client, quiz, questions, school_class, subject
):
    draft = Quiz.objects.create(
        title="Draft quiz",
        subject=subject,
        class_arm=school_class,
        time_limit_minutes=5,
        status=QuizStatus.DRAFT,
    )

    response = student_client.get("/api/quizzes/")

    assert response.status_code == 200
    body = response.json()
    ids = [row["id"] for row in body["results"]]
    assert quiz.pk in ids
    assert draft.pk not in ids
    assert "questions" not in body["results"][0]
    assert "correct_option_index" not in response.content.decode()


def test_teacher_detail_includes_answers(teacher_client, quiz, questions):
    body = teacher_client.get(f"/api/quizzes/{quiz.pk}/").json()

    assert body["questions_count"] == 3
    assert body["questions"][0]["correct_option_index"] == 1
    assert body["total_points"] == 4


def test_deleting_a_question_recalculates_total_points(quiz, questions):
    second = questions[1]
    assert Quiz.objects.get(pk=quiz.pk).total_points == 4

    second.delete()

    assert Quiz.objects.get(pk=quiz.pk).total_points == 2
